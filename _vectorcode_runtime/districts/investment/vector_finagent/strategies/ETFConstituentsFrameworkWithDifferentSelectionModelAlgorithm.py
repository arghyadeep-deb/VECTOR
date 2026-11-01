# ============================================================================
# VECTOR Financial Terminal - Strategy Engine
# Derived from Fincept Terminal (Fincept Corporation) -- see THIRD_PARTY_NOTICES.md.
# Adapted for VECTOR (owner's personal-use build).
#
# Strategy ID: FCT-A7B56E18
# Category: ETF
# Description: Demonstration of using the ETFConstituentsUniverseSelectionModel with simple ticker
# Compatibility: Backtesting | Paper Trading | Live Deployment
# ============================================================================
from AlgorithmImports import *
from Selection.ETFConstituentsUniverseSelectionModel import *
from ETFConstituentsFrameworkAlgorithm import ETFConstituentsFrameworkAlgorithm

### <summary>
### Demonstration of using the ETFConstituentsUniverseSelectionModel with simple ticker
### </summary>
class ETFConstituentsFrameworkWithDifferentSelectionModelAlgorithm(ETFConstituentsFrameworkAlgorithm):

    def initialize(self):
        super().initialize()
        
        self.set_universe_selection(ETFConstituentsUniverseSelectionModel("SPY", self.universe_settings, self.etf_constituents_filter))
