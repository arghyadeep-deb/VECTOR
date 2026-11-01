from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from core.config import CONFIG
from core.runtime.doctor import run_dependency_doctor


@dataclass
class WorldSnapshot:
    status: str
    timestamp: str
    runtime: dict[str, Any]
    readiness: dict[str, Any]
    agents: dict[str, Any]
    memory: dict[str, Any]
    safety: dict[str, Any]
    sensing: dict[str, Any]
    voice: dict[str, Any]
    tasks: dict[str, Any]
    frontend: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_section(name: str, fn, fallback: Any) -> Any:
    try:
        return fn()
    except Exception as exc:
        return {"status": "unavailable", "section": name, "error": str(exc)}


def _runtime_section() -> dict[str, Any]:
    from core.api.routers.status import START_TIME, get_uptime_seconds

    return {
        "version": CONFIG.get("version", "1.0.0"),
        "uptime_seconds": get_uptime_seconds(),
        "started_at": START_TIME.isoformat(),
        "mode": "api_or_local",
        "ollama_host": CONFIG.get("ollama_host", "http://127.0.0.1:11434"),
    }


def _agents_section() -> dict[str, Any]:
    from core.city.agent_registry import get_registry

    agents = get_registry().list_all()
    alive = [a for a in agents if a.get("is_alive") or a.get("health_points", 0) > 0]
    districts = sorted({a.get("district", "") for a in agents if a.get("district")})
    hp_values = [float(a.get("health_points", 0) or 0) for a in agents]
    return {
        "count": len(agents),
        "alive": len(alive),
        "district_count": len(districts),
        "districts": districts,
        "average_hp": round(sum(hp_values) / len(hp_values), 2) if hp_values else 0,
        "elite": len([hp for hp in hp_values if hp >= 800]),
        "critical": len([hp for hp in hp_values if 0 < hp < 200]),
        "ghost": len([hp for hp in hp_values if hp <= 0]),
        "sample": agents[:12],
    }


def _memory_section() -> dict[str, Any]:
    from core.memory.episodic import EpisodicMemory

    memory = EpisodicMemory()
    recent = []
    try:
        recent = memory.recall("", limit=8)
    except Exception:
        recent = []
    return {
        "stats": memory.get_stats(),
        "recent": recent,
    }


def _safety_section(app_state: Any | None) -> dict[str, Any]:
    gateway = getattr(app_state, "permission_gateway", None) if app_state is not None else None
    if gateway is None:
        try:
            from core.api.routers.gateway import _gw_singleton

            gateway = _gw_singleton
        except Exception:
            gateway = None

    pending = []
    audit = []
    if gateway is not None:
        if hasattr(gateway, "get_pending"):
            pending = gateway.get_pending()
        if hasattr(gateway, "get_audit_log"):
            audit = gateway.get_audit_log(limit=10)

    return {
        "pending_approvals": pending,
        "pending_count": len(pending),
        "recent_audit": audit,
        "auth_configured": bool(CONFIG.get("vector_api_key") or CONFIG.get("api_key")),
    }


def _sensing_section() -> dict[str, Any]:
    try:
        from core.sensing.health_monitor import HealthMonitor

        snap = HealthMonitor().get_health_snapshot()
        return {
            "fatigue_score": snap.get("fatigue_score", 0.0),
            "energy_level": snap.get("energy_level", "unknown"),
            "system_load": snap.get("system_load", {}),
            "camera_available": snap.get("camera_available", False),
        }
    except Exception as exc:
        return {
            "fatigue_score": 0.0,
            "energy_level": "unknown",
            "system_load": {},
            "camera_available": False,
            "error": str(exc),
        }


def _voice_section() -> dict[str, Any]:
    voice_cfg = CONFIG.get("voice", {}) if isinstance(CONFIG, dict) else {}
    consent_granted = False
    try:
        from core.voice.ambient_listener import has_ambient_consent

        consent_granted = has_ambient_consent()
    except Exception:
        consent_granted = False
    # tts/stt used to be hardcoded "available" regardless of real state --
    # phantom success, inconsistent with every other section in this file
    # (sensing/agents/memory all query real state with a safe fallback).
    # Reuse the existing lightweight, cached TTS check (same file
    # _runtime_section() already cross-imports from) rather than loading
    # the real audio models here; no equivalent cheap STT check exists yet,
    # so report "unknown" honestly instead of guessing.
    tts_status = "unknown"
    try:
        from core.api.routers.status import _get_tts_status_cached

        cached = _get_tts_status_cached()
        tts_status = cached.get("tts_engine", "unknown")
    except Exception:
        tts_status = "unknown"
    return {
        "status": "ok",
        "ambient_enabled": bool(voice_cfg.get("ambient_enabled", False)),
        "ambient_consent": consent_granted,
        "wake_word": voice_cfg.get("wake_word", "Hey Vector"),
        "tts": tts_status,
        "stt": "unknown",
    }


def _tasks_section() -> dict[str, Any]:
    from core.loop.task_queue import TaskQueue

    summary = TaskQueue.get().summary()
    return summary if isinstance(summary, dict) else {"summary": summary}


def _frontend_section(open_panels: list[str] | None) -> dict[str, Any]:
    return {
        "hud": "/hud/",
        "open_panels": open_panels or [],
        "open_panel_count": len(open_panels or []),
        "feature_registry": "frontend/js/widgets.js",
    }


def build_world_snapshot(
    app_state: Any | None = None,
    open_panels: list[str] | None = None,
    *,
    mounted_routes: Iterable[str] | None = None,
) -> WorldSnapshot:
    """Build one local, offline-safe view of VECTOR's current world state."""
    readiness_report = run_dependency_doctor(
        include_optional=False,
        mounted_routes=mounted_routes,
    ).to_dict()
    status = "ok" if readiness_report.get("required_failed", 1) == 0 else "unready"

    safety = _safe_section("safety", lambda: _safety_section(app_state), {})
    if isinstance(safety, dict) and safety.get("pending_count", 0):
        status = "attention"

    return WorldSnapshot(
        status=status,
        timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
        runtime=_safe_section("runtime", _runtime_section, {}),
        readiness={
            "status": readiness_report.get("status"),
            "required_failed": readiness_report.get("required_failed", 0),
            "warnings": readiness_report.get("warnings", 0),
        },
        agents=_safe_section("agents", _agents_section, {}),
        memory=_safe_section("memory", _memory_section, {}),
        safety=safety,
        sensing=_safe_section("sensing", _sensing_section, {}),
        voice=_safe_section("voice", _voice_section, {}),
        tasks=_safe_section("tasks", _tasks_section, {}),
        frontend=_frontend_section(open_panels),
    )
