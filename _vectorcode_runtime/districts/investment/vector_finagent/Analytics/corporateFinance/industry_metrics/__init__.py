"""Industry-Specific M&A Metrics Module"""
from pathlib import Path

# Add Analytics path for absolute imports
analytics_path = Path(__file__).parent.parent.parent

# Use absolute imports instead of relative imports
from corporateFinance.industry_metrics.technology import TechnologyMetrics, TechBusinessModel
from corporateFinance.industry_metrics.healthcare import HealthcareMetrics, HealthcareSegment
from corporateFinance.industry_metrics.financial_services import FinancialServicesMetrics

__all__ = [
    'TechnologyMetrics',
    'TechBusinessModel',
    'HealthcareMetrics',
    'HealthcareSegment',
    'FinancialServicesMetrics'
]
