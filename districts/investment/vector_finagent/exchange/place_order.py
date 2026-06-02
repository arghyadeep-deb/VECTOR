"""
from loguru import logger
Place an order on an exchange (requires API credentials via stdin).

Usage: echo '{"api_key":"...","secret":"..."}' | python place_order.py <exchange_id> <symbol> <side> <type> <amount> [price]
Example:
  Market buy:  echo '{"api_key":"...","secret":"..."}' | python place_order.py binance BTC/USDT buy market 0.001
  Limit sell:  echo '{"api_key":"...","secret":"..."}' | python place_order.py binance BTC/USDT sell limit 0.001 75000

Output JSON:
{
  "success": true,
  "data": {
    "id": "12345678",
    "symbol": "BTC/USDT",
    "side": "buy",
    "type": "market",
    "amount": 0.001,
    "price": null,
    "status": "open",
    "filled": 0.0,
    "remaining": 0.001,
    "cost": 0.0,
    "average": null,
    "timestamp": 1773466621013,
    "exchange": "binance"
  }
}
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
from loguru import logger
from exchange_client import (
    make_exchange, output_success, output_error,
    parse_credentials_from_stdin, run_with_error_handling,
    load_cached_markets, save_markets_cache,
)


@run_with_error_handling
def main():
    if len(sys.argv) < 6:
        output_error(
            "Usage: place_order.py <exchange_id> <symbol> <side> <type> <amount> [price]",
            "INVALID_ARGS",
        )

    exchange_id = sys.argv[1]
    symbol = sys.argv[2]
    side = sys.argv[3]        # buy or sell
    order_type = sys.argv[4]  # market or limit
    amount = float(sys.argv[5])
    price = float(sys.argv[6]) if len(sys.argv) > 6 else None

    if side not in ("buy", "sell"):
        output_error(f"Invalid side: {side}. Must be 'buy' or 'sell'.", "INVALID_ARGS")
    if order_type not in ("market", "limit"):
        output_error(f"Invalid type: {order_type}. Must be 'market' or 'limit'.", "INVALID_ARGS")
    if order_type == "limit" and price is None:
        output_error("Limit orders require a price.", "INVALID_ARGS")
    if amount <= 0:
        output_error("Amount must be positive.", "INVALID_ARGS")

    # SAFETY: Gate all execution through permission_gateway RED tier
    try:
        from core.loop.permission_gateway import PermissionGateway
        from core.config import CONFIG
        gw = PermissionGateway()
        action_str = f"execute_trade:{symbol}:{side}:{amount}"
        classification = gw.classify(action_str)
        if classification not in ("GREEN",):
            logger.warning(
                "[VECTOR][investment] Trade blocked — tier: {} action: {}",
                classification, action_str,
            )
            output_error(
                f"Trade blocked by permission_gateway (tier={classification}). "
                "Requires human approval.",
                "GATEWAY_BLOCKED",
            )

        # Paper mode check (default: True — safe)
        inv_cfg = CONFIG.get("investment", {}) if isinstance(CONFIG, dict) else {}
        if inv_cfg.get("paper_trading", True):
            logger.info(
                "[VECTOR][investment] PAPER MODE — would execute: {} {} {} {}",
                side, amount, symbol, order_type,
            )
            output_success({
                "status": "paper",
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "order_type": order_type,
                "price": price,
                "exchange": exchange_id,
                "simulated": True,
            })

        # Kill switch check
        if inv_cfg.get("kill_switch", False):
            logger.warning("[VECTOR][investment] KILL SWITCH ACTIVE — trade blocked")
            output_error("Kill switch is active. All live trading halted.", "KILL_SWITCH")
    except (ImportError, Exception) as _gw_err:
        logger.warning("[VECTOR][investment] Gateway check failed ({}); blocking trade for safety", _gw_err)
        output_error(
            f"Permission gateway unavailable ({_gw_err}). Trade blocked for safety.",
            "GATEWAY_ERROR",
        )

    credentials = parse_credentials_from_stdin()
    if not credentials.get("api_key"):
        output_error("API key required. Pass credentials via stdin JSON.", "AUTH_ERROR")

    exchange = make_exchange(exchange_id, credentials)

    # Use disk-cached markets (TTL 30min) to skip 3-10s load_markets() network call.
    # Use set_markets() so ccxt rebuilds all internal indexes correctly.
    cached = load_cached_markets(exchange_id)
    if cached is not None:
        try:
            exchange.set_markets(cached)
        except Exception:
            logger.debug("[VECTOR][exchange.place_order] caught Exception: %s", _sve)
            logger.debug("[VECTOR][exchange.place_order] caught Exception: %s", _sve)
            exchange.load_markets()
            save_markets_cache(exchange_id, exchange.markets)
    else:
        exchange.load_markets()
        save_markets_cache(exchange_id, exchange.markets)

    order = exchange.create_order(symbol, order_type, side, amount, price)

    output_success({
        "id": order.get("id"),
        "client_order_id": order.get("clientOrderId"),
        "symbol": order.get("symbol"),
        "side": order.get("side"),
        "type": order.get("type"),
        "amount": order.get("amount"),
        "price": order.get("price"),
        "status": order.get("status"),
        "filled": order.get("filled"),
        "remaining": order.get("remaining"),
        "cost": order.get("cost"),
        "average": order.get("average"),
        "fee": order.get("fee"),
        "timestamp": order.get("timestamp"),
        "exchange": exchange_id,
    })


if __name__ == "__main__":
    main()
