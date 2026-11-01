"""
Error Handling Module for VECTOR Research Engine

This module provides comprehensive error handling capabilities including:
- Error categorization and analysis
- User-friendly error report generation
- Integration with partial research results
"""

from .error_reporter import ErrorReporter
from .report_generator import ErrorReportGenerator

__all__ = ["ErrorReportGenerator", "ErrorReporter"]
