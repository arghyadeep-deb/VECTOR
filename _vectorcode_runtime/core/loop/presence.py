"""
TriggerMode + PresenceConfig — controls VECTOR's proactive/reactive posture.
Spec §5.

Modes:
  REACTIVE  — loop observes only; only responds to explicit wake/trigger
  HYBRID    — proactive only for allowed_proactive_agents + outside DND hours
  PROACTIVE — fully autonomous proactive care (default behaviour today)

DND gate: no proactive pings during do_not_disturb hours (default 23:00–08:00).
Emergency override: security/RED-tier tasks always bypass DND.
"""

import datetime
from enum import Enum
from dataclasses import dataclass, field

from loguru import logger
from core.config import CONFIG


class TriggerMode(str, Enum):
    REACTIVE  = "reactive"
    HYBRID    = "hybrid"
    PROACTIVE = "proactive"


@dataclass
class PresenceConfig:
    """Runtime presence configuration loaded from CONFIG["presence"]."""
    mode: TriggerMode = TriggerMode.PROACTIVE
    dnd_start_hour: int = 23     # inclusive
    dnd_end_hour: int   = 8      # exclusive (i.e. 23:00 – 08:00)
    allowed_proactive_agents: list[str] = field(default_factory=lambda: [
        "nudge_engine", "chief_of_staff", "daily_reviewer",
    ])
    wake_keywords: list[str] = field(default_factory=lambda: [
        "hey vector", "vector", "ok vector",
    ])

    @classmethod
    def from_config(cls) -> "PresenceConfig":
        import os as _os
        cfg = CONFIG.get("presence", {})
        # env vars take precedence over CONFIG snapshot (allows runtime override)
        mode_raw = _os.environ.get("VECTOR_PRESENCE_MODE", cfg.get("mode", TriggerMode.PROACTIVE.value))
        try:
            mode = TriggerMode(mode_raw)
        except ValueError:
            logger.warning("[VECTOR][presence] unknown mode '{}', defaulting to proactive", mode_raw)
            mode = TriggerMode.PROACTIVE
        return cls(
            mode=mode,
            dnd_start_hour=int(_os.environ.get("VECTOR_DND_START", cfg.get("dnd_start_hour", 23))),
            dnd_end_hour=int(_os.environ.get("VECTOR_DND_END",   cfg.get("dnd_end_hour", 8))),
            allowed_proactive_agents=cfg.get("allowed_proactive_agents", cls.__dataclass_fields__["allowed_proactive_agents"].default_factory()),
            wake_keywords=cfg.get("wake_keywords", cls.__dataclass_fields__["wake_keywords"].default_factory()),
        )


# Module-level singleton — reloaded on each call to get_presence_config()
_presence_config: PresenceConfig | None = None


def get_presence_config() -> PresenceConfig:
    global _presence_config
    if _presence_config is None:
        _presence_config = PresenceConfig.from_config()
    return _presence_config


def reload_presence_config() -> PresenceConfig:
    global _presence_config
    _presence_config = PresenceConfig.from_config()
    return _presence_config


def is_dnd_active(cfg: PresenceConfig | None = None) -> bool:
    """Returns True if current local time is within DND window."""
    if cfg is None:
        cfg = get_presence_config()
    now_hour = datetime.datetime.now().hour
    start, end = cfg.dnd_start_hour, cfg.dnd_end_hour
    if start > end:  # crosses midnight (e.g. 23 → 8)
        return now_hour >= start or now_hour < end
    return start <= now_hour < end


def allow_proactive(
    agent_name: str,
    *,
    is_emergency: bool = False,
    district: str = "",
    cfg: PresenceConfig | None = None,
) -> bool:
    """
    Gate for the autonomous loop to call before emitting a proactive action.

    Returns True if the agent is allowed to proactively act right now.
    Always returns True for emergency / security tasks regardless of mode/DND.
    """
    if cfg is None:
        cfg = get_presence_config()

    # Emergency + security always bypass
    if is_emergency or district in ("security", "ops", "governance"):
        return True

    if cfg.mode == TriggerMode.REACTIVE:
        return False

    if cfg.mode == TriggerMode.PROACTIVE:
        # Respect DND even in PROACTIVE mode
        if is_dnd_active(cfg):
            logger.debug("[VECTOR][presence] DND active — suppressing proactive for {}", agent_name)
            return False
        return True

    # HYBRID: allow only listed agents, outside DND
    if agent_name in cfg.allowed_proactive_agents and not is_dnd_active(cfg):
        return True
    return False


def is_reactive_only(cfg: PresenceConfig | None = None) -> bool:
    """True when loop should idle until explicit wake/trigger."""
    if cfg is None:
        cfg = get_presence_config()
    return cfg.mode == TriggerMode.REACTIVE


if __name__ == "__main__":
    cfg = get_presence_config()
    print(f"mode={cfg.mode} dnd_start={cfg.dnd_start_hour} dnd_end={cfg.dnd_end_hour}")
    print(f"dnd_active={is_dnd_active(cfg)}")

    # Security always allowed
    assert allow_proactive("threat_scout", is_emergency=True, cfg=cfg) is True

    # REACTIVE mode blocks normal agents
    reactive_cfg = PresenceConfig(mode=TriggerMode.REACTIVE)
    assert allow_proactive("daily_reviewer", cfg=reactive_cfg) is False

    # HYBRID allows listed agents outside DND
    hybrid_cfg = PresenceConfig(
        mode=TriggerMode.HYBRID,
        dnd_start_hour=23,
        dnd_end_hour=8,
    )
    # Should depend on current hour — just check it doesn't crash
    result = allow_proactive("nudge_engine", cfg=hybrid_cfg)
    print(f"hybrid nudge_engine allowed={result}")

    print("OK presence")
