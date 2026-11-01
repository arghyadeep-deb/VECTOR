"""Metering router — /metering/status."""

import sys

__all__ = [
    "metering_status",
    "router",
]

import json

from fastapi import APIRouter
from loguru import logger
from pathlib import Path

router = APIRouter(prefix="/metering", tags=["metering"])

@router.get("/status")
async def metering_status():
    """Get budget usage stats."""
    try:
        budgets_path = Path.home() / ".vector_ca" / "metering" / "budgets.json"
        if not budgets_path.exists():
            return {"total_spent": 0.0, "budget_limit": 0.0, "usage_pct": 0.0, "period": "unknown"}
        data = json.loads(budgets_path.read_text(encoding="utf-8"))
        total_spent = float(data.get("total_spent", 0))
        budget_limit = float(data.get("budget_limit", 0))
        usage_pct = (total_spent / budget_limit * 100) if budget_limit > 0 else 0.0
        return {
            "total_spent": total_spent,
            "budget_limit": budget_limit,
            "usage_pct": round(usage_pct, 2),
            "period": data.get("period", "unknown"),
        }
    except Exception as e:
        logger.warning(f"[VECTOR][api][metering] status failed: {e}")
        return {"total_spent": 0.0, "budget_limit": 0.0, "usage_pct": 0.0, "period": "unknown"}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ metering.py OK")
