"""Base interface for report storage backends."""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class ReportStorage(ABC):
    """Abstract base class for report storage backends."""

    @abstractmethod
    def save_report(
        self,
        research_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        username: Optional[str] = None,
    ) -> bool:
        """Save a research report.

        Args:
            research_id: Unique identifier for the research
            content: Report content (markdown)
            metadata: Optional metadata to store with the report
            username: Optional username for user-specific storage

        Returns:
            True if successful, False otherwise
        """
        raise NotImplementedError("ReportStorage.save_report must be implemented by subclass")

    @abstractmethod
    def get_report(
        self, research_id: str, username: Optional[str] = None
    ) -> Optional[str]:
        """Retrieve a research report.

        Args:
            research_id: Unique identifier for the research
            username: Optional username for user-specific storage

        Returns:
            Report content if found, None otherwise
        """
        raise NotImplementedError("ReportStorage.get_report must be implemented by subclass")

    @abstractmethod
    def get_report_with_metadata(
        self, research_id: str, username: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a research report with its metadata.

        Args:
            research_id: Unique identifier for the research
            username: Optional username for user-specific storage

        Returns:
            Dictionary with 'content' and 'metadata' keys if found, None otherwise
        """
        raise NotImplementedError("ReportStorage.get_report_with_metadata must be implemented by subclass")

    @abstractmethod
    def delete_report(
        self, research_id: str, username: Optional[str] = None
    ) -> bool:
        """Delete a research report.

        Args:
            research_id: Unique identifier for the research
            username: Optional username for user-specific storage

        Returns:
            True if successful, False otherwise
        """
        raise NotImplementedError("ReportStorage.delete_report must be implemented by subclass")

    @abstractmethod
    def list_reports(
        self, username: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List available reports.

        Args:
            username: Optional username for user-specific filtering

        Returns:
            List of report summaries with 'id', 'query', 'mode', 'created_at', 'completed_at' keys
        """
        raise NotImplementedError("ReportStorage.list_reports must be implemented by subclass")

    @abstractmethod
    def report_exists(
        self, research_id: str, username: Optional[str] = None
    ) -> bool:
        """Check if a report exists.

        Args:
            research_id: Unique identifier for the research
            username: Optional username for user-specific storage

        Returns:
            True if report exists, False otherwise
        """
        raise NotImplementedError("ReportStorage.report_exists must be implemented by subclass")
