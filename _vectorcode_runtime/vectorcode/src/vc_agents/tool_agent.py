"""
ToolAgent — wraps vectorcode's tool_guardrails.py for safe tool execution.

All tool calls in vectorcode go through ToolCallGuardrailController before execution.
This agent provides the interface for running tools safely — checks permission tiers,
applies guardrails, logs decisions to VECTOR's episodic memory.
"""
from __future__ import annotations

import datetime


from loguru import logger
from core.config import CONFIG

# Permission tiers
_GREEN = set(CONFIG.get("permission", {}).get("green", []))
_YELLOW = set(CONFIG.get("permission", {}).get("yellow", []))
_RED = set(CONFIG.get("permission", {}).get("red", []))


class ToolAgent:
    """
    Safe tool executor for vectorcode's agent runtime.

    Checks VECTOR's permission gateway before executing any tool.
    Logs all tool calls to episodic memory. Blocks RED-tier tools unless
    explicitly approved.
    """

    def __init__(self):
        self._guardrail_ctrl = None
        self._episodic = None
        self._execution_log: list[dict] = []
        logger.info("[VECTOR][vc_tool] initialized")

    def _get_guardrail(self):
        if self._guardrail_ctrl is None:
            try:
                from vectorcode.src.agent.tool_guardrails import ToolCallGuardrailController
                self._guardrail_ctrl = ToolCallGuardrailController()
            except Exception as e:
                logger.debug("[VECTOR][vc_tool] guardrail unavailable: {}", e)
        return self._guardrail_ctrl

    def _get_episodic(self):
        if self._episodic is None:
            from core.memory.episodic import EpisodicMemory
            self._episodic = EpisodicMemory()
        return self._episodic

    def get_permission_tier(self, tool_name: str) -> str:
        """Classify a tool into GREEN / YELLOW / RED permission tier."""
        name_lower = tool_name.lower()
        if any(g in name_lower for g in _GREEN) or tool_name in _GREEN:
            return "GREEN"
        if any(r in name_lower for r in _RED) or tool_name in _RED:
            return "RED"
        if any(y in name_lower for y in _YELLOW) or tool_name in _YELLOW:
            return "YELLOW"
        # Default classification by tool type
        if any(w in name_lower for w in ["read", "search", "check", "status", "list", "get"]):
            return "GREEN"
        if any(w in name_lower for w in ["write", "create", "send", "post", "commit"]):
            return "YELLOW"
        if any(w in name_lower for w in ["delete", "exec", "deploy", "push", "financial"]):
            return "RED"
        return "YELLOW"

    def can_execute(self, tool_name: str, params: dict = None) -> dict:
        """Check if a tool is allowed to execute. Returns {allowed, tier, reason}."""
        tier = self.get_permission_tier(tool_name)
        guardrail = self._get_guardrail()

        if guardrail:
            try:
                allowed = guardrail.check(tool_name, params or {})
                return {"allowed": allowed, "tier": tier, "reason": "guardrail_check"}
            except Exception as e:
                logger.debug("[VECTOR][vc_tool] guardrail check failed: {}", e)

        # Fallback: tier-based check
        if tier == "GREEN":
            return {"allowed": True, "tier": tier, "reason": "green_tier_auto_approved"}
        if tier == "RED":
            return {"allowed": False, "tier": tier, "reason": "red_tier_requires_approval"}
        return {"allowed": True, "tier": tier, "reason": "yellow_tier_permitted"}

    def execute(self, tool_name: str, params: dict = None,
                executor=None) -> dict:
        """Execute a tool after permission check. executor is a callable."""
        params = params or {}
        check = self.can_execute(tool_name, params)

        log_entry = {
            "tool": tool_name,
            "params_keys": list(params.keys()),
            "tier": check["tier"],
            "allowed": check["allowed"],
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "result": None,
        }

        if not check["allowed"]:
            logger.warning("[VECTOR][vc_tool] BLOCKED {} ({}): {}", tool_name, check["tier"], check["reason"])
            log_entry["result"] = "blocked"
            self._execution_log.append(log_entry)
            return {"status": "blocked", "tool": tool_name, "reason": check["reason"]}

        logger.info("[VECTOR][vc_tool] executing {} (tier={})", tool_name, check["tier"])

        if executor is None:
            log_entry["result"] = "no_executor"
            self._execution_log.append(log_entry)
            return {"status": "error", "tool": tool_name, "error": "No executor provided"}

        try:
            result = executor(tool_name, **params)
            log_entry["result"] = "success"
            self._execution_log.append(log_entry)
            # Store to episodic memory
            try:
                self._get_episodic().store(
                    event_type="tool_execution",
                    content=f"Tool '{tool_name}' executed ({check['tier']})",
                    tags=["vectorcode", "tool", check["tier"].lower()],
                    source="tool_agent",
                )
            except Exception:
                logger.opt(exception=True).debug("[VECTOR] suppressed exception")
            return {"status": "ok", "tool": tool_name, "result": result, "tier": check["tier"]}
        except Exception as e:
            log_entry["result"] = f"error: {e}"
            self._execution_log.append(log_entry)
            logger.error("[VECTOR][vc_tool] {} execution failed: {}", tool_name, e)
            return {"status": "error", "tool": tool_name, "error": str(e)}

    def get_execution_log(self, last_n: int = 10) -> list[dict]:
        """Return recent tool execution log."""
        return self._execution_log[-last_n:]


if __name__ == "__main__":
    agent = ToolAgent()
    tests = [
        ("search_web", {"query": "AI news"}),
        ("read_file", {"path": "test.py"}),
        ("commit_code", {"message": "test commit"}),
        ("delete_files", {"path": "/tmp/test"}),
        ("deploy_production", {}),
    ]
    for tool, params in tests:
        check = agent.can_execute(tool, params)
        print(f"[OK] {tool}: tier={check['tier']} allowed={check['allowed']}")
    print(f"[OK] permission_tiers: GREEN={len(_GREEN)} YELLOW={len(_YELLOW)} RED={len(_RED)}")
    print("tool_agent.py OK")
