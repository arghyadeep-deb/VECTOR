"""Usage analytics — VectorCode implementation.

Analyzes session history from SessionDB for:
- Token consumption (input, output, cached)
- Cost estimation by model
- Tool usage patterns
- Activity trends
- Cost breakdown by provider
"""

from __future__ import annotations

from pathlib import Path
import sys


try:
    from core.config import CONFIG
except ImportError:
    CONFIG = {}

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from loguru import logger

# ── Pricing table (per-token costs in USD) ────────────────────────────────────
PRICING: dict[str, dict[str, float]] = {
    "anthropic/claude-sonnet-4-6": {"in": 3.0e-6,  "out": 15.0e-6, "cache": 0.3e-6},
    "anthropic/claude-opus-4-7":   {"in": 15.0e-6, "out": 75.0e-6, "cache": 1.5e-6},
    "anthropic/claude-haiku-4-5":  {"in": 0.8e-6,  "out": 4.0e-6,  "cache": 0.08e-6},
    "openai/gpt-4o":               {"in": 2.5e-6,  "out": 10.0e-6, "cache": 1.25e-6},
    "openai/gpt-4o-mini":          {"in": 0.15e-6, "out": 0.6e-6,  "cache": 0.075e-6},
    "groq/llama-4-scout":          {"in": 0.11e-6, "out": 0.34e-6, "cache": 0.0},
    "google/gemini-2.5-pro":       {"in": 1.25e-6, "out": 5.0e-6,  "cache": 0.0},
    "google/gemini-2.5-flash":     {"in": 0.15e-6, "out": 0.6e-6,  "cache": 0.0},
    "deepseek/deepseek-coder-v3":  {"in": 0.27e-6, "out": 1.1e-6,  "cache": 0.0},
    "mistral/codestral":           {"in": 1.0e-6,  "out": 3.0e-6,  "cache": 0.0},
    "ollama/*":                    {"in": 0.0,     "out": 0.0,     "cache": 0.0},
}

# ISO 8601 timestamp formats VectorCode stores
_TS_FMTS = [
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
]


def _parse_ts(ts_str: str | None) -> float | None:
    """Parse ISO timestamp string to unix float. Returns None on failure."""
    if not ts_str:
        return None
    for fmt in _TS_FMTS:
        try:
            return datetime.strptime(ts_str, fmt).replace(
                tzinfo=timezone.utc
            ).timestamp()
        except ValueError:
            continue
    return None


def _bar_chart(values: list[int], max_width: int = 20) -> list[str]:
    """Return simple ASCII bar strings for a list of integer values."""
    peak = max(values) if values else 1
    if peak == 0:
        return ["" for _ in values]
    return [
        "█" * max(1, int(v / peak * max_width)) if v > 0 else ""
        for v in values
    ]


class InsightsEngine:
    """Analyzes session history from ~/.vector/sessions.db."""

    def __init__(self, db_path: Path | None = None) -> None:
        try:
            from session_db import get_session_db, SessionDB
            if db_path is not None:
                self._db = SessionDB(db_path)
            else:
                self._db = get_session_db()
            self._conn = self._db._conn
        except Exception as e:
            logger.warning(f"[VECTOR][insights] Could not open session DB: {e}")
            self._db = None
            self._conn = None

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(self, days: int = 30) -> dict[str, Any]:
        """Generate full analytics report for last N days.

        Returns:
        {
            "period_days": int,
            "sessions": int,
            "messages": int,
            "tokens": {"input": int, "output": int, "cache_read": int, "total": int},
            "cost_usd": float,
            "top_models": [{"model": str, "sessions": int, "cost_usd": float}],
            "daily_activity": [{"date": str, "sessions": int, "tokens": int}],
            "tool_usage": [{"tool": str, "count": int}],
        }
        """
        if self._conn is None:
            return self._empty_report(days)

        import time as _time
        cutoff_ts = _time.time() - (days * 86400)
        cutoff_iso = datetime.fromtimestamp(cutoff_ts, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

        try:
            rows = self._fetch_sessions(cutoff_iso)
        except Exception as e:
            logger.error(f"[VECTOR][insights] DB query failed: {e}")
            return self._empty_report(days)

        if not rows:
            return self._empty_report(days)

        total_input  = sum(r.get("input_tokens") or 0 for r in rows)
        total_output = sum(r.get("output_tokens") or 0 for r in rows)
        total_cache  = sum(r.get("cache_read_tokens") or 0 for r in rows)
        total_tokens = total_input + total_output + total_cache

        total_cost = sum(
            self.estimate_cost(
                r.get("model") or "ollama/unknown",
                r.get("input_tokens") or 0,
                r.get("output_tokens") or 0,
                r.get("cache_read_tokens") or 0,
            )
            for r in rows
        )

        top_models = self._compute_top_models(rows)
        daily_activity = self._compute_daily_activity(rows)

        total_messages = sum(r.get("message_count") or 0 for r in rows)

        return {
            "period_days":    days,
            "sessions":       len(rows),
            "messages":       total_messages,
            "tokens": {
                "input":      total_input,
                "output":     total_output,
                "cache_read": total_cache,
                "total":      total_tokens,
            },
            "cost_usd":       total_cost,
            "top_models":     top_models,
            "daily_activity": daily_activity,
            "tool_usage":     [],  # VectorCode schema has no tool_calls detail column
        }

    def format_terminal(self, days: int = 30) -> str:
        """Human-readable terminal display with ASCII charts."""
        report = self.generate(days)

        if report.get("sessions", 0) == 0:
            return f"  No sessions found in the last {days} days."

        lines: list[str] = []
        t = report["tokens"]

        # Header
        lines.append("")
        lines.append("  ╔" + "═" * 56 + "╗")
        lines.append("  ║" + f"{'VectorCode Usage Insights':^56}" + "║")
        lines.append("  ║" + f"{f'Last {days} days':^56}" + "║")
        lines.append("  ╚" + "═" * 56 + "╝")
        lines.append("")

        # Overview
        lines.append("  Overview")
        lines.append("  " + "─" * 54)
        lines.append(f"  Sessions:     {report['sessions']:<10}  Messages:   {report['messages']:,}")
        lines.append(f"  Input tokens: {t['input']:<10,}  Output:     {t['output']:,}")
        lines.append(f"  Cache-read:   {t['cache_read']:<10,}  Total:      {t['total']:,}")
        lines.append(f"  Estimated cost: ${report['cost_usd']:.6f} USD")
        lines.append("")

        # Top models
        if report["top_models"]:
            lines.append("  Top Models")
            lines.append("  " + "─" * 54)
            lines.append(f"  {'Model':<36} {'Sessions':>8} {'Cost USD':>10}")
            for m in report["top_models"][:8]:
                name = m["model"][:34]
                lines.append(
                    f"  {name:<36} {m['sessions']:>8} ${m['cost_usd']:>9.6f}"
                )
            lines.append("")

        # Daily activity (bar chart — last 14 days max)
        daily = report["daily_activity"][-14:]
        if daily:
            lines.append("  Daily Activity (last 14 days)")
            lines.append("  " + "─" * 54)
            counts = [d["sessions"] for d in daily]
            bars   = _bar_chart(counts, max_width=20)
            for i, day_row in enumerate(daily):
                bar = bars[i]
                lines.append(
                    f"  {day_row['date']}  {bar:<20} {day_row['sessions']} sessions"
                    f"  {day_row['tokens']:,} tok"
                )
            lines.append("")

        return "\n".join(lines)

    def estimate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read: int = 0,
    ) -> float:
        """Estimate cost for a request using PRICING table."""
        # Exact match first
        p = PRICING.get(model)
        if p is None:
            # Wildcard provider match: ollama/* matches ollama/anything
            provider = model.split("/", 1)[0] if "/" in model else model
            p = PRICING.get(f"{provider}/*")
        if p is None:
            # Unknown — assume cheap default
            p = {"in": 1.0e-6, "out": 4.0e-6, "cache": 0.3e-6}

        return (
            input_tokens  * p["in"]
            + output_tokens * p["out"]
            + cache_read    * p["cache"]
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _empty_report(self, days: int) -> dict[str, Any]:
        return {
            "period_days":    days,
            "sessions":       0,
            "messages":       0,
            "tokens":         {"input": 0, "output": 0, "cache_read": 0, "total": 0},
            "cost_usd":       0.0,
            "top_models":     [],
            "daily_activity": [],
            "tool_usage":     [],
        }

    def _fetch_sessions(self, cutoff_iso: str) -> list[dict]:
        """Fetch all sessions started on or after cutoff_iso."""
        cursor = self._conn.execute(
            "SELECT * FROM sessions WHERE started_at >= ? ORDER BY started_at DESC",
            (cutoff_iso,),
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def _compute_top_models(self, rows: list[dict]) -> list[dict[str, Any]]:
        """Aggregate sessions by model, return sorted by session count."""
        model_data: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"sessions": 0, "cost_usd": 0.0}
        )
        for r in rows:
            model = r.get("model") or "unknown"
            model_data[model]["sessions"] += 1
            model_data[model]["cost_usd"] += self.estimate_cost(
                model,
                r.get("input_tokens") or 0,
                r.get("output_tokens") or 0,
                r.get("cache_read_tokens") or 0,
            )
        result = [{"model": k, **v} for k, v in model_data.items()]
        result.sort(key=lambda x: x["sessions"], reverse=True)
        return result

    def _compute_daily_activity(self, rows: list[dict]) -> list[dict[str, Any]]:
        """Aggregate sessions by calendar date (UTC), return sorted ascending."""
        daily: dict[str, dict[str, int]] = defaultdict(
            lambda: {"sessions": 0, "tokens": 0}
        )
        for r in rows:
            ts = _parse_ts(r.get("started_at"))
            if ts is None:
                continue
            date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            daily[date_str]["sessions"] += 1
            daily[date_str]["tokens"] += (
                (r.get("input_tokens") or 0)
                + (r.get("output_tokens") or 0)
                + (r.get("cache_read_tokens") or 0)
            )
        result = [
            {"date": d, "sessions": v["sessions"], "tokens": v["tokens"]}
            for d, v in sorted(daily.items())
        ]
        return result


# ── Module-level self-test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import io as _io
    _stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    engine = InsightsEngine()
    _stdout.write(engine.format_terminal(days=30))
    _stdout.write("\n")
    _stdout.flush()
    report = engine.generate(days=30)
    assert "sessions" in report
    assert "tokens" in report
    assert "cost_usd" in report
    _stdout.write("insights.py OK\n")
    _stdout.flush()

