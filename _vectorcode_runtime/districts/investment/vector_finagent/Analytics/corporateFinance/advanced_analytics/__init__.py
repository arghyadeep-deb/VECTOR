"""Advanced Analytics Module"""
from pathlib import Path

# Add Analytics path for absolute imports
analytics_path = Path(__file__).parent.parent.parent

# Use absolute imports instead of relative imports
from corporateFinance.advanced_analytics.monte_carlo_valuation import MonteCarloValuation
from corporateFinance.advanced_analytics.regression_analysis import MARegression, RegressionResult

__all__ = [
    'MonteCarloValuation',
    'MARegression',
    'RegressionResult'
]
