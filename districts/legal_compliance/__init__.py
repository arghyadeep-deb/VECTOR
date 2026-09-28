"""VECTOR legal_compliance District — regulated-content compliance checks (advisory-only, gated).

New district per VECTOR_TECHNICAL_KNOWLEDGE/SELF_DEV_AGENT_SPEC.md ("kept separate on purpose,
never folded into a general district, because regulated advice needs its own tier discipline").
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from districts.legal_compliance.legal_compliance_specialists import LegalComplianceChecker
from districts.legal_compliance.legal_specialists import (
    HealthcareCustomerServiceSpecialist,
    HealthcareMarketingComplianceSpecialist,
    LegalBillingTimeTrackingSpecialist,
    LegalClientIntakeSpecialist,
    LegalDocumentReviewSpecialist,
)

__all__ = [
    "LegalComplianceChecker",
    "HealthcareCustomerServiceSpecialist",
    "HealthcareMarketingComplianceSpecialist",
    "LegalBillingTimeTrackingSpecialist",
    "LegalClientIntakeSpecialist",
    "LegalDocumentReviewSpecialist",
]


def _smoke_check() -> bool:
    agents = [cls() for cls in (
        LegalComplianceChecker,
        HealthcareCustomerServiceSpecialist,
        HealthcareMarketingComplianceSpecialist,
        LegalBillingTimeTrackingSpecialist,
        LegalClientIntakeSpecialist,
        LegalDocumentReviewSpecialist,
    )]
    return all(agent.district == "legal_compliance" and len(agent.capabilities) == 2 for agent in agents)


if __name__ == "__main__":
    assert _smoke_check(), "legal_compliance package smoke check failed"
