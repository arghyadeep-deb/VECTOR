from __future__ import annotations

import datetime

from loguru import logger

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from core.city.agent_base import AgentBase
from .connector import HAConfig, HAConnector
from .entity_manager import EntityManager
from .automation_engine import AutomationEngine
from .voice_bridge import VoiceBridge


class HomeAssistantAgent(AgentBase):
    """Front door for the home_assistant district (2026-07-30 audit fix).

    entity_manager.py / connector.py / automation_engine.py / voice_bridge.py
    were all real, well-built components (REST+WS client, fuzzy entity
    matcher, rule/scene engine, NL->service-call bridge) with ZERO caller
    anywhere in the codebase — no manifest entry, no DISTRICT_TASK_MAP key,
    no top-level agent class at all, confirmed by the 2026-07-30 audit.
    VoiceBridge already implements the real pipeline (parse -> resolve
    entity -> confirm-if-high-risk -> execute via HA's REST API); this class
    just gives it the AgentBase contract governor.dispatch() expects.

    Connects to the configured Home Assistant instance lazily, on first real
    use, rather than at import/registration time — so VECTOR still boots
    fine with no HA instance configured, and this district then honestly
    reports "not configured" / "unreachable" instead of crashing or silently
    doing nothing (the AgentBase no-op fallback this district effectively
    had before, by virtue of not existing at all).
    """

    def __init__(self):
        super().__init__(agent_id="home_assistant_agent", name="home_assistant_agent", district="home_assistant")
        self.capabilities = ["general", "ha_status"]
        self._config = HAConfig()
        self._connector = HAConnector(self._config)
        self._entity_manager = EntityManager()
        self._automation = AutomationEngine(self._connector, self._entity_manager)
        self._bridge = VoiceBridge(self._entity_manager, self._connector)
        self._connected = False

    async def _ensure_ready(self) -> str | None:
        """Returns a human-readable error if HA isn't usable right now, else None."""
        if not self._config.token:
            return (
                "Home Assistant isn't configured yet — set HASS_URL and "
                "HASS_TOKEN (env vars), or home_assistant.host/token in "
                "VECTOR's config, then restart the API."
            )
        if not self._connected:
            ok = await self._connector.connect()
            if not ok:
                return f"Couldn't reach Home Assistant at {self._config.base_url}."
            try:
                found = await self._entity_manager.discover(self._connector)
            except Exception as e:
                logger.warning("[VECTOR][home_assistant] entity discovery failed: {}", e)
                found = 0
            if not found:
                return f"Connected to Home Assistant at {self._config.base_url} but found no devices."
            self._connected = True
        return None

    async def run(self, task: dict) -> dict:
        self.last_active = datetime.datetime.utcnow().isoformat()
        params = task.get("params", {}) or {}
        query = params.get("query") or params.get("text") or task.get("content") or ""
        task_type = task.get("type", "")

        err = await self._ensure_ready()
        if err:
            return {"status": "error", "agent": self.name, "response": err}

        if task_type == "ha_status":
            health = await self._connector.health()
            return {
                "status": "ok" if health.get("rest") else "error",
                "agent": self.name,
                "response": f"Home Assistant status: {health}",
            }

        if not query:
            return {
                "status": "error",
                "agent": self.name,
                "response": "I didn't get a home-control command to run.",
            }

        # 2026-09-23 (permission-boundary audit, round 2): this used to call
        # self._bridge.process(query) directly -- real smart-home device
        # control with NO permission-gateway check. The intended front door
        # (core/voice/ambient_listener.py) now goes through
        # PermissionGateway.execute() before ever reaching Governor.dispatch()
        # -> here, but Governor.dispatch({"type": "home_control"/"smart_home"})
        # is itself still reachable directly (DISTRICT_TASK_MAP routes both
        # to this district) -- no current caller does that today, but RULE 3
        # ("Permission Gateway is the ONLY path to real-world actions...
        # Nothing bypasses this") means the district agent must not rely on
        # callers doing the right thing. Self-gating here closes it for any
        # caller, present or future, that reaches this agent without going
        # through the gateway first.
        from core.loop.permission_gateway import Action, PermissionGateway
        gw_result = await PermissionGateway().execute(
            Action(action_type="home_control", params={"text": query}, proposed_by=self.name)
        )
        if not gw_result.approved:
            return {
                "status": "blocked",
                "agent": self.name,
                "response": gw_result.reason or "Home control action was not approved.",
            }
        payload = gw_result.result or {}
        return {
            "status": payload.get("status", "ok"),
            "agent": self.name,
            "response": payload.get("message", "Done."),
        }
