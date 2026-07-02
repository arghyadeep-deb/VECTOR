"""Coding Companion — stuck detection + vectorcode session marker (2026-07-02).

Owner runs vectorcode CLI on project B while VECTOR runs autonomously on
project A; VECTOR watches the screen and proactively helps when the owner is
stuck. These tests cover the detector state machine and the session marker
(pid-alive semantics) with a simulated clock — no screen, no LLM.
"""

import sys
import json
import os
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.sensing import stuck_detector as sd
from core.sensing.stuck_detector import (
    StuckDetector, extract_error_lines, error_signature,
    write_session_marker, clear_session_marker, get_active_session,
)

ERR = "Traceback (most recent call last):\n  File x\nTypeError: cannot unpack non-iterable int"
ERR2 = "npm ERR! code ERESOLVE\nnpm ERR! unable to resolve dependency tree"


@pytest.fixture
def clock():
    t = {"now": 1000.0}
    return t


@pytest.fixture
def det(clock):
    return StuckDetector(min_samples=3, after_min=1.0, cooldown_min=10.0,
                         clock=lambda: clock["now"])


def _tick(clock, det, text, dt=30.0):
    clock["now"] += dt
    return det.feed(text)


# ── error extraction ─────────────────────────────────────────────────────────

def test_extract_error_lines_finds_errors():
    lines = extract_error_lines(ERR)
    assert any("TypeError" in ln for ln in lines)
    assert extract_error_lines("all tests passed\nclean output") == []


def test_signature_stable_across_volatile_bits():
    a = error_signature(["TypeError at line 42 in 0xdeadbeef"])
    b = error_signature(["TypeError at line 97 in 0xcafebabe"])
    assert a == b  # line numbers / addresses normalized out


def test_signature_differs_for_different_errors():
    assert error_signature(extract_error_lines(ERR)) != \
        error_signature(extract_error_lines(ERR2))


# ── state machine ────────────────────────────────────────────────────────────

def test_not_stuck_before_thresholds(det, clock):
    assert _tick(clock, det, ERR) is None
    assert _tick(clock, det, ERR) is None


def test_stuck_after_persistence(det, clock):
    _tick(clock, det, ERR)
    _tick(clock, det, ERR)
    evt = _tick(clock, det, ERR)  # 3rd sample, 1.5 min
    assert evt is not None
    assert evt["samples"] == 3
    assert evt["since_min"] >= 1.0
    assert any("TypeError" in ln for ln in evt["error_lines"])


def test_clean_screen_resets_streak(det, clock):
    _tick(clock, det, ERR)
    _tick(clock, det, ERR)
    _tick(clock, det, "all green, 512 tests passed")   # recovered
    assert _tick(clock, det, ERR) is None               # streak restarted
    assert _tick(clock, det, ERR) is None


def test_different_error_is_progress(det, clock):
    _tick(clock, det, ERR)
    _tick(clock, det, ERR)
    _tick(clock, det, ERR2)   # new error — old streak dropped
    assert _tick(clock, det, ERR2) is None  # ERR2 streak only at 2


def test_cooldown_prevents_nagging(det, clock):
    for _ in range(3):
        evt = _tick(clock, det, ERR)
    assert evt is not None
    # Still erroring right after the nudge — silence during cooldown.
    for _ in range(5):
        assert _tick(clock, det, ERR) is None
    # After the 10-min cooldown the SAME error may nudge again.
    clock["now"] += 10 * 60
    for _ in range(3):
        evt2 = _tick(clock, det, ERR)
    assert evt2 is not None


def test_no_trigger_on_clean_text(det, clock):
    for _ in range(10):
        assert _tick(clock, det, "writing docs, everything fine") is None


def test_feed_never_raises(det):
    assert det.feed(None) is None  # type: ignore[arg-type]


# ── session marker ───────────────────────────────────────────────────────────

@pytest.fixture
def marker(tmp_path, monkeypatch):
    path = tmp_path / "vc_session.json"
    monkeypatch.setattr(sd, "_marker_path", lambda: path)
    return path


def test_marker_roundtrip(marker):
    write_session_marker("C:/some/other/project")
    sess = get_active_session()
    assert sess is not None
    assert sess["project"] == "C:/some/other/project"
    assert sess["pid"] == os.getpid()
    clear_session_marker()
    assert get_active_session() is None


def test_stale_marker_dead_pid_ignored(marker):
    marker.write_text(json.dumps(
        {"pid": 999999999, "project": "X", "started_at": "2026-01-01"}),
        encoding="utf-8")
    assert get_active_session() is None  # dead pid → no phantom session


def test_corrupt_marker_ignored(marker):
    marker.write_text("{not json", encoding="utf-8")
    assert get_active_session() is None


def test_no_marker_no_session(marker):
    assert get_active_session() is None


if __name__ == "__main__":
    # real test, no mocks
    ok = bool(extract_error_lines(ERR))
    print("✅ test_stuck_detector OK" if ok else "❌ FAILED")
