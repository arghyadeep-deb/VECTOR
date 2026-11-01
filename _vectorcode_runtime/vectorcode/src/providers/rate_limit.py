"""Rate limit tracking — absorbed from reference agent/rate_limit_tracker.py.

Parses x-ratelimit-* response headers and formats them for /usage display.
Supports Nous Portal, OpenRouter, OpenAI-compatible header schema (12 headers).
"""
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Mapping, Optional



@dataclass
class RateLimitBucket:
    """One rate-limit window (requests/min, tokens/min, etc.)."""
    limit: int = 0
    remaining: int = 0
    reset_seconds: float = 0.0
    captured_at: float = 0.0

    @property
    def used(self) -> int:
        return max(0, self.limit - self.remaining)

    @property
    def usage_pct(self) -> float:
        return (self.used / self.limit * 100.0) if self.limit > 0 else 0.0

    @property
    def remaining_seconds_now(self) -> float:
        return max(0.0, self.reset_seconds - (time.time() - self.captured_at))


@dataclass
class RateLimitState:
    """Full rate-limit state for one provider/request."""
    requests_min:  RateLimitBucket = field(default_factory=RateLimitBucket)
    requests_hour: RateLimitBucket = field(default_factory=RateLimitBucket)
    tokens_min:    RateLimitBucket = field(default_factory=RateLimitBucket)
    tokens_hour:   RateLimitBucket = field(default_factory=RateLimitBucket)
    captured_at: float = 0.0
    provider: str = ""

    @property
    def has_data(self) -> bool:
        return self.captured_at > 0

    @property
    def age_seconds(self) -> float:
        return (time.time() - self.captured_at) if self.has_data else float("inf")


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    raw = str(v).strip()
    try:
        return float(raw)
    except ValueError:
        pass
    duration = re.fullmatch(r"(\d+(?:\.\d+)?)(ms|s|m|h)", raw, re.IGNORECASE)
    if duration:
        value = float(duration.group(1))
        unit = duration.group(2).lower()
        return value * {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[unit]
    try:
        reset_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=timezone.utc)
        return max(0.0, reset_at.timestamp() - time.time())
    except ValueError:
        return default


def parse_rate_limit_headers(
    headers: Mapping[str, str],
    provider: str = "",
) -> Optional[RateLimitState]:
    """Parse x-ratelimit-* headers into a RateLimitState. Returns None if absent."""
    lowered = {k.lower(): v for k, v in headers.items()}
    if not any(k.startswith("x-ratelimit-") for k in lowered):
        return None
    now = time.time()

    def _bucket(resource: str, suffix: str = "") -> RateLimitBucket:
        tag = f"{resource}{suffix}"
        return RateLimitBucket(
            limit=_safe_int(lowered.get(f"x-ratelimit-limit-{tag}")),
            remaining=_safe_int(lowered.get(f"x-ratelimit-remaining-{tag}")),
            reset_seconds=_safe_float(lowered.get(f"x-ratelimit-reset-{tag}")),
            captured_at=now,
        )

    return RateLimitState(
        requests_min=_bucket("requests"),
        requests_hour=_bucket("requests", "-1h"),
        tokens_min=_bucket("tokens"),
        tokens_hour=_bucket("tokens", "-1h"),
        captured_at=now,
        provider=provider,
    )


def _fmt_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def _fmt_seconds(s: float) -> str:
    s = max(0, int(s))
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if s < 3600:
        return f"{m}m {sec}s" if sec else f"{m}m"
    h, r = divmod(s, 3600)
    return f"{h}h {r//60}m" if r else f"{h}h"


def _bar(pct: float, width: int = 20) -> str:
    filled = max(0, min(width, int(pct / 100.0 * width)))
    return f"[{'█' * filled}{'░' * (width - filled)}]"


def format_rate_limits(state: RateLimitState) -> str:
    """Full rate-limit display for /usage command."""
    if not state.has_data:
        return "No rate limit data yet — make an API request first."

    age = state.age_seconds
    freshness = "just now" if age < 5 else (f"{int(age)}s ago" if age < 60 else f"{_fmt_seconds(age)} ago")
    provider = state.provider.title() if state.provider else "Provider"

    def line(label: str, b: RateLimitBucket) -> str:
        if b.limit <= 0:
            return f"  {label:<14}  (no data)"
        return (f"  {label:<14} {_bar(b.usage_pct)} {b.usage_pct:5.1f}%  "
                f"{_fmt_count(b.used)}/{_fmt_count(b.limit)}  "
                f"({_fmt_count(b.remaining)} left, resets {_fmt_seconds(b.remaining_seconds_now)})")

    lines = [
        f"{provider} Rate Limits (captured {freshness}):", "",
        line("Requests/min",  state.requests_min),
        line("Requests/hr",   state.requests_hour), "",
        line("Tokens/min",    state.tokens_min),
        line("Tokens/hr",     state.tokens_hour),
    ]
    warnings = [
        f"  ⚠ {lbl} at {b.usage_pct:.0f}% — resets {_fmt_seconds(b.remaining_seconds_now)}"
        for lbl, b in [("requests/min", state.requests_min), ("requests/hr", state.requests_hour),
                        ("tokens/min", state.tokens_min), ("tokens/hr", state.tokens_hour)]
        if b.limit > 0 and b.usage_pct >= 80
    ]
    if warnings:
        lines += [""] + warnings
    return "\n".join(lines)


def format_rate_limits_compact(state: RateLimitState) -> str:
    if not state.has_data:
        return "No rate limit data."
    parts = []
    if state.requests_min.limit > 0:
        parts.append(f"RPM: {state.requests_min.remaining}/{state.requests_min.limit}")
    if state.requests_hour.limit > 0:
        parts.append(f"RPH: {_fmt_count(state.requests_hour.remaining)}/{_fmt_count(state.requests_hour.limit)}")
    if state.tokens_min.limit > 0:
        parts.append(f"TPM: {_fmt_count(state.tokens_min.remaining)}/{_fmt_count(state.tokens_min.limit)}")
    if state.tokens_hour.limit > 0:
        parts.append(f"TPH: {_fmt_count(state.tokens_hour.remaining)}/{_fmt_count(state.tokens_hour.limit)}")
    return " | ".join(parts)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    # Parse fake headers
    fake_headers = {
        "x-ratelimit-limit-requests": "100",
        "x-ratelimit-remaining-requests": "45",
        "x-ratelimit-reset-requests": "30",
        "x-ratelimit-limit-tokens": "90000",
        "x-ratelimit-remaining-tokens": "72000",
        "x-ratelimit-reset-tokens": "15",
    }
    state = parse_rate_limit_headers(fake_headers, provider="anthropic")
    assert state is not None
    assert state.requests_min.limit == 100
    assert state.requests_min.remaining == 45
    assert state.requests_min.usage_pct == 55.0
    fmt = format_rate_limits(state)
    assert "Requests/min" in fmt
    compact = format_rate_limits_compact(state)
    assert "RPM:" in compact
    # Empty headers
    assert parse_rate_limit_headers({}) is None
    print("rate_limit.py OK")

