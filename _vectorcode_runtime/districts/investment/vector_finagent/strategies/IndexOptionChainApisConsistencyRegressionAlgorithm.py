# ============================================================================
# VECTOR Financial Terminal - Strategy Engine
# Derived from Fincept Terminal (Fincept Corporation) -- see THIRD_PARTY_NOTICES.md.
# Adapted for VECTOR (owner's personal-use build).
#
# Strategy ID: FCT-F859111A
# Category: Options
# Description: Regression algorithm asserting that the option chain APIs return consistent values for index options. See QCAlgorithm...
# Compatibility: Backtesting | Paper Trading | Live Deployment
# ============================================================================
from datetime import datetime
from AlgorithmImports import *

from OptionChainApisConsistencyRegressionAlgorithm import OptionChainApisConsistencyRegressionAlgorithm

### <summary>
### Regression algorithm asserting that the option chain APIs return consistent values for index options.
### See QCAlgorithm.OptionChain(Symbol) and QCAlgorithm.OptionChainProvider
### </summary>
class IndexOptionChainApisConsistencyRegressionAlgorithm(OptionChainApisConsistencyRegressionAlgorithm):

    def get_test_date(self) -> datetime:
        return datetime(2021, 1, 4)

    def get_option(self) -> Option:
        return self.add_index_option("SPX")
