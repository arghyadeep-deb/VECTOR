# ============================================================================
# VECTOR Financial Terminal - Strategy Engine
# Derived from Fincept Terminal (Fincept Corporation) -- see THIRD_PARTY_NOTICES.md.
# Adapted for VECTOR (owner's personal-use build).
#
# Strategy ID: FCT-7A279BE5
# Category: Portfolio Management
# Description: Regression algorithm to assert the behavior of <see cref="MaximumDrawdownPercentPortfolio"/>
# Compatibility: Backtesting | Paper Trading | Live Deployment
# ============================================================================
from AlgorithmImports import *
from BaseFrameworkRegressionAlgorithm import BaseFrameworkRegressionAlgorithm
from Risk.CompositeRiskManagementModel import CompositeRiskManagementModel
from Risk.MaximumDrawdownPercentPortfolio import MaximumDrawdownPercentPortfolio

### <summary>
### Regression algorithm to assert the behavior of <see cref="MaximumDrawdownPercentPortfolio"/>.
### </summary>
class MaximumDrawdownPercentPortfolioFrameworkRegressionAlgorithm(BaseFrameworkRegressionAlgorithm):

    def initialize(self):
        super().initialize()
        self.set_universe_selection(ManualUniverseSelectionModel(Symbol.create("AAPL", SecurityType.EQUITY, Market.USA)))

        # define risk management model as a composite of several risk management models
        self.set_risk_management(CompositeRiskManagementModel(
            MaximumDrawdownPercentPortfolio(0.01),         # Avoid loss of initial capital
            MaximumDrawdownPercentPortfolio(0.015, True)   # Avoid profit losses
            ))
