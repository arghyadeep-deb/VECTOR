# Ported from GitHub/VectorCode_vectorcode/repo/utils.py
"""Core utility functions for VectorCode."""
from loguru import logger
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Optional, Union
from urllib.parse import urlparse


TRUTHY_STRINGS = frozenset({"1", "true", "yes", "on"})


def is_truthy_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY_STRINGS
    return bool(value)


def env_var_enabled(name: str, default: str = "") -> bool:
    """Return True when an environment variable is set to a truthy value."""
    return is_truthy_value(os.environ.get(name, default), default=False)


def env_int(key: str, default: int = 0) -> int:
    raw = os.environ.get(key, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def safe_json_loads(text: str, default: Any = None) -> Any:
    """Parse JSON, returning default on any parse error."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


def _preserve_file_mode(path: Path) -> Optional[int]:
    try:
        return stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    except OSError:
        return None


def _restore_file_mode(path: Path, mode: Optional[int]) -> None:
    if mode is None:
        return
    try:
        os.chmod(path, mode)
    except OSError as _sve:
        logger.warning("[VECTOR][utils.core] suppressed OSError: %s", _sve)


def atomic_json_write(
    path: Union[str, Path],
    data: Any,
    *,
    indent: int = 2,
    **dump_kwargs: Any,
) -> None:
    """Write JSON data to a file atomically (temp + fsync + os.replace)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    original_mode = _preserve_file_mode(path)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.stem}_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False, **dump_kwargs)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        _restore_file_mode(path, original_mode)
    except BaseException as _sve:
        try:
            os.unlink(tmp_path)
        except OSError as _sve:
            logger.warning("[VECTOR][utils.core] suppressed OSError: %s", _sve)
        raise


def normalize_proxy_url(proxy_url: Optional[str]) -> Optional[str]:
    """Normalize proxy URLs (socks:// → socks5://)."""
    candidate = str(proxy_url or "").strip()
    if not candidate:
        return None
    if candidate.lower().startswith("socks://"):
        return f"socks5://{candidate[len('socks://'):]}"
    return candidate


def base_url_hostname(base_url: str) -> str:
    """Return the lowercased hostname for a base URL."""
    raw = (base_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    return (parsed.hostname or "").lower().rstrip(".")


def base_url_host_matches(base_url: str, domain: str) -> bool:
    """Return True when the base URL's hostname is domain or a subdomain."""
    hostname = base_url_hostname(base_url)
    if not hostname:
        return False
    domain = (domain or "").strip().lower().rstrip(".")
    if not domain:
        return False
    return hostname == domain or hostname.endswith("." + domain)
