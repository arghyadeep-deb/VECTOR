"""Shared investment execution safety gates.

This module is intentionally small and dependency-light so CLI bridges and
async agents can all use the same production safety contract.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from core.config import CONFIG
from core.loop.permission_gateway import Action, PermissionGateway
from loguru import logger

_SENSITIVE_KEYS = {
    "api_key",
    "api_secret",
    "api_passphrase",
    "secret",
    "private_key",
    "private_key_pem",
    "solana_private_key",
    "token",
}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if k.lower() in _SENSITIVE_KEYS else _redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def investment_config() -> dict:
    cfg = CONFIG.get("investment", {}) if isinstance(CONFIG, dict) else {}
    return cfg if isinstance(cfg, dict) else {}


async def approve_live_trade(
    *,
    platform: str,
    operation: str,
    details: dict,
    proposed_by: str = "investment",
) -> dict:
    """Return a normalized decision for an investment execution attempt.

    Returns:
      - status=paper when global paper mode is enabled.
      - status=blocked when kill switch/gateway denies execution.
      - status=approved only after explicit RED-tier owner approval.
    """

    cfg = investment_config()
    if cfg.get("kill_switch", False):
        return {"status": "blocked", "approved": False, "reason": "kill_switch_active"}

    if cfg.get("paper_trading", True):
        return {
            "status": "paper",
            "approved": False,
            "simulated": True,
            "reason": "investment.paper_trading=True",
        }

    action = Action(
        action_type="financial_transaction",
        params={
            "platform": platform,
            "operation": operation,
            "details": _redact(details),
        },
        proposed_by=proposed_by,
        priority="critical",
    )

    gateway = PermissionGateway()
    result = await gateway.execute(action)
    if not result.approved:
        logger.warning(
            "[VECTOR][investment] live {} {} blocked by gateway: {}",
            platform,
            operation,
            result.reason,
        )
        return {
            "status": "blocked",
            "approved": False,
            "reason": result.reason,
            "tier": result.level,
        }

    return {
        "status": "approved",
        "approved": True,
        "reason": result.reason,
        "tier": result.level,
    }


def approve_live_trade_sync(**kwargs) -> dict:
    """Synchronous wrapper for CLI bridge scripts."""

    async def _run() -> dict:
        return await approve_live_trade(**kwargs)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_run())

    box: dict[str, Any] = {}

    def _thread_main() -> None:
        try:
            box["result"] = asyncio.run(_run())
        except Exception as exc:  # pragma: no cover - defensive bridge path
            box["error"] = exc

    thread = threading.Thread(target=_thread_main, daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["result"]
