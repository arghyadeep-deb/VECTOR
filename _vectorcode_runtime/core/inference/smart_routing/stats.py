"""
VECTOR Smart Routing — Usage Statistics + Request Journal
Python port of ClawRouter/src/stats.ts + src/logger.ts

Tracks per-model usage, cost, latency, and savings.
Journals requests to ~/.vector/smart_routing/logs/YYYY-MM-DD.jsonl

Usage:
    journal = RequestJournal()
    journal.log(model="google/gemini-2.5-flash", tokens_in=1000,
                tokens_out=500, cost_usd=0.0002, latency_ms=800)
    stats = journal.get_stats(days=7)
    logger.info(stats["total_savings_usd"])

"""
from __future__ import annotations

__all__ = [
    "get_journal",
    "RequestJournal",
    "RequestLog",
    "UsageStats",
]


from pathlib import Path
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

_LOG_DIR = Path.home() / ".vector" / "smart_routing" / "logs"


@dataclass
class RequestLog:
    timestamp:   float
    model:       str
    provider:    str
    tier:        str
    profile:     str
    tokens_in:   int
    tokens_out:  int
    cost_usd:    float
    baseline_usd: float   # what claude-opus-4.7 would cost
    savings_usd:  float
    latency_ms:  int
    method:      str      # "rules" | "llm" (routing method)
    cache_hit:   bool
    error:       str = ""


@dataclass
class UsageStats:
    total_requests:   int = 0
    total_tokens_in:  int = 0
    total_tokens_out: int = 0
    total_cost_usd:   float = 0.0
    total_baseline_usd: float = 0.0
    total_savings_usd: float = 0.0
    savings_pct:       float = 0.0
    cache_hits:        int = 0
    avg_latency_ms:    float = 0.0
    by_model:          dict = field(default_factory=dict)
    by_tier:           dict = field(default_factory=dict)
    by_provider:       dict = field(default_factory=dict)
    period_days:       int = 7


class RequestJournal:
    """
    Persistent request/response journal for cost tracking and analytics.
    Stores JSONL logs per day in ~/.vector/smart_routing/logs/
    """

    def __init__(self, log_dir: Path | None = None) -> None:
        self._log_dir = log_dir or _LOG_DIR
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._today_file: Path | None = None
        self._buffer: list[RequestLog] = []

    def _get_log_file(self, date: datetime | None = None) -> Path:
        d = date or datetime.now()
        return self._log_dir / f"{d.strftime('%Y-%m-%d')}.jsonl"

    def log(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        latency_ms: int,
        tier: str = "MEDIUM",
        profile: str = "auto",
        method: str = "rules",
        baseline_usd: float = 0.0,
        cache_hit: bool = False,
        error: str = "",
    ) -> None:
        """Log a completed request."""
        from core.inference.smart_routing.model_catalog import get_model
        entry = get_model(model)
        provider = entry.provider if entry else model.split("/")[0]

        savings = max(0.0, baseline_usd - cost_usd)
        record = RequestLog(
            timestamp=time.time(),
            model=model,
            provider=provider,
            tier=tier,
            profile=profile,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            baseline_usd=baseline_usd,
            savings_usd=savings,
            latency_ms=latency_ms,
            method=method,
            cache_hit=cache_hit,
            error=error,
        )
        # Write to JSONL
        try:
            log_file = self._get_log_file()
            with log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(record)) + "\n")
        except Exception as e:
            logger.debug("[VECTOR][stats] log write failed: {}", e)

        logger.debug("[VECTOR][stats] {} ${:.6f} saved={:.1%} {}ms",
                     model, cost_usd, savings / max(baseline_usd, 0.001), latency_ms)

    def get_stats(self, days: int = 7) -> UsageStats:
        """Aggregate stats across the last N days."""
        stats = UsageStats(period_days=days)
        latencies: list[int] = []
        by_model: dict[str, dict] = defaultdict(lambda: {"requests": 0, "cost": 0.0, "tokens": 0})
        by_tier:  dict[str, int] = defaultdict(int)
        by_prov:  dict[str, dict] = defaultdict(lambda: {"requests": 0, "cost": 0.0})

        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            log_file = self._get_log_file(date)
            if not log_file.exists():
                continue
            for line in log_file.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                    stats.total_requests    += 1
                    stats.total_tokens_in   += r.get("tokens_in", 0)
                    stats.total_tokens_out  += r.get("tokens_out", 0)
                    stats.total_cost_usd    += r.get("cost_usd", 0)
                    stats.total_baseline_usd += r.get("baseline_usd", 0)
                    stats.total_savings_usd += r.get("savings_usd", 0)
                    if r.get("cache_hit"):
                        stats.cache_hits += 1
                    if r.get("latency_ms"):
                        latencies.append(r["latency_ms"])
                    m = r.get("model", "unknown")
                    by_model[m]["requests"] += 1
                    by_model[m]["cost"] = by_model[m].get("cost", 0.0) + r.get("cost_usd", 0)
                    by_model[m]["tokens"] = by_model[m].get("tokens", 0) + r.get("tokens_in", 0)
                    by_tier[r.get("tier", "MEDIUM")] += 1
                    p = r.get("provider", "unknown")
                    by_prov[p]["requests"] += 1
                    by_prov[p]["cost"] = by_prov[p].get("cost", 0.0) + r.get("cost_usd", 0)
                except Exception:
                    logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        if latencies:
            stats.avg_latency_ms = sum(latencies) / len(latencies)
        if stats.total_baseline_usd > 0:
            stats.savings_pct = stats.total_savings_usd / stats.total_baseline_usd

        stats.by_model    = dict(by_model)
        stats.by_tier     = dict(by_tier)
        stats.by_provider = dict(by_prov)
        return stats


# Module-level singleton
_journal: RequestJournal | None = None


def get_journal() -> RequestJournal:
    global _journal
    if _journal is None:
        _journal = RequestJournal()
    return _journal


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    journal = RequestJournal()
    journal.log(
        model="google/gemini-2.5-flash",
        tokens_in=500, tokens_out=200, cost_usd=0.0001,
        latency_ms=800, baseline_usd=0.0138, tier="SIMPLE",
    )
    stats = journal.get_stats(days=1)
    print(f"OK stats.py — request journaling + usage statistics")
    print(f"  log_dir: {journal._log_dir}")
    print(f"  total_requests: {stats.total_requests}")
    print(f"  total_cost: ${stats.total_cost_usd:.6f}")
    print(f"  savings: {stats.savings_pct:.0%}")
