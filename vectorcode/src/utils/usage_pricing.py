"""Usage pricing — track and display token cost per session."""

from loguru import logger
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Optional

_USAGE_FILE = Path.home() / ".vector" / "usage.json"


def record_usage(model: str, input_tokens: int, output_tokens: int, cost: float):
    _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    usage = _load_usage()
    usage["sessions"].append({
        "model": model, "input_tokens": input_tokens,
        "output_tokens": output_tokens, "cost": cost, "timestamp": time.time(),
    })
    usage["total_cost"] += cost
    usage["total_tokens"] += input_tokens + output_tokens
    _save_usage(usage)


def _load_usage() -> dict:
    if _USAGE_FILE.exists():
        try:
            usage = json.loads(_USAGE_FILE.read_text())
            if not isinstance(usage, dict) or not isinstance(usage.get("sessions"), list):
                raise ValueError("usage file has an invalid schema")
            return usage
        except Exception as e:
            logger.error("[VECTOR][usage] refusing to replace corrupt usage file: {}", e)
            raise ValueError(f"Cannot load usage state from {_USAGE_FILE}") from e
    return {"sessions": [], "total_cost": 0.0, "total_tokens": 0}


def _save_usage(usage: dict):
    _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(dir=_USAGE_FILE.parent, prefix="usage.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(usage, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, _USAGE_FILE)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def get_usage_summary(days: Optional[int] = None) -> dict:
    usage = _load_usage()
    if days:
        cutoff = time.time() - days * 86400
        usage["sessions"] = [s for s in usage["sessions"] if s.get("timestamp", 0) > cutoff]
    return {
        "total_cost": round(sum(s["cost"] for s in usage["sessions"]), 6),
        "total_tokens": sum(s["input_tokens"] + s["output_tokens"] for s in usage["sessions"]),
        "session_count": len(usage["sessions"]),
    }
