"""Usage pricing — track and display token cost per session."""

from loguru import logger
import json
from pathlib import Path
from typing import Optional

_USAGE_FILE = Path.home() / ".vector" / "usage.json"


def record_usage(model: str, input_tokens: int, output_tokens: int, cost: float):
    _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    usage = _load_usage()
    usage["sessions"].append({
        "model": model, "input_tokens": input_tokens,
        "output_tokens": output_tokens, "cost": cost,
    })
    usage["total_cost"] += cost
    usage["total_tokens"] += input_tokens + output_tokens
    _save_usage(usage)


def _load_usage() -> dict:
    if _USAGE_FILE.exists():
        try: return json.loads(_USAGE_FILE.read_text())
        except Exception as e:
            from loguru import logger
            logger.debug("[VECTOR][usage] load usage file skipped: {}", e)
    return {"sessions": [], "total_cost": 0.0, "total_tokens": 0}


def _save_usage(usage: dict):
    _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _USAGE_FILE.write_text(json.dumps(usage, indent=2))


def get_usage_summary(days: Optional[int] = None) -> dict:
    import time
    usage = _load_usage()
    if days:
        cutoff = time.time() - days * 86400
        usage["sessions"] = [s for s in usage["sessions"] if s.get("timestamp", 0) > cutoff]
    return {
        "total_cost": round(sum(s["cost"] for s in usage["sessions"]), 6),
        "total_tokens": sum(s["input_tokens"] + s["output_tokens"] for s in usage["sessions"]),
        "session_count": len(usage["sessions"]),
    }
