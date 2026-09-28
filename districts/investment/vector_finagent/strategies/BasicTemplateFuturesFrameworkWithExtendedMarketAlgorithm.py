# ============================================================================
# VECTOR Financial Terminal - Strategy Engine
# Derived from Fincept Terminal (Fincept Corporation) -- see THIRD_PARTY_NOTICES.md.
# Adapted for VECTOR (owner's personal-use build).
#
# Strategy ID: FCT-456D112C
# Category: Futures
# Description: Basic template futures framework algorithm uses framework components to define an algorithm that trades futures
# Compatibility: Backtesting | Paper Trading | Live Deployment
# ============================================================================
from AlgorithmImports import *

from BasicTemplateFuturesFrameworkAlgorithm import BasicTemplateFuturesFrameworkAlgorithm

### <summary>
### Basic template futures framework algorithm uses framework components
### to define an algorithm that trades futures.
### </summary>
class BasicTemplateFuturesFrameworkWithExtendedMarketAlgorithm(BasicTemplateFuturesFrameworkAlgorithm):

    def get_extended_market_hours(self):
        return True
