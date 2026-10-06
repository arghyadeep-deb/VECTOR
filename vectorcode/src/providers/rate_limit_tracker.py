"""Rate limit tracking for inference API responses.

Captures x-ratelimit-* headers from provider responses and provides
formatted display for the /usage slash command.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any, Mapping, Optional


@dataclass
class RateLimitBucket:
    limit: int = 0
    remaining: int = 0
    reset_seconds: float = 0.0
    captured_at: float = 0.0

    @property
    def used(self) -> int:
        return max(0, self.limit - self.remaining)

    @property
    def usage_pct(self) -> float:
        if self.limit <= 0: return 0.0
        return (self.used / self.limit) * 100.0

    @property
    def remaining_seconds_now(self) -> float:
        return max(0.0, self.reset_seconds - (time.time() - self.captured_at))


@dataclass
class RateLimitState:
    requests_min: RateLimitBucket = field(default_factory=RateLimitBucket)
    requests_hour: RateLimitBucket = field(default_factory=RateLimitBucket)
    tokens_min: RateLimitBucket = field(default_factory=RateLimitBucket)
    tokens_hour: RateLimitBucket = field(default_factory=RateLimitBucket)
    captured_at: float = 0.0
    provider: str = ""

    @property
    def has_data(self) -> bool:
        return self.captured_at > 0

    @property
    def age_seconds(self) -> float:
        if not self.has_data: return float("inf")
        return time.time() - self.captured_at


def parse_rate_limit_headers(headers: Mapping[str, str], provider: str = "") -> Optional[RateLimitState]:
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
        captured_at=now, provider=provider,
    )


def _safe_int(value: Any, default: int = 0) -> int:
    try: return int(float(value))
    except (TypeError, ValueError): return default

def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    raw = str(value).strip()
    try:
        return float(raw)
    except ValueError:
        pass
    duration = re.fullmatch(r"(\d+(?:\.\d+)?)(ms|s|m|h)", raw, re.IGNORECASE)
    if duration:
        amount = float(duration.group(1))
        unit = duration.group(2).lower()
        return amount * {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[unit]
    try:
        reset_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=timezone.utc)
        return max(0.0, reset_at.timestamp() - time.time())
    except ValueError:
        return default


def format_rate_limit_display(state: RateLimitState) -> str:
    if not state.has_data:
        return "No rate limit data yet."
    age = state.age_seconds
    freshness = f"{int(age)}s ago" if age < 60 else f"{_fmt_seconds(age)} ago"
    lines = [f"{state.provider.title()} Rate Limits ({freshness}):", ""]
    lines.append(_bucket_line("Requests/min", state.requests_min))
    lines.append(_bucket_line("Requests/hr", state.requests_hour))
    lines.append("")
    lines.append(_bucket_line("Tokens/min", state.tokens_min))
    lines.append(_bucket_line("Tokens/hr", state.tokens_hour))
    warnings = []
    for label, bucket in [("req/min", state.requests_min), ("req/hr", state.requests_hour),
                          ("tok/min", state.tokens_min), ("tok/hr", state.tokens_hour)]:
        if bucket.limit > 0 and bucket.usage_pct >= 80:
            warnings.append(f"  \u26A0 {label} at {bucket.usage_pct:.0f}%")
    if warnings: lines.extend(["", *warnings])
    return "\n".join(lines)


def _fmt_count(n: int) -> str:
    if n >= 1_000_000: return f"{n / 1_000_000:.1f}M"
    if n >= 10_000: return f"{n / 1_000:.1f}K"
    if n >= 1_000: return f"{n / 1_000:.1f}K"
    return str(n)

def _fmt_seconds(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60: return f"{s}s"
    if s < 3600: return f"{s // 60}m {s % 60}s"
    return f"{s // 3600}h {(s % 3600) // 60}m"

def _bar(pct: float, width: int = 20) -> str:
    filled = max(0, min(width, int(pct / 100.0 * width)))
    return f"[{'\u2588' * filled}{'\u2591' * (width - filled)}]"

def _bucket_line(label: str, bucket: RateLimitBucket, label_width: int = 14) -> str:
    if bucket.limit <= 0: return f"  {label:<{label_width}}  (no data)"
    bar = _bar(bucket.usage_pct)
    return f"  {label:<{label_width}} {bar} {bucket.usage_pct:5.1f}%  {_fmt_count(bucket.used)}/{_fmt_count(bucket.limit)} used"
