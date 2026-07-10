"""
core/control/social_safety.py — ban-safety gate for social posting.

The automation VECTOR uses (real device, real app taps, residential IP) is the
LOWEST-ban-risk method. The residual risk is behavioural: a NEW account that posts
on a rigid machine schedule looks like a bot. This gate encodes the rules that keep
posting human-shaped:

  1. WARM-UP — refuse to post until the account is `warmup_days` old.
  2. DAILY CAP — at most `max_posts_per_day` per account.
  3. SPACING — at least `min_hours_between_posts` since the last post.
  4. JITTER — never post at an exact clock time; offset by a random ±jitter.

`can_post_now()` returns an allow/deny decision with a human-readable reason.
Post history + account-created dates live in a small JSON state file (per handle),
not the encrypted memory DB — this is operational metadata, not owner memory.

Pure stdlib + config. No network, no device calls. Fully unit-testable.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from loguru import logger

from core.config import CONFIG

_STATE_PATH = Path.home() / ".vector_ca" / "social" / "post_history.json"


@dataclass
class PostDecision:
    allowed: bool
    reason: str
    next_allowed_at: str = ""   # ISO time when the next post becomes allowed (if denied)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_state() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
        tmp.replace(_STATE_PATH)
    except Exception as e:
        logger.warning("[VECTOR][social_safety] state save failed: {}", e)


def _cfg() -> dict:
    return CONFIG.get("growth", {})


def register_account(handle: str, created_iso: str | None = None) -> None:
    """Record when an account was created (or first warmed). Call once per handle.
    If created_iso is omitted, 'now' is used — so a brand-new account correctly
    starts its warm-up window today."""
    state = _load_state()
    acc = state.setdefault(handle, {"created": "", "posts": []})
    if not acc.get("created"):
        acc["created"] = created_iso or _now().isoformat()
        _save_state(state)
        logger.info("[VECTOR][social_safety] registered {} created={}", handle, acc["created"])


def can_post_now(handle: str, at: datetime | None = None) -> PostDecision:
    """Decide whether `handle` may post at time `at` (default now), per the
    warm-up / daily-cap / spacing rules. Does NOT enforce jitter (that shapes the
    schedule, not the allow/deny) — use jittered_time() for that."""
    cfg = _cfg()
    now = at or _now()
    state = _load_state()
    acc = state.get(handle)

    # Unknown account → treat as brand-new starting today (safest).
    if not acc or not acc.get("created"):
        register_account(handle)
        acc = _load_state().get(handle, {"created": now.isoformat(), "posts": []})

    created = datetime.fromisoformat(acc["created"])
    warmup_days = int(cfg.get("warmup_days", 10))
    age_days = (now - created).total_seconds() / 86400
    if age_days < warmup_days:
        ready = created + timedelta(days=warmup_days)
        return PostDecision(False,
            f"account warming up: {age_days:.1f}/{warmup_days}d old — post like a human "
            f"(scroll/like/follow) first", ready.isoformat())

    posts = [datetime.fromisoformat(p) for p in acc.get("posts", [])]
    today = [p for p in posts if p.date() == now.date()]
    cap = int(cfg.get("max_posts_per_day", 1))
    if len(today) >= cap:
        tomorrow = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)
        return PostDecision(False, f"daily cap reached ({len(today)}/{cap})", tomorrow.isoformat())

    if posts:
        last = max(posts)
        min_gap = float(cfg.get("min_hours_between_posts", 6))
        gap_h = (now - last).total_seconds() / 3600
        if gap_h < min_gap:
            ready = last + timedelta(hours=min_gap)
            return PostDecision(False,
                f"too soon: {gap_h:.1f}h since last post (min {min_gap}h)", ready.isoformat())

    return PostDecision(True, f"ok — account {age_days:.0f}d old, {len(today)}/{cap} today")


def jittered_delay_seconds(seed_offset: int = 0) -> int:
    """Return a deterministic-but-varied delay (seconds) to add before posting so
    posts never land at an exact clock time. Uses the current minute + seed as the
    varier — Math.random/Date.now are avoided (VECTOR determinism rule); this is
    'human enough' without needing an RNG."""
    jitter_min = int(_cfg().get("post_jitter_minutes", 90))
    if jitter_min <= 0:
        return 0
    # Vary by wall-clock second + caller seed → spread across the ±window.
    base = (_now().second * 60 + _now().microsecond // 1000 + seed_offset * 37)
    return base % (jitter_min * 60)


def record_post(handle: str, at: datetime | None = None) -> None:
    """Log a successful post so the cap/spacing rules see it. Keeps last 60."""
    now = at or _now()
    state = _load_state()
    acc = state.setdefault(handle, {"created": now.isoformat(), "posts": []})
    acc.setdefault("posts", []).append(now.isoformat())
    acc["posts"] = acc["posts"][-60:]
    _save_state(state)
    logger.info("[VECTOR][social_safety] recorded post for {} at {}", handle, now.isoformat())


if __name__ == "__main__":
    # real test, no mocks — uses a throwaway handle so it can't touch real state
    from datetime import timezone as _tz
    h = "__selftest__"
    st = _load_state(); st.pop(h, None); _save_state(st)

    # brand-new account → warm-up denies
    d0 = can_post_now(h)
    assert not d0.allowed and "warming up" in d0.reason, d0

    # aged account, no posts → allowed
    old = (_now() - timedelta(days=30)).isoformat()
    st = _load_state(); st[h] = {"created": old, "posts": []}; _save_state(st)
    d1 = can_post_now(h)
    assert d1.allowed, d1

    # after a post → daily cap denies (cap default 1)
    record_post(h)
    d2 = can_post_now(h)
    assert not d2.allowed and "cap" in d2.reason, d2

    # jitter in range
    j = jittered_delay_seconds()
    assert 0 <= j <= int(CONFIG["growth"].get("post_jitter_minutes", 90)) * 60

    st = _load_state(); st.pop(h, None); _save_state(st)  # cleanup
    print("social_safety OK")
