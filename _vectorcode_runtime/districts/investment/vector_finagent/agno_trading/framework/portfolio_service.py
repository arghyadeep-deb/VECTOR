"""
In-memory portfolio service for tracking trading state.
"""

import math
import time
from collections import deque
from typing import Dict
from .base_portfolio import BasePortfolioService
from .types import TxResult, PortfolioView, PositionSnapshot, Side, TxStatus


class InMemoryPortfolioService(BasePortfolioService):
    """
    In-memory portfolio service.

    Tracks:
    - Cash balance
    - Open positions (long/short)
    - Realized P&L (from closed trades)
    - Unrealized P&L (mark-to-market)
    """

    def __init__(self, initial_capital: float = 10000.0):
        """
        Initialize portfolio.

        Args:
            initial_capital: Starting cash balance
        """
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, PositionSnapshot] = {}
        self.total_realized_pnl = 0.0
        self.trades_count = 0
        self.winning_trades = 0
        self._equity_history: deque[float] = deque(maxlen=1000)

    async def apply_trade(self, tx: TxResult) -> None:
        """
        Apply a completed trade to the portfolio.

        Logic:
        - BUY: Deduct cash, increase/open long position
        - SELL: Add cash, reduce/close long or open short position
        """
        if tx.status != TxStatus.FILLED:
            return

        inst = tx.instruction
        symbol = inst.symbol
        side = inst.side
        quantity = tx.fill_quantity or 0.0
        price = tx.fill_price or 0.0
        fee = tx.fee

        # Update trade count
        self.trades_count += 1

        # Handle BUY
        if side == Side.BUY:
            cost = (quantity * price) + fee
            self.cash -= cost

            # Update or create position
            if symbol in self.positions:
                pos = self.positions[symbol]
                total_qty = pos.quantity + quantity
                total_cost = (pos.quantity * pos.avg_entry_price) + (quantity * price)
                new_avg_price = total_cost / total_qty if total_qty > 0 else price

                self.positions[symbol] = PositionSnapshot(
                    symbol=symbol,
                    quantity=total_qty,
                    avg_entry_price=new_avg_price,
                    current_price=price,
                    unrealized_pnl=0.0,  # Will be updated in mark_to_market
                    leverage=inst.leverage,
                    side=Side.BUY
                )
            else:
                self.positions[symbol] = PositionSnapshot(
                    symbol=symbol,
                    quantity=quantity,
                    avg_entry_price=price,
                    current_price=price,
                    unrealized_pnl=0.0,
                    leverage=inst.leverage,
                    side=Side.BUY
                )

        # Handle SELL
        elif side == Side.SELL:
            proceeds = (quantity * price) - fee
            self.cash += proceeds

            if symbol in self.positions:
                pos = self.positions[symbol]

                if pos.quantity >= quantity:
                    # Partial or full close of long position
                    realized_pnl = (price - pos.avg_entry_price) * quantity
                    self.total_realized_pnl += realized_pnl
                    if realized_pnl > 0:
                        self.winning_trades += 1

                    remaining_qty = pos.quantity - quantity
                    if remaining_qty > 0.01:  # Keep position open
                        self.positions[symbol] = PositionSnapshot(
                            symbol=symbol,
                            quantity=remaining_qty,
                            avg_entry_price=pos.avg_entry_price,
                            current_price=price,
                            unrealized_pnl=0.0,
                            leverage=pos.leverage,
                            side=Side.BUY
                        )
                    else:
                        # Close position completely
                        del self.positions[symbol]
                else:
                    # Short position (sell more than we have)
                    # First close existing long, then open short
                    realized_pnl = (price - pos.avg_entry_price) * pos.quantity
                    self.total_realized_pnl += realized_pnl

                    short_qty = quantity - pos.quantity
                    # For short, we need margin (assume 50% margin requirement)
                    margin_required = (short_qty * price) * 0.5
                    self.cash -= margin_required

                    self.positions[symbol] = PositionSnapshot(
                        symbol=symbol,
                        quantity=-short_qty,  # Negative for short
                        avg_entry_price=price,
                        current_price=price,
                        unrealized_pnl=0.0,
                        leverage=inst.leverage,
                        side=Side.SELL
                    )
            else:
                # Opening short position directly
                margin_required = (quantity * price) * 0.5
                self.cash -= margin_required

                self.positions[symbol] = PositionSnapshot(
                    symbol=symbol,
                    quantity=-quantity,
                    avg_entry_price=price,
                    current_price=price,
                    unrealized_pnl=0.0,
                    leverage=inst.leverage,
                    side=Side.SELL
                )

    async def mark_to_market(self, prices: Dict[str, float]) -> None:
        """
        Update unrealized P&L based on current market prices.
        """
        for symbol, pos in self.positions.items():
            if symbol in prices:
                current_price = prices[symbol]
                pos.current_price = current_price

                if pos.quantity > 0:
                    # Long position
                    pos.unrealized_pnl = (current_price - pos.avg_entry_price) * pos.quantity
                else:
                    # Short position
                    pos.unrealized_pnl = (pos.avg_entry_price - current_price) * abs(pos.quantity)

        # Snapshot equity for performance stats
        long_val = sum(p.quantity * p.current_price for p in self.positions.values() if p.quantity > 0)
        short_unr = sum(p.unrealized_pnl for p in self.positions.values() if p.quantity < 0)
        self._equity_history.append(self.cash + long_val + short_unr)

    async def get_portfolio_view(self) -> PortfolioView:
        """
        Get current portfolio snapshot.

        Total portfolio value = Cash + Position Values (at current market prices)

        For long positions: position_value = quantity * current_price
        For short positions: position_value = margin_held + unrealized_pnl
            (margin is already deducted from cash when opening short)
        """
        total_unrealized_pnl = sum(pos.unrealized_pnl for pos in self.positions.values())

        # Calculate exposures
        gross_exposure = 0.0
        net_exposure = 0.0

        for pos in self.positions.values():
            notional = abs(pos.quantity) * pos.current_price
            gross_exposure += notional

            if pos.quantity > 0:
                # Long position: positive exposure
                net_exposure += notional
            else:
                # Short position: negative exposure
                net_exposure -= notional

        # Total value = Cash + Long Position Values + Unrealized P&L from shorts
        # For longs: unrealized_pnl is already embedded in (current_price - entry_price) * qty
        # So we use: Cash + Long Positions Market Value + Short Unrealized P&L
        # Simplified: Cash + Gross Long Exposure + Total Unrealized P&L (which includes both)

        # More accurate calculation:
        # - Cash includes proceeds/margin from trades
        # - Long positions: add current market value
        # - Short positions: margin is in cash, add/subtract unrealized P&L

        # Calculate long positions value at cost basis + unrealized gain/loss
        long_positions_value = sum(
            pos.quantity * pos.current_price
            for pos in self.positions.values()
            if pos.quantity > 0
        )

        # Short positions: only unrealized P&L affects value (margin already in cash)
        short_unrealized_pnl = sum(
            pos.unrealized_pnl
            for pos in self.positions.values()
            if pos.quantity < 0
        )

        # Total portfolio value
        total_value = self.cash + long_positions_value + short_unrealized_pnl

        return PortfolioView(
            cash=self.cash,
            positions=self.positions.copy(),
            total_value=total_value,
            total_unrealized_pnl=total_unrealized_pnl,
            total_realized_pnl=self.total_realized_pnl,
            gross_exposure=gross_exposure,
            net_exposure=net_exposure,
            trades_count=self.trades_count
        )

    def get_performance_stats(self) -> dict:
        """Compute win_rate, sharpe_ratio, max_drawdown from in-memory history."""
        win_rate = (self.winning_trades / self.trades_count * 100) if self.trades_count > 0 else 0.0

        history = list(self._equity_history)
        max_drawdown = 0.0
        sharpe_ratio = 0.0
        if len(history) >= 2:
            # Max drawdown
            peak = history[0]
            for v in history:
                peak = max(peak, v)
                dd = (peak - v) / peak if peak > 0 else 0.0
                max_drawdown = max(max_drawdown, dd)
            # Annualised Sharpe (daily returns, 252 trading days)
            returns = [(history[i] - history[i - 1]) / history[i - 1]
                       for i in range(1, len(history)) if history[i - 1] > 0]
            if len(returns) >= 2:
                avg = sum(returns) / len(returns)
                variance = sum((r - avg) ** 2 for r in returns) / len(returns)
                std = math.sqrt(variance)
                sharpe_ratio = (avg / std * math.sqrt(252)) if std > 0 else 0.0

        return {"win_rate": win_rate, "sharpe_ratio": sharpe_ratio, "max_drawdown": max_drawdown}

    async def reset(self, initial_capital: float) -> None:
        """
        Reset portfolio to initial state.
        """
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}
        self.total_realized_pnl = 0.0
        self.trades_count = 0
