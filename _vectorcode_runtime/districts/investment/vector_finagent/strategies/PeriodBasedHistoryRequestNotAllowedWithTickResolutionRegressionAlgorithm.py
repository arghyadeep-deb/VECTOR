# ============================================================================
# VECTOR Financial Terminal - Strategy Engine
# Derived from Fincept Terminal (Fincept Corporation) -- see THIRD_PARTY_NOTICES.md.
# Adapted for VECTOR (owner's personal-use build).
#
# Strategy ID: FCT-B9E58D2A
# Category: Regression Test
# Description: Regression algorithm for testing that period-based history requests are not allowed with tick resolution
# Compatibility: Backtesting | Paper Trading | Live Deployment
# ============================================================================
from loguru import logger
from AlgorithmImports import *

### <summary>
### Regression algorithm for testing that period-based history requests are not allowed with tick resolution
### </summary>
class PeriodBasedHistoryRequestNotAllowedWithTickResolutionRegressionAlgorithm(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2013, 10, 8)
        self.set_end_date(2013, 10, 9)

        spy = self.add_equity("SPY", Resolution.TICK).symbol

        # Tick resolution is not allowed for period-based history requests
        self.assert_that_history_throws_for_tick_resolution(lambda: self.history[Tick](spy, 1),
            "Tick history call with implicit tick resolution")
        self.assert_that_history_throws_for_tick_resolution(lambda: self.history[Tick](spy, 1, Resolution.TICK),
            "Tick history call with explicit tick resolution")
        self.assert_that_history_throws_for_tick_resolution(lambda: self.history[Tick]([spy], 1),
            "Tick history call with symbol array with implicit tick resolution")
        self.assert_that_history_throws_for_tick_resolution(lambda: self.history[Tick]([spy], 1, Resolution.TICK),
            "Tick history call with symbol array with explicit tick resolution")

        history = self.history[Tick](spy, TimeSpan.from_hours(12))
        if len(list(history)) == 0:
            raise Exception("On history call with implicit tick resolution: history returned no results")

        history = self.history[Tick](spy, TimeSpan.from_hours(12), Resolution.TICK)
        if len(list(history)) == 0:
            raise Exception("On history call with explicit tick resolution: history returned no results")

    def assert_that_history_throws_for_tick_resolution(self, history_call, history_call_description):
        try:
            history_call()
            raise Exception(f"{history_call_description}: expected an exception to be thrown")
        except InvalidOperationException:
            # expected
            logger.debug("[VECTOR] suppressed exception", exc_info=True)
