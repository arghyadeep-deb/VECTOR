from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger


_HIGH_RISK_DOMAINS = {"lock", "alarm_control_panel", "gate", "garage_door", "camera"}
# A cover entity that is really a door/garage/gate is a security device.
_HIGH_RISK_COVER_CLASSES = {"garage", "gate", "door"}
# Domain an intent must resolve to (stops "lock front door" resolving to a
# binary_sensor and reporting "Locked" for a service call that did nothing).
_INTENT_DOMAIN = {
    "lock": "lock", "unlock": "lock",
    "arm": "alarm_control_panel", "disarm": "alarm_control_panel",
    "close": "cover", "open_cover": "cover",
    "set_temperature": "climate",
}
_FAIL = "Sorry, I couldn't execute that command: "


@dataclass
class VoiceCommand:
    raw_text: str
    intent: str
    entities: List[str] = field(default_factory=list)
    domain: str = ""
    service: str = ""
    confidence: float = 0.0
    params: Dict[str, Any] = field(default_factory=dict)


class IntentMapper:
    # Order matters (first match wins, search() is unanchored): word boundaries
    # keep "unlock" from parsing as "lock" and "disarm" as "arm"; open_cover and
    # set_temperature must precede the broader unlock/open and set..to patterns.
    _PATTERNS: List[Tuple[re.Pattern, str, str]] = [
        (re.compile(r"turn (?:on|switch on)\s+(.+)", re.I), "turn_on", "turn_on"),
        (re.compile(r"turn (?:off|switch off)\s+(.+)", re.I), "turn_off", "turn_off"),
        (re.compile(r"\btoggle\s+(.+)", re.I), "toggle", "toggle"),
        (re.compile(r"\bset\s+(?:the\s+)?(?:temperature|thermostat)\s+(?:to\s+)?(\d+)", re.I), "set_temperature", "set_temperature"),
        (re.compile(r"\bset\s+(.+?)\s+to\s+(.+)", re.I), "set_value", "set_value"),
        (re.compile(r"\bdisarm\s+(.+)", re.I), "disarm", "alarm_disarm"),
        (re.compile(r"\barm\s+(.+)", re.I), "arm", "alarm_arm_away"),
        (re.compile(r"\bunlock\s+(.+)", re.I), "unlock", "unlock"),
        (re.compile(r"\b(?:lock|secure)\s+(.+)", re.I), "lock", "lock"),
        (re.compile(r"\bopen\s+(?:the\s+)?(?:cover|blind|curtain|shade)s?\s+(.+)", re.I), "open_cover", "open_cover"),
        (re.compile(r"\bopen\s+(.+)", re.I), "unlock", "unlock"),
        (re.compile(r"\bdim\s+(.+?)\s+to\s+(\d+)", re.I), "dim", "turn_on"),
        (re.compile(r"\bclose\s+(.+)", re.I), "close", "close_cover"),
        (re.compile(r"(?:what'?s? is? )?the\s+(?:temperature|temp)\s+(?:in\s+)?(.+)", re.I), "get_temperature", "get_temperature"),
    ]

    def parse(self, text: str) -> Optional[VoiceCommand]:
        text_stripped = text.strip()
        for pattern, intent, service in self._PATTERNS:
            match = pattern.search(text_stripped)
            if match:
                groups = match.groups()
                entities = [groups[0]] if groups else []
                params: Dict[str, Any] = {}

                if intent == "set_value" and len(groups) >= 2:
                    params["value"] = groups[1].strip()
                elif intent == "dim" and len(groups) >= 2:
                    params["brightness"] = int(groups[1])
                elif intent == "set_temperature" and len(groups) >= 1:
                    params["temperature"] = int(groups[0])
                elif intent == "get_temperature":
                    params["entity_hint"] = groups[0] if groups else ""

                return VoiceCommand(
                    raw_text=text_stripped,
                    intent=intent,
                    entities=entities,
                    service=service,
                    confidence=0.8,
                    params=params,
                )

        return None


class EntityResolver:
    def __init__(self, entity_manager):
        self._entity_manager = entity_manager

    def resolve(self, entity_name: str, domain_hint: Optional[str] = None) -> Tuple[Any, float]:
        matches = self._entity_manager.matcher.match(entity_name, domain=domain_hint)
        if matches:
            return matches[0]
        return (None, 0.0)


class ConfirmDialog:
    _HIGH_RISK_PATTERNS = [
        re.compile(r"lock", re.I),
        re.compile(r"disarm", re.I),
        re.compile(r"unlock", re.I),
        re.compile(r"arm", re.I),
        re.compile(r"open.*(?:gate|door|garage)", re.I),
    ]

    @classmethod
    def needs_confirmation(cls, command: VoiceCommand) -> bool:
        if command.domain in _HIGH_RISK_DOMAINS:
            return True
        for pat in cls._HIGH_RISK_PATTERNS:
            if pat.search(command.raw_text):
                return True
        return False

    @classmethod
    def format_confirmation(cls, command: VoiceCommand) -> str:
        return (
            f"Are you sure you want to {command.intent} "
            f"{', '.join(command.entities) if command.entities else command.domain}?"
        )


class VoiceBridge:
    def __init__(self, entity_manager, connector):
        self._intent_mapper = IntentMapper()
        self._entity_resolver = EntityResolver(entity_manager)
        self._entity_manager = entity_manager
        self._connector = connector

    async def process(self, text: str) -> str:
        command = self._intent_mapper.parse(text)
        if command is None:
            return "I couldn't understand that home control command."

        domain = ""
        resolved = None
        hint = _INTENT_DOMAIN.get(command.intent)
        if command.intent == "set_temperature":
            # The regex captured the number, not a device: target the climate entity.
            climates = self._entity_manager.get_by_domain("climate")
            command.entities = []
            if len(climates) == 1:
                resolved = climates[0]
        elif command.intent != "get_temperature":
            for entity_name in command.entities:
                entity, score = self._entity_resolver.resolve(entity_name, hint)
                if entity:
                    resolved = entity
                    break
        if resolved:
            domain = resolved.domain
            command.entities = [resolved.entity_id]

        command.domain = domain
        door_like = bool(
            resolved and domain == "cover"
            and str(resolved.attributes.get("device_class", "")).lower() in _HIGH_RISK_COVER_CLASSES
        )

        if door_like or ConfirmDialog.needs_confirmation(command):
            return ConfirmDialog.format_confirmation(command)

        if command.intent != "get_temperature" and not resolved:
            # "I couldn't understand" prefix -> gateway reports rejected, not ok.
            return "I couldn't understand that home control command: no matching device was found."

        result = await self._execute(command)
        return result

    async def _execute(self, command: VoiceCommand) -> str:
        try:
            if command.intent == "turn_on":
                domain = command.domain or "light"
                for eid in command.entities:
                    data = dict(command.params) if command.params else {}
                    await self._connector.rest.call_service(domain, "turn_on", {**data, "entity_id": eid})
                return f"Turned on {', '.join(command.entities)}"

            if command.intent == "turn_off":
                domain = command.domain or "light"
                for eid in command.entities:
                    await self._connector.rest.call_service(domain, "turn_off", {"entity_id": eid})
                return f"Turned off {', '.join(command.entities)}"

            if command.intent == "dim":
                pct = max(0, min(100, int(command.params.get("brightness", 0))))
                for eid in command.entities:
                    await self._connector.rest.call_service("light", "turn_on", {"entity_id": eid, "brightness_pct": pct})
                return f"Set {', '.join(command.entities)} to {pct}%"

            if command.intent == "set_value" and "value" in command.params:
                if command.domain != "light":
                    return f"{_FAIL}setting a value is only supported for lights"
                entity = command.entities[0] if command.entities else ""
                await self._connector.rest.call_service("light", "turn_on", {
                    "entity_id": entity,
                    "brightness_pct": max(0, min(100, int(command.params["value"]))),
                })
                return f"Set {entity} to {command.params['value']}"

            if command.intent == "set_temperature":
                target = command.params.get("temperature", 22)
                if not command.entities:
                    return f"{_FAIL}no single climate device found"
                for eid in command.entities:
                    await self._connector.rest.call_service("climate", "set_temperature", {
                        "entity_id": eid,
                        "temperature": target,
                    })
                return f"Temperature set to {target} degrees"

            if command.intent == "get_temperature":
                hint = command.params.get("entity_hint", "")
                climates = self._entity_manager.get_by_domain("climate")
                if not climates:
                    return f"{_FAIL}no climate devices found"
                matches = self._entity_manager.matcher.match(hint, domain="climate") if hint else []
                e = matches[0][0] if matches else climates[0]
                temp = e.attributes.get("current_temperature")
                if e.state in ("unavailable", "unknown") or temp in (None, "", "unknown", "unavailable"):
                    return f"{_FAIL}no temperature reading available for {e.friendly_name}"
                return f"The current temperature is {temp} degrees"

            if command.intent in ("lock", "arm"):
                domain = "lock" if command.intent == "lock" else "alarm_control_panel"
                svc = "lock" if command.intent == "lock" else "alarm_arm_away"
                for eid in command.entities:
                    await self._connector.rest.call_service(domain, svc, {"entity_id": eid})
                return f"{'Locked' if command.intent == 'lock' else 'Armed'} {', '.join(command.entities)}"

            if command.intent in ("unlock", "disarm"):
                domain = "lock" if command.intent == "unlock" else "alarm_control_panel"
                svc = "unlock" if command.intent == "unlock" else "alarm_disarm"
                for eid in command.entities:
                    await self._connector.rest.call_service(domain, svc, {"entity_id": eid})
                return f"{'Unlocked' if command.intent == 'unlock' else 'Disarmed'} {', '.join(command.entities)}"

            if command.intent == "close":
                for eid in command.entities:
                    await self._connector.rest.call_service("cover", "close_cover", {"entity_id": eid})
                return f"Closed {', '.join(command.entities)}"

            if command.intent == "open_cover":
                for eid in command.entities:
                    await self._connector.rest.call_service("cover", "open_cover", {"entity_id": eid})
                return f"Opened {', '.join(command.entities)}"

            return f"{_FAIL}unsupported action '{command.intent}'"

        except Exception as e:
            logger.error("[VECTOR][ha_voice_bridge] Execute failed: {}", e)
            return f"Sorry, I couldn't execute that command: {e}"
