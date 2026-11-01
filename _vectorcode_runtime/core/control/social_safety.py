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
  5. CONTENT DEDUP — refuse to re-post the exact same media+caption within
     `content_dedup_hours` (default 72h). Time/cap/spacing rules alone don't
     catch this: a retry, a double-tap, or an orchestrator replay calling
     post_instagram(same_reel_path, same_caption) twice is a *different* post
     as far as warm-up/cap/spacing are concerned, but produces two real,
     duplicate, ban-risk-raising posts on the platform (2026-07-30 audit
     finding, Section 5.3). See _content_signature()/can_post_now().

`can_post_now()` returns an allow/deny decision with a human-readable reason.
Post history + account-created dates live in a small JSON state file (per handle),
not the encrypted memory DB — this is operational metadata, not owner memory.

Pure stdlib + config. No network, no device calls. Fully unit-testable.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import hashlib
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


def _content_signature(media_path: str, caption: str) -> str:
    """Fingerprint of *what* would be posted (not *when*) — used to catch
    duplicate-content resubmission (retries/double-taps/replays) independent
    of the time-based rules above. Includes file size+mtime when the media
    file is reachable so a reused temp path with genuinely new content isn't
    mistaken for a repeat; falls back to path+caption alone if the file can't
    be stat'd (e.g. remote/device-only path)."""
    size = mtime = ""
    try:
        p = Path(media_path) if media_path else None
        if p and p.exists():
            st = p.stat()
            size, mtime = str(st.st_size), str(int(st.st_mtime))
    except Exception:
        pass
    raw = f"{media_path or ''}|{(caption or '').strip()}|{size}|{mtime}"
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _post_entries(acc: dict) -> list[dict]:
    """Normalize an account's 'posts' list to dicts with 'at' and optional
    'sig' keys. Older state files store plain ISO-string entries (pre-dedup
    format) — those normalize to {'at': <str>, 'sig': None} so old history
    keeps working without a migration step."""
    out = []
    for p in acc.get("posts", []):
        if isinstance(p, dict):
            out.append({"at": p.get("at", ""), "sig": p.get("sig")})
        else:
            out.append({"at": p, "sig": None})
    return out


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


def can_post_now(handle: str, at: datetime | None = None,
                  media_path: str = "", caption: str = "") -> PostDecision:
    """Decide whether `handle` may post at time `at` (default now), per the
    warm-up / daily-cap / spacing / content-dedup rules. Does NOT enforce
    jitter (that shapes the schedule, not the allow/deny) — use
    jittered_time() for that.

    `media_path`/`caption` are optional but should be passed by every real
    caller (2026-07-30 audit fix): without them, calling
    post_instagram(same_reel_path, same_caption) twice sails through every
    other rule (it's a different timestamp, still under the daily cap, etc.)
    and posts the identical content twice. See _content_signature()."""
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

    entries = _post_entries(acc)

    if media_path or caption:
        sig = _content_signature(media_path, caption)
        dedup_hours = float(cfg.get("content_dedup_hours", 72))
        if dedup_hours > 0:
            for e in entries:
                if e.get("sig") != sig:
                    continue
                try:
                    e_at = datetime.fromisoformat(e["at"])
                except Exception:
                    continue
                age_h = (now - e_at).total_seconds() / 3600
                if age_h < dedup_hours:
                    ready = e_at + timedelta(hours=dedup_hours)
                    return PostDecision(False,
                        f"duplicate content already posted {age_h:.1f}h ago "
                        f"(same media+caption) — not reposting identical content "
                        f"within the {dedup_hours:.0f}h dedup window",
                        ready.isoformat())

    posts = [datetime.fromisoformat(e["at"]) for e in entries]
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


def record_post(handle: str, at: datetime | None = None,
                 media_path: str = "", caption: str = "") -> None:
    """Log a successful post so the cap/spacing/dedup rules see it. Keeps last 60.
    Pass the same media_path/caption given to can_post_now() so the content
    signature is recorded and future duplicate attempts are caught."""
    now = at or _now()
    sig = _content_signature(media_path, caption) if (media_path or caption) else None
    state = _load_state()
    acc = state.setdefault(handle, {"created": now.isoformat(), "posts": []})
    acc["posts"] = _post_entries(acc)
    acc["posts"].append({"at": now.isoformat(), "sig": sig})
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

    # content dedup: same media+caption, different (fresh) account state → denied as duplicate
    st = _load_state(); st[h] = {"created": old, "posts": []}; _save_state(st)
    record_post(h, media_path="/tmp/__selftest_reel.mp4", caption="same caption")
    d3 = can_post_now(h, media_path="/tmp/__selftest_reel.mp4", caption="same caption")
    assert not d3.allowed and "duplicate content" in d3.reason, d3
    # different content on the same (already-capped) account → cap reason, not dedup
    d4 = can_post_now(h, media_path="/tmp/__selftest_reel.mp4", caption="a totally different caption")
    assert not d4.allowed and "duplicate content" not in d4.reason, d4

    # jitter in range
    j = jittered_delay_seconds()
    assert 0 <= j <= int(CONFIG["growth"].get("post_jitter_minutes", 90)) * 60

    st = _load_state(); st.pop(h, None); _save_state(st)  # cleanup
    print("social_safety OK")
