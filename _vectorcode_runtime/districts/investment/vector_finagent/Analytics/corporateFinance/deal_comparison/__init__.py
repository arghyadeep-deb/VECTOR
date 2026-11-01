"""Deal Comparison Module"""
from pathlib import Path

# Add Analytics path for absolute imports
analytics_path = Path(__file__).parent.parent.parent

# Use absolute imports instead of relative imports
from corporateFinance.deal_comparison.deal_comparator import DealComparator, Deal

__all__ = ['DealComparator', 'Deal']
