"""Persistent checkpoint for the autonomous loop.

Stores three pieces of state in semantic_memory so the loop survives
Ctrl+C and process restarts:
  - loop:current_goal   — id of the active SHORT/MID horizon goal
  - loop:last_decision  — JSON of the last executed decision candidate
  - loop:agent_hp       — JSON dict of {agent_id: hp} snapshot

Uses EpisodicMemory.remember() / recall_fact() — no new tables needed.
"""
import json
import datetime
import threading
from typing import Callable, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Runtime state — tick counter, running flag, broadcast callback.
# These break the circular import cycle (P1.4):
#   core.loop.permission_gateway → core.api.routers.websocket (replaced by ui_broadcast)
#   core.api.{health,app} → core.loop.autonomous_loop (replaced by get_runtime)
# ---------------------------------------------------------------------------

_rt_lock = threading.Lock()
_rt_tick_count: int = 0
_rt_running: bool = False
_rt_start_time: str = ""
_ui_broadcast_fn: Optional[Callable] = None

# Cross-process heartbeat (2026-07-19): the loop (`run_vector.py loop`) and the
# API server (`run_vector.py api`) are separate processes, so the in-memory
# runtime above is invisible to the API — /loop/status reported running=False
# forever while the loop was healthy. The loop now also writes a throttled
# heartbeat file; get_runtime() falls back to it when the in-process state is
# not running.
_HEARTBEAT_MAX_AGE_SEC = 10.0
_hb_last_write: float = 0.0


def _heartbeat_path():
    from core.runtime_paths import data_path
    return data_path("loop_heartbeat.json")


def _write_heartbeat(tick_count: int, running: bool, start_time: str) -> None:
    global _hb_last_write
    import json
    import os
    import time
    now = time.time()
    if running and (now - _hb_last_write) < 2.0:
        return  # throttle: at most one write per 2s
    _hb_last_write = now
    try:
        path = _heartbeat_path()
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({
                "tick_count": tick_count,
                "running": running,
                "start_time": start_time,
                "pid": os.getpid(),
                "ts": now,
            }, f)
        os.replace(tmp, str(path))
    except Exception:
        pass  # heartbeat is best-effort; never break the loop


def _read_heartbeat() -> Optional[dict]:
    import json
    import time
    try:
        with open(_heartbeat_path(), encoding="utf-8") as f:
            hb = json.load(f)
        if hb.get("running") and (time.time() - float(hb.get("ts", 0))) <= _HEARTBEAT_MAX_AGE_SEC:
            return hb
        return None  # stale or stopped
    except Exception:
        return None


def update_runtime(*, tick_count: int, running: bool, start_time: str = "") -> None:
    """Called by AutonomousLoop on each tick and on start/stop."""
    global _rt_tick_count, _rt_running, _rt_start_time
    with _rt_lock:
        _rt_tick_count = tick_count
        _rt_running = running
        if start_time:
            _rt_start_time = start_time
        st = _rt_start_time
    _write_heartbeat(tick_count, running, st)


def get_runtime() -> dict:
    """Return a snapshot of current loop runtime state.

    Falls back to the cross-process heartbeat file when this process isn't
    the one running the loop (API process case).
    """
    with _rt_lock:
        if _rt_running:
            return {
                "tick_count": _rt_tick_count,
                "running": _rt_running,
                "start_time": _rt_start_time,
            }
    hb = _read_heartbeat()
    if hb:
        return {
            "tick_count": int(hb.get("tick_count", 0)),
            "running": True,
            "start_time": str(hb.get("start_time", "")),
        }
    with _rt_lock:
        return {
            "tick_count": _rt_tick_count,
            "running": _rt_running,
            "start_time": _rt_start_time,
        }


def register_ui_broadcast(fn: Callable) -> None:
    """Register the WebSocket broadcast function at app startup (avoids circular import)."""
    global _ui_broadcast_fn
    _ui_broadcast_fn = fn


async def ui_broadcast(payload: dict) -> bool:
    """Emit a UI event via the registered broadcast function. Returns success."""
    fn = _ui_broadcast_fn
    if fn is None:
        return False
    try:
        await fn(payload)
        return True
    except Exception:
        return False


_PREFIX = "loop:"
_GOAL_KEY = f"{_PREFIX}current_goal"
_DECISION_KEY = f"{_PREFIX}last_decision"
_AGENT_HP_KEY = f"{_PREFIX}agent_hp"


def _mem():
    from core.memory.episodic import EpisodicMemory
    return EpisodicMemory()


def save_goal(goal_id: str) -> None:
    try:
        _mem().remember(_GOAL_KEY, goal_id, category="loop_state", confidence=1.0)
    except Exception as e:
        logger.debug("[VECTOR][loop_state] save_goal failed: {}", e)


def load_goal() -> str | None:
    try:
        row = _mem().recall_fact(_GOAL_KEY)
        return row["value"] if row else None
    except Exception as e:
        logger.debug("[VECTOR][loop_state] load_goal failed: {}", e)
        return None


def save_decision(action_type: str, params: dict, score: float) -> None:
    try:
        payload = json.dumps({
            "action_type": action_type,
            "params": params,
            "score": score,
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }, default=str)
        _mem().remember(_DECISION_KEY, payload, category="loop_state", confidence=1.0)
    except Exception as e:
        logger.debug("[VECTOR][loop_state] save_decision failed: {}", e)


def load_decision() -> dict | None:
    try:
        row = _mem().recall_fact(_DECISION_KEY)
        if row and row.get("value"):
            return json.loads(row["value"])
        return None
    except Exception as e:
        logger.debug("[VECTOR][loop_state] load_decision failed: {}", e)
        return None


def save_agent_hp(registry) -> None:
    """Snapshot HP of all living agents into semantic_memory."""
    try:
        agents = registry.get_all_agents()
        snapshot = {
            a.id: {"name": a.name, "district": a.district, "hp": a.health_points}
            for a in agents
        }
        _mem().remember(_AGENT_HP_KEY, json.dumps(snapshot, default=str),
                        category="loop_state", confidence=1.0)
    except Exception as e:
        logger.debug("[VECTOR][loop_state] save_agent_hp failed: {}", e)


def load_agent_hp() -> dict | None:
    """Return {agent_id: {name, district, hp}} or None if no snapshot."""
    try:
        row = _mem().recall_fact(_AGENT_HP_KEY)
        if row and row.get("value"):
            return json.loads(row["value"])
        return None
    except Exception as e:
        logger.debug("[VECTOR][loop_state] load_agent_hp failed: {}", e)
        return None


def restore_agent_hp(registry) -> int:
    """Restore HP from last checkpoint into currently registered agents. Returns count restored."""
    snapshot = load_agent_hp()
    if not snapshot:
        return 0
    agents = {a.id: a for a in registry.get_all_agents()}
    restored = 0
    for agent_id, data in snapshot.items():
        if agent_id in agents:
            agents[agent_id].health_points = data["hp"]
            restored += 1
    if restored:
        logger.info("[VECTOR][loop_state] restored HP for {} agents", restored)
    return restored


if __name__ == "__main__":
    save_goal("g_vector_phase1")
    assert load_goal() == "g_vector_phase1"
    save_decision("research", {"query": "test"}, 0.75)
    d = load_decision()
    assert d and d["action_type"] == "research"
    print("loop_state OK")
