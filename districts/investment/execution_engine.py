"""
VECTOR Investment Execution Engine — paper-first, gateway-gated real trading.

SAFETY RULES (all must pass before any real order):
1. paper_trading=True by default — flip to False only when ready for live
2. kill_switch check — instantly halts ALL execution if True
3. Permission gateway RED tier — every real order needs owner confirmation
4. Position size cap — max single order value
5. Daily loss cap — total loss limit resets midnight
6. Max trades/day — hard limit on order count
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import asyncio
import sqlite3
from datetime import datetime, timezone, date
from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


EXECUTION_DB = Path(__file__).parent.parent.parent / "data" / "execution_ledger.db"


def _init_ledger():
    EXECUTION_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(EXECUTION_DB))
    conn.execute("""CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        symbol TEXT, side TEXT, quantity REAL, order_type TEXT,
        price REAL, status TEXT, paper INTEGER DEFAULT 1,
        timestamp TEXT, reason TEXT, broker TEXT
    )""")
    conn.commit()
    conn.close()


class ExecutionEngine(AgentBase):
    """
    Paper-first order execution engine with full safety stack.
    Set CONFIG["investment"]["paper_trading"] = False to enable live trading.
    """

    def __init__(self):
        super().__init__("execution_engine_001", "ExecutionEngine", "investment")
        _init_ledger()
        self._today_trades = 0
        self._today_loss = 0.0
        self._today_date = date.today()
        logger.info("[VECTOR][execution] ExecutionEngine initialized — paper_trading={}",
                    CONFIG.get("investment", {}).get("paper_trading", True))

    def _reset_daily_counters(self):
        if date.today() != self._today_date:
            self._today_trades = 0
            self._today_loss = 0.0
            self._today_date = date.today()

    def _get_inv_cfg(self) -> dict:
        return CONFIG.get("investment", {})

    def _check_guardrails(self, symbol: str, quantity: float, price: float) -> tuple[bool, str]:
        """Run all safety checks. Returns (ok, reason)."""
        cfg = self._get_inv_cfg()
        self._reset_daily_counters()

        # Kill switch
        if cfg.get("kill_switch", False):
            return False, "KILL SWITCH ACTIVE"

        # Daily trade limit
        max_trades = cfg.get("max_trades_per_day", 10)
        if self._today_trades >= max_trades:
            return False, f"Max trades/day reached ({max_trades})"

        # Position size cap
        order_value = quantity * (price or 1.0)
        max_pos = cfg.get("max_position_size", 10000)
        if order_value > max_pos:
            return False, f"Order value ₹{order_value:.0f} exceeds max_position_size ₹{max_pos}"

        # Daily loss cap
        daily_cap = cfg.get("daily_loss_cap", 5000)
        if self._today_loss >= daily_cap:
            return False, f"Daily loss cap ₹{daily_cap} reached"

        return True, "ok"

    def _log_order(self, order_id: str, symbol: str, side: str, quantity: float,
                   price: float, status: str, paper: bool, reason: str = ""):
        try:
            conn = sqlite3.connect(str(EXECUTION_DB))
            conn.execute(
                "INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (order_id, symbol, side, quantity, "market", price, status,
                 1 if paper else 0, datetime.now(timezone.utc).isoformat(), reason, "VECTOR")
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("[VECTOR][execution] ledger write failed: {}", e)

    def get_order_history(self, limit: int = 50) -> list[dict]:
        """Return the most recent orders from the audit ledger."""
        try:
            conn = sqlite3.connect(str(EXECUTION_DB))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM orders ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error("[VECTOR][execution] ledger read failed: {}", e)
            return []

    async def place_order(self, symbol: str, side: str, quantity: float,
                          price: float = 0.0, order_type: str = "market") -> dict:
        """
        Place an order. Paper mode by default. Requires gateway RED for real.

        side: 'BUY' | 'SELL' | 'SHORT' | 'COVER'
        """
        import uuid
        order_id = str(uuid.uuid4())[:8]
        cfg = self._get_inv_cfg()
        paper = cfg.get("paper_trading", True)

        # Guardrail checks
        ok, reason = self._check_guardrails(symbol, quantity, price)
        if not ok:
            logger.warning("[VECTOR][execution] Order BLOCKED: {}", reason)
            self._log_order(order_id, symbol, side, quantity, price, "blocked", paper, reason)
            self.deduct_points(2, "order_blocked")
            return {"status": "blocked", "reason": reason, "order_id": order_id}

        # Paper mode
        if paper:
            logger.info("[VECTOR][execution] PAPER ORDER: {} {} {} @ ₹{}", side, quantity, symbol, price)
            self._today_trades += 1
            self._log_order(order_id, symbol, side, quantity, price, "paper_filled", True, "paper_mode")
            self.award_points(3, "paper_order")
            return {
                "status": "paper_filled",
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "paper": True,
                "message": "PAPER MODE — set paper_trading=False for live",
            }

        # Live execution — requires RED tier gateway approval
        try:
            from core.loop.permission_gateway import PermissionGateway, Action
            gw = PermissionGateway()
            action = Action(
                action_type="execute_trade",
                params={"symbol": symbol, "side": side, "quantity": quantity, "price": price},
                proposed_by=self.name,
            )
            result = await gw.execute(action)
            if not result.approved:
                reason = f"Gateway rejected: {result.reason}"
                self._log_order(order_id, symbol, side, quantity, price, "gateway_rejected", False, reason)
                return {"status": "rejected", "reason": reason, "order_id": order_id}
        except Exception as e:
            logger.error("[VECTOR][execution] Gateway error: {}", e)
            self._log_order(order_id, symbol, side, quantity, price, "error", False, str(e))
            return {"status": "error", "error": str(e), "order_id": order_id}

        # Execute via broker (Zerodha Kite as primary target)
        try:
            exec_result = await self._execute_via_broker(symbol, side, quantity, order_type, price)
            self._today_trades += 1
            self._log_order(order_id, symbol, side, quantity, price, "filled", False)
            self.award_points(15, f"live_order_{symbol}")
            return {**exec_result, "order_id": order_id, "paper": False}
        except Exception as e:
            logger.error("[VECTOR][execution] Broker execution failed: {}", e)
            self._log_order(order_id, symbol, side, quantity, price, "error", False, str(e))
            self.deduct_points(10, "execution_failed")
            return {"status": "error", "error": str(e), "order_id": order_id}

    async def _execute_via_broker(self, symbol: str, side: str, quantity: float,
                                   order_type: str, price: float) -> dict:
        """Execute via configured broker. Currently supports Zerodha Kite."""
        import os
        kite_api_key = os.getenv("ZERODHA_API_KEY")
        if kite_api_key:
            return await self._execute_zerodha(symbol, side, quantity, order_type, price)
        raise NotImplementedError("No broker configured. Set ZERODHA_API_KEY to enable live trading.")

    async def _execute_zerodha(self, symbol: str, side: str, quantity: float,
                                order_type: str, price: float) -> dict:
        """Execute via Zerodha Kite Connect API."""
        try:
            from kiteconnect import KiteConnect
            import os
            kite = KiteConnect(api_key=os.getenv("ZERODHA_API_KEY"))
            kite.set_access_token(os.getenv("ZERODHA_ACCESS_TOKEN", ""))
            transaction = (
                kite.ORDER_TRANSACTION_TYPE_BUY
                if side == "BUY"
                else kite.ORDER_TRANSACTION_TYPE_SELL
            )
            broker_order_id = kite.place_order(
                tradingsymbol=symbol,
                exchange=kite.EXCHANGE_NSE,
                transaction_type=transaction,
                quantity=int(quantity),
                product=kite.PRODUCT_CNC,
                order_type=(
                    kite.ORDER_TYPE_MARKET
                    if order_type == "market"
                    else kite.ORDER_TYPE_LIMIT
                ),
                price=price if order_type == "limit" else None,
                variety=kite.VARIETY_REGULAR,
            )
            return {"status": "filled", "broker_order_id": broker_order_id, "broker": "zerodha"}
        except ImportError:
            raise ImportError("kiteconnect not installed: pip install kiteconnect")

    def get_today_summary(self) -> dict:
        self._reset_daily_counters()
        return {
            "trades_today": self._today_trades,
            "loss_today": self._today_loss,
            "paper_mode": self._get_inv_cfg().get("paper_trading", True),
            "kill_switch": self._get_inv_cfg().get("kill_switch", False),
        }

    async def run(self, params: dict = None) -> dict:
        p = params or {}
        task = p.get("type", "summary")
        if task == "place_order":
            return await self.place_order(
                symbol=p.get("symbol", ""),
                side=p.get("side", "BUY"),
                quantity=p.get("quantity", 1),
                price=p.get("price", 0.0),
            )
        if task == "order_history":
            return {"status": "ok", "orders": self.get_order_history(p.get("limit", 50))}
        return self.get_today_summary()


if __name__ == "__main__":
    e = ExecutionEngine()
    print("✅ ExecutionEngine OK — paper_trading:", e._get_inv_cfg().get("paper_trading", True))
