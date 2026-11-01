"""Market hours utilities — check if a market is open right now."""
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from datetime import datetime, time
from zoneinfo import ZoneInfo
from loguru import logger


def is_market_open(market_type: str = "us-stock") -> bool:
    """
    Check if the given market is currently open.
    market_type: 'us-stock' | 'crypto' | 'india-stock'
    """
    if market_type == "crypto":
        return True  # Crypto trades 24/7

    now_utc = datetime.now(ZoneInfo("UTC"))

    if market_type == "us-stock":
        now_et = now_utc.astimezone(ZoneInfo("America/New_York"))
        # NYSE/NASDAQ: Mon-Fri, 9:30-16:00 ET
        if now_et.weekday() >= 5:  # Saturday or Sunday
            return False
        market_open = time(9, 30)
        market_close = time(16, 0)
        return market_open <= now_et.time() < market_close

    if market_type == "india-stock":
        now_ist = now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
        # NSE/BSE: Mon-Fri, 9:15-15:30 IST
        if now_ist.weekday() >= 5:
            return False
        market_open = time(9, 15)
        market_close = time(15, 30)
        return market_open <= now_ist.time() < market_close

    logger.warning("[VECTOR][market_hours] Unknown market type: {}", market_type)
    return False


def get_market_status(market_type: str = "us-stock") -> dict:
    """Return market status with next open/close time."""
    open_ = is_market_open(market_type)
    return {
        "market": market_type,
        "is_open": open_,
        "status": "OPEN" if open_ else "CLOSED",
        "checked_at": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    for m in ["us-stock", "crypto", "india-stock"]:
        print(f"{m}: {get_market_status(m)}")
    print("✅ market_hours OK")
