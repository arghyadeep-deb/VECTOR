"""Mining router — /mining/status."""

import sys

__all__ = [
    "mining_status",
    "router",
]

import httpx

from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/mining", tags=["mining"])

@router.get("/status")
async def mining_status():
    """Get mining/Pearl gateway metrics from Prometheus endpoint."""
    running = False
    shares_submitted = 0
    shares_accepted = 0
    blocks_found = 0
    errors = 0
    try:
        from core.mining._metrics import (
            parse_gateway_metrics,
            PROM_SHARES_SUBMITTED,
            PROM_SHARES_ACCEPTED,
            PROM_BLOCKS_FOUND,
            PROM_ERRORS_TOTAL,
        )
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://127.0.0.1:8000/metrics")
            if resp.status_code == 200:
                stats = parse_gateway_metrics(resp.text, provider_id="pearl")
                shares_submitted = stats.shares_submitted
                shares_accepted = stats.shares_accepted
                blocks_found = stats.blocks_found
                errors = int(getattr(stats, "last_error", "0").split()[0]) if stats.last_error else 0
                running = stats.uptime_seconds > 0
    except Exception as e:
        logger.warning(f"[VECTOR][api][mining] status failed: {e}")

    return {
        "shares_submitted": shares_submitted,
        "shares_accepted": shares_accepted,
        "blocks_found": blocks_found,
        "errors": errors,
        "running": running,
    }

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ mining.py OK")
