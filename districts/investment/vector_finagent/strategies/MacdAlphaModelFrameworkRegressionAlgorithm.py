# ============================================================================
# VECTOR Financial Terminal - Strategy Engine
# Derived from Fincept Terminal (Fincept Corporation) -- see THIRD_PARTY_NOTICES.md.
# Adapted for VECTOR (owner's personal-use build).
#
# Strategy ID: FCT-EABA6096
# Category: Alpha Model
# Description: Regression algorithm to assert the behavior of <see cref="MacdAlphaModel"/>
# Compatibility: Backtesting | Paper Trading | Live Deployment
# ============================================================================
from AlgorithmImports import *
from BaseFrameworkRegressionAlgorithm import BaseFrameworkRegressionAlgorithm
from Alphas.MacdAlphaModel import MacdAlphaModel

### <summary>
### Regression algorithm to assert the behavior of <see cref="MacdAlphaModel"/>.
### </summary>
class MacdAlphaModelFrameworkRegressionAlgorithm(BaseFrameworkRegressionAlgorithm):

    def initialize(self):
        super().initialize()
        self.set_alpha(MacdAlphaModel())

    def on_end_of_algorithm(self):
        expected = 4
        if self.insights.total_count != expected:
           raise Exception(f"The total number of insights should be {expected}. Actual: {self.insights.total_count}")
