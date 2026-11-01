# Ported from GitHub/VectorCode_vectorcode/repo/vector_time.py
"""Timezone-aware clock for VectorCode."""
from loguru import logger
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore

_cached_tz: Optional["ZoneInfo"] = None
_cache_resolved: bool = False


def _resolve_timezone_name() -> str:
    tz_env = os.environ.get("VECTOR_TIMEZONE", os.environ.get("VECTOR_TIMEZONE", "")).strip()
    if tz_env:
        return tz_env
    try:
        import yaml
        config_path = _get_config_path()
        if config_path and config_path.exists():
            with open(config_path) as f:
                cfg = yaml.safe_load(f) or {}
            tz_cfg = cfg.get("timezone", "")
            if isinstance(tz_cfg, str) and tz_cfg.strip():
                return tz_cfg.strip()
    except Exception as _sve:
        logger.debug("[VECTOR][utils.time_utils] suppressed Exception: %s", _sve)
    return ""


def _get_config_path():
    try:
        from pathlib import Path
        return Path.home() / ".vectorcode" / "config.yaml"
    except Exception:
        return None


def _get_zoneinfo(name: str) -> Optional["ZoneInfo"]:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except Exception as exc:
        logger.warning("Invalid timezone %r: %s. Falling back to server local time.", name, exc)
        return None


def get_timezone() -> Optional["ZoneInfo"]:
    global _cached_tz, _cache_resolved
    if not _cache_resolved:
        _cached_tz = _get_zoneinfo(_resolve_timezone_name())
        _cache_resolved = True
    return _cached_tz


def now() -> datetime:
    """Return current time as a timezone-aware datetime."""
    tz = get_timezone()
    if tz is not None:
        return datetime.now(tz)
    return datetime.now().astimezone()


def reset_cache() -> None:
    """Force re-resolution of timezone on next call."""
    global _cache_resolved
    _cache_resolved = False


def format_duration(seconds: float) -> str:
    """Format a duration in seconds as a human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs:.0f}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"


def parse_relative_time(text: str) -> Optional[datetime]:
    """Parse relative time strings like '5m', '2h', '1d' into a future datetime."""
    import re
    m = re.match(r'^(\d+)\s*([smhd])$', text.strip().lower())
    if not m:
        return None
    value, unit = int(m.group(1)), m.group(2)
    from datetime import timedelta
    delta = {"s": timedelta(seconds=value), "m": timedelta(minutes=value),
             "h": timedelta(hours=value), "d": timedelta(days=value)}[unit]
    return now() + delta


# Backwards-compat alias
VectorTime = now
VectorCodeTime = now
