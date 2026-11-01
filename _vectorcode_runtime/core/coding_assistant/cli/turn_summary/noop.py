from __future__ import annotations

from collections.abc import Callable

from core.coding_assistant.cli.turn_summary.port import TurnSummaryPort, TurnSummaryResult
from core.coding_assistant.core.types import BaseEvent


class NoopTurnSummary(TurnSummaryPort):
    @property
    def generation(self) -> int:
        return 0

    @property
    def on_summary(self) -> Callable[[TurnSummaryResult], None] | None:
        return None

    @on_summary.setter
    def on_summary(self, value: Callable[[TurnSummaryResult], None] | None) -> None:
        return None

    def start_turn(self, user_message: str) -> None:
        return None

    def track(self, event: BaseEvent) -> None:
        return None

    def set_error(self, message: str) -> None:
        return None

    def cancel_turn(self) -> None:
        return None

    def end_turn(self) -> Callable[[], bool] | None:
        return None

    async def close(self) -> None:
        return None
