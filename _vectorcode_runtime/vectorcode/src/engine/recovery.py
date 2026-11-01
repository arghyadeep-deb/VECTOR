# Ported from GitHub/VectorCode_vectorcode/repo/run_agent.py
"""Error recovery with credential pool rotation."""
from typing import Any, Optional, TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from .agent import AIAgent


async def recover_on_error(agent: "AIAgent", error: Exception) -> Optional[Any]:
    """Try to recover from a provider error via credential rotation.

    Returns a new response if recovery succeeded, None if not.
    """
    error_str = str(error).lower()
    is_rate_limit = any(x in error_str for x in ("429", "rate limit", "quota", "too many"))
    is_auth = any(x in error_str for x in ("401", "403", "unauthorized", "forbidden", "invalid api key"))

    if not (is_rate_limit or is_auth):
        return None

    pool = agent.credential_pool
    if pool is None:
        logger.warning("No credential pool — cannot rotate on error")
        return None

    if not hasattr(pool, "rotate"):
        return None

    logger.info(f"Rotating credentials after error: {error_str[:80]}")
    try:
        pool.rotate()
        from .conversation import _call_model
        return await _call_model(agent)
    except Exception as e2:
        logger.error(f"Recovery attempt failed: {e2}")
        return None
