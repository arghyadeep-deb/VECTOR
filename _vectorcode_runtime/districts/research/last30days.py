"""Recency-first social intelligence contracts.

Safe skeleton for the promoted last30days idea. It does not scrape or call
external services directly; it normalizes source signals and produces a ranked
brief that live connectors can feed later after SkillSpector quarantine.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class RecentSignal:
    source: str
    title: str
    url: str
    published_at: str
    engagement: float = 0.0
    confidence: float = 0.5
    notes: str = ""

    def score(self, *, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        try:
            published = datetime.fromisoformat(self.published_at.replace("Z", "+00:00"))
            age_days = max(0.0, (now - published).total_seconds() / 86400)
        except Exception:
            age_days = 30.0
        recency = max(0.0, 1.0 - min(age_days, 30.0) / 30.0)
        return round((recency * 60.0) + (min(self.engagement, 1000.0) / 1000.0 * 25.0) + (self.confidence * 15.0), 2)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["score"] = self.score()
        return data


@dataclass
class Last30DaysBrief:
    query: str
    as_of: str
    signals: list[RecentSignal] = field(default_factory=list)
    degraded_sources: list[str] = field(default_factory=list)

    def ranked(self) -> list[dict[str, Any]]:
        return sorted((s.to_dict() for s in self.signals), key=lambda item: item["score"], reverse=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "as_of": self.as_of,
            "signals": self.ranked(),
            "degraded_sources": self.degraded_sources,
        }


def build_brief(query: str, signals: list[RecentSignal], degraded_sources: list[str] | None = None) -> Last30DaysBrief:
    return Last30DaysBrief(
        query=query,
        as_of=datetime.now(timezone.utc).isoformat(),
        signals=signals,
        degraded_sources=degraded_sources or [],
    )

