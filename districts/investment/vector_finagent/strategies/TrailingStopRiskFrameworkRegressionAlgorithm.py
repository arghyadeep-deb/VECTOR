# ============================================================================
# VECTOR Financial Terminal - Strategy Engine
# Derived from Fincept Terminal (Fincept Corporation) -- see THIRD_PARTY_NOTICES.md.
# Adapted for VECTOR (owner's personal-use build).
#
# Strategy ID: FCT-DD7ECCB4
# Category: Risk Management
# Description: Show example of how to use the TrailingStopRiskManagementModel
# Compatibility: Backtesting | Paper Trading | Live Deployment
# ============================================================================
from AlgorithmImports import *
from BaseFrameworkRegressionAlgorithm import BaseFrameworkRegressionAlgorithm
from Risk.TrailingStopRiskManagementModel import TrailingStopRiskManagementModel

class TrailingStopRiskFrameworkRegressionAlgorithm(BaseFrameworkRegressionAlgorithm):
    '''Show example of how to use the TrailingStopRiskManagementModel'''

    def initialize(self):
        super().initialize()
        self.set_universe_selection(ManualUniverseSelectionModel([Symbol.create("AAPL", SecurityType.EQUITY, Market.USA)]))

        self.set_risk_management(TrailingStopRiskManagementModel(0.01))
