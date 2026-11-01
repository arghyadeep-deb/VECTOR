"""Clean-room staged order lifecycle for VECTOR investment safety."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

__all__ = ["OrderState", "RiskSnapshot", "StagedOrder", "transition_order"]


class OrderState(str, Enum):
    DRAFT = "draft"
    STAGED = "staged"
    RISK_CHECKED = "risk_checked"
    APPROVED = "approved"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True)
class RiskSnapshot:
    cash: float = 0.0
    exposure: float = 0.0
    open_orders: int = 0
    daily_pnl: float = 0.0
    max_drawdown: float = 0.0
    account_profile: str = "paper"
    rule_decisions: tuple[str, ...] = ()


@dataclass
class StagedOrder:
    order_id: str
    symbol: str
    side: str
    quantity: float
    mode: str = "paper"
    state: OrderState = OrderState.DRAFT
    proposed_by: str = "vector"
    approved_by: str = ""
    risk_snapshot: RiskSnapshot = field(default_factory=RiskSnapshot)
    transitions: list[dict] = field(default_factory=list)

    def can_submit(self) -> bool:
        return self.mode == "paper" or self.state == OrderState.APPROVED


_ALLOWED: dict[OrderState, set[OrderState]] = {
    OrderState.DRAFT: {OrderState.STAGED, OrderState.CANCELLED},
    OrderState.STAGED: {OrderState.RISK_CHECKED, OrderState.REJECTED, OrderState.CANCELLED},
    OrderState.RISK_CHECKED: {OrderState.APPROVED, OrderState.REJECTED},
    OrderState.APPROVED: {OrderState.SUBMITTED, OrderState.CANCELLED},
    OrderState.SUBMITTED: {OrderState.ACCEPTED, OrderState.REJECTED, OrderState.FAILED},
    OrderState.ACCEPTED: {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCEL_REQUESTED, OrderState.FAILED},
    OrderState.PARTIALLY_FILLED: {OrderState.FILLED, OrderState.CANCEL_REQUESTED, OrderState.FAILED},
    OrderState.CANCEL_REQUESTED: {OrderState.CANCELLED, OrderState.FAILED},
}


def transition_order(order: StagedOrder, new_state: OrderState, reason: str, actor: str = "system") -> StagedOrder:
    allowed = _ALLOWED.get(order.state, set())
    if new_state not in allowed:
        raise ValueError(f"invalid order transition: {order.state.value} -> {new_state.value}")
    order.state = new_state
    order.transitions.append({
        "state": new_state.value,
        "reason": reason,
        "actor": actor,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if new_state == OrderState.APPROVED:
        order.approved_by = actor
    return order
