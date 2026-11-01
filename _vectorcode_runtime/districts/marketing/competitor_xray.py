"""VECTOR-native competitor x-ray workflow.

Clean-room implementation of the promoted Competitor X-Ray idea: structured
briefs with evidence tiers, source links, and threat ranking.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


EVIDENCE_TIERS = {"CONFIRMED", "REPORTED", "INFERRED", "NOT_FOUND"}


@dataclass
class EvidenceClaim:
    claim: str
    tier: str
    source_url: str = ""

    def __post_init__(self) -> None:
        tier = self.tier.upper()
        if tier not in EVIDENCE_TIERS:
            raise ValueError(f"invalid evidence tier: {self.tier}")
        self.tier = tier


@dataclass
class CompetitorXRayBrief:
    target: str
    normalized_target: str
    target_type: str
    icp: list[EvidenceClaim] = field(default_factory=list)
    funnel: list[EvidenceClaim] = field(default_factory=list)
    monetization: list[EvidenceClaim] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    confidence: str = "low"
    threat_score: float = 0.0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


def normalize_target(target: str) -> dict[str, str]:
    raw = target.strip()
    lowered = raw.lower()
    if re.search(r"https?://|www\.|[a-z0-9-]+\.[a-z]{2,}", lowered):
        kind = "url"
        normalized = raw if re.match(r"https?://", raw, re.I) else f"https://{raw.lstrip('@')}"
    elif raw.startswith("@") or re.match(r"^[A-Za-z0-9_.-]{2,40}$", raw):
        kind = "social_handle"
        normalized = raw.lstrip("@")
    else:
        kind = "company_or_person"
        normalized = re.sub(r"\s+", " ", raw)
    return {"raw": raw, "normalized": normalized, "type": kind}


def build_empty_brief(target: str, *, confidence: str = "low") -> CompetitorXRayBrief:
    normalized = normalize_target(target)
    return CompetitorXRayBrief(
        target=normalized["raw"],
        normalized_target=normalized["normalized"],
        target_type=normalized["type"],
        confidence=confidence,
    )


def score_threat(
    *,
    maturity: float = 0.0,
    momentum: float = 0.0,
    evidence_quality: float = 0.0,
) -> float:
    score = (maturity * 0.45) + (momentum * 0.35) + (evidence_quality * 0.20)
    return round(max(0.0, min(100.0, score)), 2)


def rank_threats(briefs: list[CompetitorXRayBrief]) -> list[dict[str, Any]]:
    ranked = sorted(briefs, key=lambda b: b.threat_score, reverse=True)
    return [
        {
            "rank": index + 1,
            "target": brief.target,
            "normalized_target": brief.normalized_target,
            "threat_score": brief.threat_score,
            "confidence": brief.confidence,
        }
        for index, brief in enumerate(ranked)
    ]


def make_claim(claim: str, tier: str = "INFERRED", source_url: str = "") -> EvidenceClaim:
    return EvidenceClaim(claim=claim, tier=tier, source_url=source_url)

