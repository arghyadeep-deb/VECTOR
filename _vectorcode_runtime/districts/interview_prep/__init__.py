"""
Module: agents/interview_prep/__init__.py
V.E.C.T.O.R. Interview Prep District - Interview preparation agents
"""

import sys

from loguru import logger

from .mock_interviewer import MockInterviewer
from .company_researcher import CompanyResearcher
from .feedback_analyst import FeedbackAnalyst
from .report_generator import ReportGenerator

__all__ = [
    "MockInterviewer",
    "CompanyResearcher",
    "FeedbackAnalyst",
    "ReportGenerator",
]

logger.info("[VECTOR][interview_prep] Interview Prep district loaded")


def get_agent(name: str):
    """Factory function to get interview prep agents."""
    agents = {
        "MockInterviewer": MockInterviewer,
        "CompanyResearcher": CompanyResearcher,
        "FeedbackAnalyst": FeedbackAnalyst,
        "ReportGenerator": ReportGenerator,
    }
    return agents.get(name)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    interviewer = MockInterviewer()
    print(f"MockInterviewer: {interviewer.name}")

    researcher = CompanyResearcher()
    print(f"CompanyResearcher: {researcher.name}")

    analyst = FeedbackAnalyst()
    print(f"FeedbackAnalyst: {analyst.name}")

    reporter = ReportGenerator()
    print(f"ReportGenerator: {reporter.name}")

    print("✅ interview_prep/__init__.py OK")
