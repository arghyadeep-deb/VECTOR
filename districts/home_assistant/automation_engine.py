from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


_TRIGGER_TYPES = {"time", "presence", "event", "security"}


@dataclass
class AutomationRule:
    name: str
    trigger: str
    conditions: Dict[str, Any] = field(default_factory=dict)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    cooldown_seconds: int = 60


class SceneManager:
    def __init__(self, connector):
        self._connector = connector
        self._scenes: Dict[str, Dict[str, Any]] = {}
        self._previous_states: Dict[str, Any] = {}
        self._load_scenes()

    def _load_scenes(self):
        path = Path(__file__).parent / "scenes.json"
        if path.exists():
            try:
                self._scenes = json.loads(path.read_text(encoding="utf-8"))
                logger.info("[HA Scenes] Loaded {} scenes", len(self._scenes))
            except Exception as e:
                logger.warning("[HA Scenes] Failed to load: {}", e)

    def list_scenes(self) -> List[str]:
        return list(self._scenes.keys())

    def get_scene(self, name: str) -> Optional[Dict[str, Any]]:
        return self._scenes.get(name)

    async def activate(self, name: str) -> bool:
        scene = self._scenes.get(name)
        if not scene:
            logger.warning("[HA Scenes] Scene '{}' not found", name)
            return False

        try:
            self._previous_states[name] = await self._connector.rest.get_states()
        except Exception:
            self._previous_states[name] = []

        failed = 0
        services = scene.get("services", [])
        for svc in services:
            domain = svc.get("domain", "")
            service = svc.get("service", "")
            data = svc.get("data", {})
            try:
                await self._connector.rest.call_service(domain, service, data)
            except Exception as e:
                failed += 1
                logger.warning("[VECTOR][ha_scenes] {}.{} failed: {}", domain, service, e)

        if failed:
            logger.warning("[VECTOR][ha_scenes] Scene '{}' only partly applied ({}/{} calls failed)", name, failed, len(services))
            return False
        logger.info("[VECTOR][ha_scenes] Scene '{}' activated", name)
        return True

    async def deactivate(self, name: str) -> bool:
        prev = self._previous_states.pop(name, None)
        if not prev:
            logger.warning("[HA Scenes] No saved state for '{}'", name)
            return False
        failed = 0
        for s in prev:
            eid = s.get("entity_id", "")
            state = s.get("state", "")
            domain = eid.split(".")[0] if "." in eid else ""
            # Map each saved state to a service that exists for its domain.
            # (Old code sent turn_off for any non-"on" state: cover.turn_off
            # does not exist, and "heat"/"unavailable" were turned OFF.)
            call = None
            if domain in ("light", "switch") and state in ("on", "off"):
                call = (domain, "turn_on" if state == "on" else "turn_off", {})
            elif domain == "cover" and state in ("open", "closed"):
                call = (domain, "open_cover" if state == "open" else "close_cover", {})
            elif domain == "climate" and state not in ("", "unavailable", "unknown"):
                call = (domain, "set_hvac_mode", {"hvac_mode": state})
            if call is None:
                continue
            try:
                await self._connector.rest.call_service(call[0], call[1], {"entity_id": eid, **call[2]})
            except Exception as e:
                failed += 1
                logger.warning("[VECTOR][ha_scenes] Restore {} failed: {}", eid, e)
        if failed:
            logger.warning("[VECTOR][ha_scenes] Scene '{}' restore incomplete ({} failures)", name, failed)
            return False
        logger.info("[VECTOR][ha_scenes] Scene '{}' deactivated", name)
        return True


class AutomationEngine:
    def __init__(self, connector, entity_manager):
        self._connector = connector
        self._entity_manager = entity_manager
        self._rules: Dict[str, AutomationRule] = {}
        self._last_triggered: Dict[str, float] = {}
        self._scene_manager = SceneManager(connector)
        self._register_builtins()

    @property
    def scene_manager(self) -> SceneManager:
        return self._scene_manager

    def _register_builtins(self):
        builtins = [
            AutomationRule(
                name="nighttime_auto_off",
                trigger="time",
                conditions={"hour": 23, "minute": 0},
                actions=[{"domain": "light", "service": "turn_off", "data": {}}],
                cooldown_seconds=3600,
            ),
            AutomationRule(
                name="morning_wakeup",
                trigger="time",
                conditions={"hour": 7, "minute": 0},
                actions=[{"scene": "morning"}],
                cooldown_seconds=3600,
            ),
            AutomationRule(
                name="away_mode",
                trigger="presence",
                conditions={"absent_seconds": 1800},
                actions=[{"scene": "away"}],
                cooldown_seconds=600,
            ),
            AutomationRule(
                name="arrival_mode",
                trigger="presence",
                conditions={"present": True},
                actions=[{"scene": "evening"}],
                cooldown_seconds=300,
            ),
            AutomationRule(
                name="movie_mode",
                trigger="event",
                conditions={"event_type": "movie_start"},
                actions=[{"scene": "movie"}],
                cooldown_seconds=120,
            ),
            AutomationRule(
                name="security_breach",
                trigger="security",
                conditions={"alarm_triggered": True},
                actions=[
                    {"domain": "light", "service": "turn_on", "data": {}},
                    {"domain": "switch", "service": "turn_on", "data": {}},
                    {"domain": "persistent_notification", "service": "create",
                     "data": {"message": "Security breach detected!"}},
                ],
                cooldown_seconds=300,
            ),
            AutomationRule(
                name="going_to_bed",
                trigger="event",
                conditions={"event_type": "bedtime"},
                actions=[
                    {"domain": "lock", "service": "lock", "data": {}},
                    {"domain": "light", "service": "turn_off", "data": {}},
                    {"domain": "alarm_control_panel", "service": "alarm_arm_away", "data": {}},
                ],
                cooldown_seconds=300,
            ),
        ]
        for rule in builtins:
            self._rules[rule.name] = rule

    def add_rule(self, rule: AutomationRule):
        if rule.trigger not in _TRIGGER_TYPES:
            logger.warning("[HA Auto] Unknown trigger type: {}", rule.trigger)
            return
        self._rules[rule.name] = rule
        logger.info("[HA Auto] Rule '{}' added", rule.name)

    def remove_rule(self, name: str):
        self._rules.pop(name, None)
        logger.info("[HA Auto] Rule '{}' removed", name)

    def get_rules(self) -> Dict[str, AutomationRule]:
        return dict(self._rules)

    def _is_on_cooldown(self, rule_name: str) -> bool:
        now = time.monotonic()
        last = self._last_triggered.get(rule_name)
        rule = self._rules.get(rule_name)
        # Never-triggered rules are not on cooldown (monotonic() can be < the
        # cooldown right after boot, so a 0 default wrongly blocked them).
        if rule and last is not None and (now - last) < rule.cooldown_seconds:
            return True
        return False

    async def evaluate_triggers(self, context: Dict[str, Any]) -> List[str]:
        triggered: List[str] = []
        for name, rule in self._rules.items():
            if self._is_on_cooldown(name):
                continue

            if rule.trigger == "time":
                now_hour = context.get("hour", -1)
                now_min = context.get("minute", -1)
                cond = rule.conditions
                if now_hour == cond.get("hour", -1) and now_min == cond.get("minute", -1):
                    triggered.append(name)

            elif rule.trigger == "presence":
                present = context.get("present", False)
                cond = rule.conditions
                if cond.get("present", False) and present:
                    triggered.append(name)
                elif (not present and not cond.get("present", False)
                      and context.get("absent_seconds", 0) >= cond.get("absent_seconds", 0)):
                    triggered.append(name)

            elif rule.trigger == "event":
                event_type = context.get("event_type", "")
                if event_type == rule.conditions.get("event_type", ""):
                    triggered.append(name)

            elif rule.trigger == "security":
                alarm = context.get("alarm_triggered", False)
                if alarm:
                    triggered.append(name)

        for name in triggered:
            self._last_triggered[name] = time.monotonic()
            rule = self._rules[name]
            await self._execute_rule(rule)

        return triggered

    async def _execute_rule(self, rule: AutomationRule):
        for action in rule.actions:
            if "scene" in action:
                await self._scene_manager.activate(action["scene"])
            else:
                domain = action.get("domain", "")
                service = action.get("service", "")
                data = action.get("data", {})
                try:
                    await self._connector.rest.call_service(domain, service, data)
                except Exception as e:
                    logger.warning("[HA Auto] Rule '{}' action failed: {}", rule.name, e)
        logger.info("[HA Auto] Rule '{}' executed", rule.name)
