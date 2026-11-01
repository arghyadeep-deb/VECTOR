from __future__ import annotations

import re
from dataclasses import dataclass


__all__ = ["ConsistencyEnforcer", "InconsistencyReport"]

_CASUAL_PATTERNS = [
    re.compile(r"\bno prob\b", re.IGNORECASE),
    re.compile(r"\bgonna\b", re.IGNORECASE),
    re.compile(r"\bwanna\b", re.IGNORECASE),
    re.compile(r"\blol\b", re.IGNORECASE),
    re.compile(r"\bbruh\b", re.IGNORECASE),
]

_OVERLY_FAMILIAR = [
    re.compile(r"\bdude\b", re.IGNORECASE),
    re.compile(r"\bbro\b", re.IGNORECASE),
    re.compile(r"\bmate\b", re.IGNORECASE),
]


@dataclass
class InconsistencyReport:
    district: str
    text_snippet: str
    issue: str
    severity: str


class ConsistencyEnforcer:
    def check_output(self, district_name: str, text: str) -> str:
        return text

    def audit_recent_outputs(
        self, outputs: list[dict[str, str]]
    ) -> list[InconsistencyReport]:
        reports: list[InconsistencyReport] = []
        for entry in outputs:
            district = entry.get("district", "unknown")
            text = entry.get("text", "")
            for pat in _CASUAL_PATTERNS:
                if pat.search(text):
                    reports.append(
                        InconsistencyReport(
                            district=district,
                            text_snippet=text[:80],
                            issue=f"Casual language detected: {pat.pattern}",
                            severity="low",
                        )
                    )
            for pat in _OVERLY_FAMILIAR:
                if pat.search(text):
                    reports.append(
                        InconsistencyReport(
                            district=district,
                            text_snippet=text[:80],
                            issue=f"Overly familiar language: {pat.pattern}",
                            severity="medium",
                        )
                    )
        return reports
