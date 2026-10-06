"""Honest provider quota/availability for the dev orchestrator.

Levels: UNKNOWN / NORMAL / CONSTRAINED / EXHAUSTED per provider.

Rules:
  - No invented numbers. Real telemetry is used only where it genuinely
    exists locally: Codex writes `rate_limits` (used_percent + reset time)
    into its own session logs (~/.codex/sessions/**/rollout-*.jsonl); that
    is read-only evidence. Claude Code exposes no reliable local telemetry,
    so Claude is UNKNOWN unless the owner sets it or a call reveals
    exhaustion.
  - UNKNOWN is reported as UNKNOWN (never silently NORMAL). Routing stays
    safe under UNKNOWN: it reduces no capability (see router.py).
  - EXHAUSTED can come from telemetry, from a provider error that matches
    an exhaustion pattern, or from the owner. It expires to UNKNOWN after a
    retry window so a stale flag cannot block the bridge forever.
  - An owner-set level is never overwritten by the automatic probe.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models import Provider, ProviderQuota, QuotaBand
from router import quota_band_for_percent

DEFAULT_RETRY_HOURS = 6.0

# Availability level -> conservation band when no explicit band is recorded.
LEVEL_DEFAULT_BAND: dict[ProviderQuota, QuotaBand] = {
    ProviderQuota.UNKNOWN: QuotaBand.UNKNOWN,
    ProviderQuota.NORMAL: QuotaBand.NORMAL,
    ProviderQuota.CONSTRAINED: QuotaBand.RESERVE,
    ProviderQuota.EXHAUSTED: QuotaBand.EMERGENCY,
}

# Owner-declared band -> availability level (any non-NORMAL band is CONSTRAINED).
BAND_LEVEL: dict[QuotaBand, ProviderQuota] = {
    QuotaBand.UNKNOWN: ProviderQuota.UNKNOWN,
    QuotaBand.NORMAL: ProviderQuota.NORMAL,
    QuotaBand.CONSERVE: ProviderQuota.CONSTRAINED,
    QuotaBand.RESERVE: ProviderQuota.CONSTRAINED,
    QuotaBand.EMERGENCY: ProviderQuota.CONSTRAINED,
}
_TAIL_BYTES = 400_000
_EXHAUSTION_RE = re.compile(
    r"(usage|rate)[ _-]?limit|quota|\b429\b|too many requests|"
    r"out of (credits|usage)|insufficient (credits|quota)|credit balance",
    re.IGNORECASE,
)


def detect_provider_exhaustion(text: str) -> bool:
    """Whether provider diagnostics look like a quota/rate-limit stop."""

    return bool(_EXHAUSTION_RE.search(text or ""))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


class QuotaBoard:
    """Persisted per-provider level with source and expiry."""

    def __init__(self, path: Path, now_fn=_now) -> None:
        self.path = Path(path)
        self.now_fn = now_fn

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Quota board is corrupt: {self.path}") from exc

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            Path(temp).replace(self.path)
        except Exception:
            Path(temp).unlink(missing_ok=True)
            raise

    def entry(self, provider: Provider) -> dict:
        data = self._read()
        entry = data.get(provider.value) or {
            "level": ProviderQuota.UNKNOWN.value,
            "reason": "no telemetry",
            "source": "default",
            "retry_after": None,
        }
        retry_after = entry.get("retry_after")

        if (
            entry["level"] == ProviderQuota.EXHAUSTED.value
            and retry_after
            and datetime.fromisoformat(retry_after) <= self.now_fn()
        ):
            return {
                "level": ProviderQuota.UNKNOWN.value,
                "reason": "exhaustion retry window elapsed; state unverified",
                "source": "expiry",
                "retry_after": None,
            }

        return entry

    def level(self, provider: Provider) -> ProviderQuota:
        return ProviderQuota(self.entry(provider)["level"])

    def levels(self) -> dict[Provider, ProviderQuota]:
        return {p: self.level(p) for p in Provider}

    def available(self, provider: Provider) -> bool:
        return self.level(provider) is not ProviderQuota.EXHAUSTED

    def band(self, provider: Provider) -> QuotaBand:
        """Conservation band (POLICY.md sec. 8): explicit band, else from the level."""

        entry = self.entry(provider)
        explicit = entry.get("band")

        if explicit:
            return QuotaBand(explicit)

        return LEVEL_DEFAULT_BAND[ProviderQuota(entry["level"])]

    def bands(self) -> dict[Provider, QuotaBand]:
        return {p: self.band(p) for p in Provider}

    def remaining_percent(self, provider: Provider) -> float | None:
        value = self.entry(provider).get("remaining_percent")
        return None if value is None else float(value)

    def set_band(self, provider: Provider, band: QuotaBand, *, reason: str, source: str) -> None:
        """Record a conservation band (owner-declared or telemetry-derived)."""

        self.set(provider, BAND_LEVEL[band], reason=reason, source=source, band=band)

    def set(
        self,
        provider: Provider,
        level: ProviderQuota,
        *,
        reason: str,
        source: str,
        retry_after_hours: float | None = None,
        band: QuotaBand | None = None,
        remaining_percent: float | None = None,
    ) -> None:
        data = self._read()
        retry_after = None

        if level is ProviderQuota.EXHAUSTED:
            hours = DEFAULT_RETRY_HOURS if retry_after_hours is None else retry_after_hours
            retry_after = _iso(self.now_fn() + timedelta(hours=hours))

        data[provider.value] = {
            "level": level.value,
            "reason": reason,
            "source": source,
            "retry_after": retry_after,
            "updated_at": _iso(self.now_fn()),
        }

        if band is not None:
            data[provider.value]["band"] = band.value

        if remaining_percent is not None:
            data[provider.value]["remaining_percent"] = round(float(remaining_percent), 1)

        self._write(data)

    def clear(self, provider: Provider) -> None:
        data = self._read()
        data.pop(provider.value, None)
        self._write(data)

    def mark_exhausted_from_error(self, provider: Provider, detail: str) -> bool:
        """Record exhaustion revealed by a provider failure (no-op if not one)."""

        if not detect_provider_exhaustion(detail):
            return False

        return self.mark_exhausted(
            provider, f"provider error: {detail.strip()[-160:]}"
        )

    def mark_exhausted(self, provider: Provider, reason: str) -> bool:
        """Flag a provider EXHAUSTED from an observed stop (never over an owner level)."""

        if self.entry(provider).get("source") == "owner":
            return False

        self.set(provider, ProviderQuota.EXHAUSTED, reason=reason, source="error")
        return True

    def refresh_from_telemetry(self, sessions_root: Path | None = None) -> dict[Provider, ProviderQuota]:
        """Apply real Codex telemetry; never overwrites an owner-set level."""

        current = self.entry(Provider.CODEX)

        if current.get("source") != "owner":
            level, reason, remaining = codex_quota_reading(sessions_root, now=self.now_fn())

            if level is ProviderQuota.UNKNOWN and current.get("source") == "error" \
                    and current["level"] == ProviderQuota.EXHAUSTED.value:
                pass  # keep an error-derived exhaustion until it expires
            else:
                self.set(
                    Provider.CODEX, level, reason=reason, source="telemetry",
                    band=None if remaining is None else quota_band_for_percent(remaining),
                    remaining_percent=remaining,
                )

        return self.levels()


def codex_quota_probe(
    sessions_root: Path | None = None,
    *,
    now: datetime | None = None,
) -> tuple[ProviderQuota, str]:
    """(level, reason) from Codex's own most recent rate_limits record (read-only)."""

    level, reason, _ = codex_quota_reading(sessions_root, now=now)
    return level, reason


def codex_quota_reading(
    sessions_root: Path | None = None,
    *,
    now: datetime | None = None,
) -> tuple[ProviderQuota, str, float | None]:
    """(level, reason, remaining_percent) - remaining is the tightest live window."""

    now = now or _now()
    root = Path(sessions_root) if sessions_root else Path.home() / ".codex" / "sessions"

    try:
        files = sorted(root.rglob("rollout-*.jsonl"), key=lambda p: p.stat().st_mtime)
    except OSError:
        files = []

    for path in reversed(files[-12:]):
        record = _last_rate_limits(path)

        if record is None:
            continue

        limits, stamp = record
        return _classify_limits(limits, stamp, now)

    return ProviderQuota.UNKNOWN, "no Codex rate_limits telemetry found", None


def _last_rate_limits(path: Path) -> tuple[dict, datetime] | None:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - _TAIL_BYTES))
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None

    for line in reversed(tail.splitlines()):
        if '"rate_limits"' not in line:
            continue
        try:
            obj = json.loads(line)
            limits = obj["payload"]["rate_limits"]
            stamp = datetime.fromisoformat(obj["timestamp"].replace("Z", "+00:00"))
        except (ValueError, KeyError, TypeError):
            continue
        if isinstance(limits, dict) and limits.get("secondary") is not None:
            return limits, stamp

    return None


def _classify_limits(
    limits: dict, stamp: datetime, now: datetime
) -> tuple[ProviderQuota, str, float | None]:
    live: list[tuple[str, float]] = []
    notes: list[str] = []

    for name in ("primary", "secondary"):
        window = limits.get(name)

        if not isinstance(window, dict) or window.get("used_percent") is None:
            continue

        resets_at = window.get("resets_at")

        if resets_at is not None and float(resets_at) <= now.timestamp():
            notes.append(f"{name} window already reset (stale reading ignored)")
            continue

        live.append((name, float(window["used_percent"])))

    if not live:
        return (
            ProviderQuota.UNKNOWN,
            "Codex telemetry present but every window has reset: " + "; ".join(notes),
            None,
        )

    summary = ", ".join(f"{n} used {u:.0f}%" for n, u in live)
    age_h = (now - stamp).total_seconds() / 3600
    detail = f"Codex telemetry ({summary}; reading {age_h:.1f}h old)"

    remaining = 100.0 - max(u for _, u in live)

    if any(u >= 97 for _, u in live):
        return ProviderQuota.EXHAUSTED, detail, remaining

    # POLICY.md sec. 8: anything below 60% remaining is CONSTRAINED (CONSERVE/RESERVE/EMERGENCY
    # bands are derived from the percentage by the router).
    if quota_band_for_percent(remaining) is not QuotaBand.NORMAL:
        return ProviderQuota.CONSTRAINED, detail, remaining

    return ProviderQuota.NORMAL, detail, remaining


def _self_test() -> None:
    import shutil

    temp = Path(tempfile.mkdtemp(prefix="vector_quota_test_"))

    def rollout(name: str, used_primary: float, used_weekly: float, resets_in_s: float = 3600, age_s: float = 60) -> Path:
        stamp = datetime.now(timezone.utc) - timedelta(seconds=age_s)
        record = {
            "timestamp": _iso(stamp).replace("+00:00", "Z"),
            "type": "event_msg",
            "payload": {"rate_limits": {
                "primary": {"used_percent": used_primary, "window_minutes": 300, "resets_at": time.time() + resets_in_s},
                "secondary": {"used_percent": used_weekly, "window_minutes": 10080, "resets_at": time.time() + resets_in_s * 100},
            }},
        }
        path = temp / "sessions" / "2026" / "09" / f"rollout-{name}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"noise": 1}) + "\n" + json.dumps(record) + "\n", encoding="utf-8")
        return path

    try:
        root = temp / "sessions"

        # No telemetry -> UNKNOWN, honestly.
        level, why = codex_quota_probe(root)
        assert level is ProviderQuota.UNKNOWN and "no Codex" in why

        rollout("a", 1.0, 6.0)
        assert codex_quota_probe(root)[0] is ProviderQuota.NORMAL
        assert codex_quota_reading(root)[2] == 94.0, "remaining is the tightest live window"
        rollout("b", 10.0, 75.0)
        os.utime(next(root.rglob("rollout-b.jsonl")), None)
        assert codex_quota_probe(root)[0] is ProviderQuota.CONSTRAINED
        rollout("c", 99.0, 40.0)
        assert codex_quota_probe(root)[0] is ProviderQuota.EXHAUSTED
        rollout("d", 5.0, 99.0)
        assert codex_quota_probe(root)[0] is ProviderQuota.EXHAUSTED

        # A window that already reset is stale and must not read as exhausted.
        rollout("e", 99.0, 99.0, resets_in_s=-10)
        stale_level, stale_why = codex_quota_probe(root)
        assert stale_level is ProviderQuota.UNKNOWN and "reset" in stale_why

        # Board: default UNKNOWN, honest reasons, no Claude telemetry.
        clock = {"now": datetime.now(timezone.utc)}
        board = QuotaBoard(temp / "quota.json", now_fn=lambda: clock["now"])
        assert board.level(Provider.CLAUDE) is ProviderQuota.UNKNOWN
        assert board.levels() == {Provider.CODEX: ProviderQuota.UNKNOWN, Provider.CLAUDE: ProviderQuota.UNKNOWN}

        rollout("f", 2.0, 8.0)
        assert board.refresh_from_telemetry(root)[Provider.CODEX] is ProviderQuota.NORMAL
        assert board.level(Provider.CLAUDE) is ProviderQuota.UNKNOWN

        # Exhaustion detection from provider errors + expiry.
        assert detect_provider_exhaustion("ERROR: You've hit your usage limit")
        assert detect_provider_exhaustion("HTTP 429 Too Many Requests")
        assert not detect_provider_exhaustion("AssertionError: expected 3")
        assert board.mark_exhausted_from_error(Provider.CLAUDE, "Claude usage limit reached")
        assert not board.available(Provider.CLAUDE)
        assert not board.mark_exhausted_from_error(Provider.CODEX, "SyntaxError in file")
        clock["now"] += timedelta(hours=DEFAULT_RETRY_HOURS + 1)
        assert board.level(Provider.CLAUDE) is ProviderQuota.UNKNOWN, "exhaustion expires"
        assert board.available(Provider.CLAUDE)

        # POLICY.md sec. 8 bands come from the real percentage (remaining = 100 - used).
        for name, used_primary, used_weekly, expected in (
            ("h1", 5.0, 30.0, QuotaBand.NORMAL),        # 70% remaining
            ("h2", 5.0, 45.0, QuotaBand.CONSERVE),      # 55%
            ("h3", 5.0, 75.0, QuotaBand.RESERVE),       # 25%
            ("h4", 5.0, 90.0, QuotaBand.EMERGENCY),     # 10%
        ):
            rollout(name, used_primary, used_weekly)
            os.utime(next(root.rglob(f"rollout-{name}.jsonl")), None)
            board.refresh_from_telemetry(root)
            assert board.band(Provider.CODEX) is expected, (name, board.band(Provider.CODEX))
            assert board.remaining_percent(Provider.CODEX) == 100.0 - used_weekly

        assert board.band(Provider.CLAUDE) is QuotaBand.UNKNOWN, "no Claude telemetry: UNKNOWN band"
        assert board.bands() == {Provider.CODEX: QuotaBand.EMERGENCY, Provider.CLAUDE: QuotaBand.UNKNOWN}

        # Owner-declared band (the standing "Codex ~1% weekly" instruction) beats telemetry.
        board.set_band(Provider.CODEX, QuotaBand.EMERGENCY, reason="owner: ~1% weekly", source="owner")
        rollout("h5", 1.0, 2.0)
        os.utime(next(root.rglob("rollout-h5.jsonl")), None)
        board.refresh_from_telemetry(root)
        assert board.band(Provider.CODEX) is QuotaBand.EMERGENCY and board.entry(Provider.CODEX)["source"] == "owner"
        assert board.level(Provider.CODEX) is ProviderQuota.CONSTRAINED and board.available(Provider.CODEX)
        board.clear(Provider.CODEX)
        assert board.band(Provider.CODEX) is QuotaBand.UNKNOWN

        # Owner-set level survives probe and error signals.
        board.set(Provider.CODEX, ProviderQuota.CONSTRAINED, reason="owner says so", source="owner")
        rollout("g", 1.0, 1.0)
        assert board.refresh_from_telemetry(root)[Provider.CODEX] is ProviderQuota.CONSTRAINED
        assert not board.mark_exhausted_from_error(Provider.CODEX, "usage limit")
        board.clear(Provider.CODEX)
        assert board.level(Provider.CODEX) is ProviderQuota.UNKNOWN

        # Error-derived exhaustion is kept when telemetry is silent.
        board.set(Provider.CODEX, ProviderQuota.EXHAUSTED, reason="err", source="error")
        assert board.refresh_from_telemetry(temp / "empty")[Provider.CODEX] is ProviderQuota.EXHAUSTED

        # Corrupt board fails closed.
        (temp / "bad.json").write_text("{nope", encoding="utf-8")
        try:
            QuotaBoard(temp / "bad.json").level(Provider.CODEX)
        except RuntimeError:
            pass
        else:
            raise AssertionError("corrupt quota board must fail closed")
    finally:
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    _self_test()
