"""
Sticker description cache for Telegram.

When users send stickers, we describe them via the vision tool and cache
the descriptions keyed by file_unique_id so we don't re-analyze the same
sticker image on every send. Descriptions are concise (1-2 sentences).

Cache location: ~/.vectorcode/sticker_cache.json
"""

import json
import os
import tempfile
import time
from typing import Optional

from loguru import logger

from vector_cli.config import get_vector_home


CACHE_PATH = get_vector_home() / "sticker_cache.json"

# Vision prompt for describing stickers -- kept concise to save tokens
STICKER_VISION_PROMPT = (
    "Describe this sticker in 1-2 sentences. Focus on what it depicts -- "
    "character, action, emotion. Be concise and objective."
)


def _load_cache() -> dict:
    """Load the sticker cache from disk.

    Unlike the vault/webhook stores, this is a cheaply-regenerable
    performance cache (sticker descriptions are re-derived from a vision
    call on a miss), and its only caller (telegram.py's sticker handler)
    does not wrap the lookup in a try/except -- letting a corrupt-file
    exception propagate would crash sticker handling entirely instead of
    just costing one extra vision call. Fail open, but log loudly so
    silent corruption is still visible.
    """
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("[VECTOR][gateway.sticker_cache] Cache file unreadable, treating as empty: {}", e)
            return {}
    return {}


def _save_cache(cache: dict) -> bool:
    """Best-effort, atomic save for the cheaply-regenerable cache."""
    tmp_path: Optional[str] = None
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(CACHE_PATH.parent),
            prefix=f".{CACHE_PATH.name}.",
            suffix=".tmp",
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, CACHE_PATH)
        return True
    except OSError as exc:
        logger.warning(
            "[VECTOR][gateway.sticker_cache] Cache write failed; continuing without persistence: {}",
            exc,
        )
        return False
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                logger.debug(
                    "[VECTOR][gateway.sticker_cache] Could not remove temporary cache file {}: {}",
                    tmp_path,
                    exc,
                )


def get_cached_description(file_unique_id: str) -> Optional[dict]:
    """
    Look up a cached sticker description.

    Returns:
        dict with keys {description, emoji, set_name, cached_at} or None.
    """
    cache = _load_cache()
    return cache.get(file_unique_id)


def cache_sticker_description(
    file_unique_id: str,
    description: str,
    emoji: str = "",
    set_name: str = "",
) -> None:
    """
    Store a sticker description in the cache.

    Args:
        file_unique_id: Telegram's stable sticker identifier.
        description:    Vision-generated description text.
        emoji:          Associated emoji (e.g. "😀").
        set_name:       Sticker set name if available.
    """
    cache = _load_cache()
    cache[file_unique_id] = {
        "description": description,
        "emoji": emoji,
        "set_name": set_name,
        "cached_at": time.time(),
    }
    _save_cache(cache)


def build_sticker_injection(
    description: str,
    emoji: str = "",
    set_name: str = "",
) -> str:
    """
    Build the warm-style injection text for a sticker description.

    Returns a string like:
      [The user sent a sticker 😀 from "MyPack"~ It shows: "A cat waving" (=^.w.^=)]
    """
    context = ""
    if set_name and emoji:
        context = f" {emoji} from \"{set_name}\""
    elif emoji:
        context = f" {emoji}"

    return f"[The user sent a sticker{context}~ It shows: \"{description}\" (=^.w.^=)]"


def build_animated_sticker_injection(emoji: str = "") -> str:
    """
    Build injection text for animated/video stickers we can't analyze.
    """
    if emoji:
        return (
            f"[The user sent an animated sticker {emoji}~ "
            f"I can't see animated ones yet, but the emoji suggests: {emoji}]"
        )
    return "[The user sent an animated sticker~ I can't see animated ones yet]"
