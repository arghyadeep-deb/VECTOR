# ============================================================================
# VECTOR Financial Terminal - Strategy Engine
# Copyright (c) 2024-2026 VECTOR. All rights reserved.
# Licensed under the MIT License.
# https://github.com/Fincept-Corporation/VectorFinancialTerminal
#
# Strategy ID: FCT-86D91C89
# Category: Regression Test
# Description: Regression algorithm to test we can specify a custom settlement model using Security.set_settlement_model() method (w...
# Compatibility: Backtesting | Paper Trading | Live Deployment
# ============================================================================
from AlgorithmImports import *
from CustomSettlementModelRegressionAlgorithm import CustomSettlementModel, CustomSettlementModelRegressionAlgorithm

### <summary>
### Regression algorithm to test we can specify a custom settlement model using Security.set_settlement_model() method
### (without a custom brokerage model)
### </summary>
class SetCustomSettlementModelRegressionAlgorithm(CustomSettlementModelRegressionAlgorithm):
    def set_settlement_model(self, security):
        security.set_settlement_model(CustomSettlementModel())
