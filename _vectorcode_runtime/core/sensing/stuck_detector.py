"""Coding Companion — owner-coding session awareness + stuck detection.

Two independent lanes, one machine:
  - VECTOR runs its autonomous loop on its own projects
  - the owner runs vectorcode in a terminal on a DIFFERENT project

This module gives VECTOR the awareness to keep those lanes independent and
to help proactively instead of only when asked:

1. **Session marker** — the vectorcode CLI launcher writes a marker file
   (pid + project cwd) while a session is live. VECTOR reads it to know the
   owner is actively coding: it defers its own heavy LLM ticks (one Ollama
   GPU, OLLAMA_MAX_LOADED_MODELS=1 — don't thrash the owner's model) and
   arms stuck detection. Stale markers are ignored via a pid-alive check.

2. **StuckDetector** — consumes the 30s screen-OCR samples from _sense_tick.
   If the same error signature keeps appearing across samples for several
   minutes (or the screen shows an error and stops changing), the owner is
   probably stuck → emit ONE stuck event (per-signature + global cooldowns,
   never nagging) which the loop turns into a spoken/HUD nudge with concrete
   advice.

No screen capture happens here — the loop feeds text in. Fail-open: any
error inside this module means "not stuck", never a crashed sense tick.
"""

import sys
import os
import re
import json
import time
import datetime
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger

# ── error signature extraction ───────────────────────────────────────────────

_ERROR_LINE = re.compile(
    r"(traceback|exception|error[:\s]|err!|failed|failure|fatal|panic"
    r"|undefined|cannot find|not found|no module named|unexpected token"
    r"|syntaxerror|typeerror|valueerror|keyerror|attributeerror|importerror"
    r"|assertionerror|npm err|E\d{4}|exit code [1-9])",
    re.IGNORECASE,
)

# Volatile bits stripped before hashing so line numbers / addresses / temp
# paths don't make every sample look like a new error.
_VOLATILE = re.compile(r"0x[0-9a-f]+|\d+|['\"][^'\"]{20,}['\"]")


def extract_error_lines(text: str, max_lines: int = 4) -> list[str]:
    """Salient error lines from an OCR sample (may be noisy — best effort)."""
    lines = []
    for line in (text or "").splitlines():
        line = line.strip()
        if len(line) >= 8 and _ERROR_LINE.search(line):
            lines.append(line[:200])
            if len(lines) >= max_lines:
                break
    return lines


def error_signature(error_lines: list[str]) -> str | None:
    """Stable hash of an error block (volatile parts normalized out)."""
    if not error_lines:
        return None
    normalized = "|".join(_VOLATILE.sub("#", ln.lower()) for ln in error_lines)
    return hashlib.md5(normalized.encode("utf-8", "replace")).hexdigest()[:16]


# ── vectorcode session marker ────────────────────────────────────────────────

def _marker_path() -> Path:
    try:
        from core.config import CONFIG
        return Path(CONFIG["sensing"]["vc_session_marker"])
    except Exception:
        return Path.home() / ".vector" / "vc_session.json"


def write_session_marker(project_path: str | None = None) -> None:
    """Called by the vectorcode CLI launcher on start."""
    try:
        path = _marker_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "pid": os.getpid(),
            "project": str(project_path or os.getcwd()),
            "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }), encoding="utf-8")
        logger.info(f"[VECTOR][companion] coding session marker written ({path})")
    except Exception as e:
        logger.debug(f"[VECTOR][companion] marker write failed: {e}")


def clear_session_marker() -> None:
    try:
        _marker_path().unlink(missing_ok=True)
        logger.info("[VECTOR][companion] coding session marker cleared")
    except Exception as e:
        logger.debug(f"[VECTOR][companion] marker clear failed: {e}")


def _pid_alive(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(pid)
    except Exception:
        # No psutil → trust the marker (better a false session than none).
        return True


def get_active_session() -> dict | None:
    """The owner's live vectorcode session, or None. Stale markers (dead pid)
    are ignored so a crashed CLI never leaves VECTOR in deferred mode."""
    try:
        path = _marker_path()
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not _pid_alive(int(data.get("pid", -1))):
            return None
        return data
    except Exception as e:
        logger.debug(f"[VECTOR][companion] marker read failed: {e}")
        return None


# ── stuck detection state machine ────────────────────────────────────────────

class StuckDetector:
    """Feed 30s OCR samples in; get at most one stuck event per error per
    cooldown window out.

    Trigger: the same error signature appears in >= min_samples samples AND
    has persisted for >= after_min minutes. Sample gaps (owner switched
    windows, OCR missed a frame) don't reset the streak — only a genuinely
    different error or a clean screen does.
    """

    def __init__(self, min_samples: int | None = None, after_min: float | None = None,
                 cooldown_min: float | None = None, clock=time.time):
        cfg = {}
        try:
            from core.config import CONFIG
            cfg = CONFIG.get("sensing", {})
        except Exception:
            cfg = {}
        self.min_samples = min_samples if min_samples is not None else int(cfg.get("stuck_min_samples", 4))
        self.after_min = after_min if after_min is not None else float(cfg.get("stuck_after_min", 2.0))
        self.cooldown_min = cooldown_min if cooldown_min is not None else float(cfg.get("stuck_cooldown_min", 20.0))
        self._clock = clock
        # signature -> {"first": ts, "count": n, "error_lines": [...]}
        self._streaks: dict[str, dict] = {}
        self._nudged_at: dict[str, float] = {}   # per-signature cooldown
        self._last_nudge: float | None = None    # global cooldown (half of per-sig)

    def feed(self, raw_text: str, activity: str = "") -> dict | None:
        """One OCR sample in → stuck event dict, or None."""
        try:
            now = self._clock()
            error_lines = extract_error_lines(raw_text)
            sig = error_signature(error_lines)

            if sig is None:
                # Clean screen → owner recovered; forget streaks.
                self._streaks.clear()
                return None

            streak = self._streaks.setdefault(
                sig, {"first": now, "count": 0, "error_lines": error_lines})
            streak["count"] += 1
            streak["error_lines"] = error_lines  # keep freshest OCR of it
            # A different error replacing this one is progress of a kind —
            # drop other streaks so only the persisting signature accumulates.
            for other in [s for s in self._streaks if s != sig]:
                self._streaks.pop(other, None)

            elapsed_min = (now - streak["first"]) / 60.0
            if streak["count"] < self.min_samples or elapsed_min < self.after_min:
                return None

            # Cooldowns — per signature, plus a global half-cooldown.
            _sig_at = self._nudged_at.get(sig)
            if _sig_at is not None and now - _sig_at < self.cooldown_min * 60:
                return None
            if self._last_nudge is not None and now - self._last_nudge < (self.cooldown_min / 2) * 60:
                return None

            self._nudged_at[sig] = now
            self._last_nudge = now
            logger.info(
                f"[VECTOR][companion] stuck detected — same error for "
                f"{elapsed_min:.1f}min across {streak['count']} samples")
            return {
                "signature": sig,
                "error_lines": streak["error_lines"],
                "since_min": round(elapsed_min, 1),
                "samples": streak["count"],
                "activity": activity,
            }
        except Exception as e:
            logger.debug(f"[VECTOR][companion] feed failed (treating as not stuck): {e}")
            return None


# Module singleton (loop convention)
_detector: StuckDetector | None = None


def get_stuck_detector() -> StuckDetector:
    global _detector
    if _detector is None:
        _detector = StuckDetector()
    return _detector


if __name__ == "__main__":
    # real test, no mocks — simulated clock walks the state machine
    t = [0.0]
    d = StuckDetector(min_samples=3, after_min=1.0, cooldown_min=10.0, clock=lambda: t[0])
    err = "Traceback (most recent call last):\n  ...\nTypeError: cannot unpack x"
    ok = True
    for _ in range(2):
        t[0] += 30
        ok &= d.feed(err) is None            # not enough samples yet
    t[0] += 30
    evt = d.feed(err)                         # 3rd sample, 1.5min elapsed
    ok &= evt is not None and evt["samples"] == 3
    t[0] += 30
    ok &= d.feed(err) is None                 # cooldown holds
    ok &= d.feed("all tests passed, clean") is None   # clean screen resets
    ok &= extract_error_lines("no problems here") == []
    print("✅ stuck_detector.py OK" if ok else "❌ FAILED")
