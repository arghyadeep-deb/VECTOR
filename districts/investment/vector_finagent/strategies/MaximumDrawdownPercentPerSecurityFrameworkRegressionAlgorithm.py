# ============================================================================
# VECTOR Financial Terminal - Strategy Engine
# Derived from Fincept Terminal (Fincept Corporation) -- see THIRD_PARTY_NOTICES.md.
# Adapted for VECTOR (owner's personal-use build).
#
# Strategy ID: FCT-791ECD54
# Category: Regression Test
# Description: Regression algorithm to assert the behavior of <see cref="MaximumDrawdownPercentPerSecurity"/>
# Compatibility: Backtesting | Paper Trading | Live Deployment
# ============================================================================
from AlgorithmImports import *
from BaseFrameworkRegressionAlgorithm import BaseFrameworkRegressionAlgorithm
from Risk.MaximumDrawdownPercentPerSecurity import MaximumDrawdownPercentPerSecurity

### <summary>
### Regression algorithm to assert the behavior of <see cref="MaximumDrawdownPercentPerSecurity"/>.
### </summary>
class MaximumDrawdownPercentPerSecurityFrameworkRegressionAlgorithm(BaseFrameworkRegressionAlgorithm):

    def initialize(self):
        super().initialize()
        self.set_universe_selection(ManualUniverseSelectionModel(Symbol.create("AAPL", SecurityType.EQUITY, Market.USA)))

        self.set_risk_management(MaximumDrawdownPercentPerSecurity(0.004))

