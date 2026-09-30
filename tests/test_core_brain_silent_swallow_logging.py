"""Regression test for a real, previously-silent bug across 4 core/brain/
files (epistemic_tracker.py, goal_system.py x2, person_model.py,
suggestion_queue.py) found during the Phase 3 whole-repo audit's Claude/Codex
50/50 split, deep-verify pass on core/brain/, 2026-09-30.

A prior automated pass had added `logger.warning(...)` calls to previously
bare `except: pass` blocks -- but two distinct mistakes meant the actual
exception text never reached the log, defeating the point of the fix:

1. epistemic_tracker.py (_log_staleness, close) and goal_system.py
   (_prune_expired's two except blocks) used `except Exception:` with no
   `as e` binding at all, then logged the generic literal string
   "[VECTOR] silent swallow" -- no exception detail was even captured.
2. person_model.py (close) and suggestion_queue.py (close) DID capture the
   exception as `e`, but logged it with `logger.warning("... %s", e)`.
   loguru's message formatting uses str.format() semantics (`{}`), not
   %-style -- `"...: %s".format(e)` silently returns the string unchanged,
   with `%s` printed literally and `e` dropped. Verified directly:
   `"...: %s".format("boom")` == "...: %s" (no substitution, no error).

Fixed: all 6 sites now use loguru's `{}` placeholder with the caught
exception actually captured and interpolated.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _rendered(call_args) -> str:
    """Mimic loguru's own message.format(*args) rendering for a captured
    (args, kwargs) tuple from a patched logger.warning call."""
    args, kwargs = call_args
    msg, *fmt_args = args
    return msg.format(*fmt_args)


def test_epistemic_tracker_close_logs_real_exception_text():
    from core.brain.epistemic_tracker import EpistemicTracker
    import core.brain.epistemic_tracker as mod

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = f.name
    et = EpistemicTracker(db_path=db)
    real_conn = et._conn

    fake_conn = MagicMock(wraps=real_conn)
    fake_conn.close.side_effect = RuntimeError("boom-close")
    et._conn = fake_conn

    captured = []
    with patch.object(mod.logger, "warning", side_effect=lambda *a, **k: captured.append((a, k))):
        et.close()

    assert len(captured) == 1
    rendered = _rendered(captured[0])
    assert "%s" not in rendered
    assert "boom-close" in rendered
    real_conn.close()
    Path(db).unlink(missing_ok=True)


def test_epistemic_tracker_log_staleness_logs_real_exception_text():
    from core.brain.epistemic_tracker import EpistemicTracker
    import core.brain.epistemic_tracker as mod

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db = f.name
    et = EpistemicTracker(db_path=db)

    real_conn = et._conn
    fake_conn = MagicMock(wraps=real_conn)
    fake_conn.execute.side_effect = RuntimeError("boom-staleness")
    et._conn = fake_conn

    captured = []
    with patch.object(mod.logger, "warning", side_effect=lambda *a, **k: captured.append((a, k))):
        et._log_staleness("some_claim", "ttl_expired")

    assert len(captured) == 1
    rendered = _rendered(captured[0])
    assert "%s" not in rendered
    assert "boom-staleness" in rendered
    real_conn.close()
    Path(db).unlink(missing_ok=True)


def test_goal_system_prune_expired_logs_real_parse_error():
    from core.brain.goal_system import GoalSystem
    import core.brain.goal_system as mod

    gs = GoalSystem.__new__(GoalSystem)
    gs._goals = [{
        "id": "g1", "title": "bad due date", "status": "active",
        "due_date": "not-a-real-date", "horizon": "SHORT",
    }]
    gs._persist = lambda: None

    captured = []
    with patch.object(mod.logger, "warning", side_effect=lambda *a, **k: captured.append((a, k))):
        gs._prune_expired()

    assert len(captured) >= 1
    rendered = _rendered(captured[0])
    assert "%s" not in rendered
    assert "g1" in rendered


def test_person_model_close_logs_real_exception_text():
    from core.brain.person_model import PersonModel
    import core.brain.person_model as mod

    pm = PersonModel(db_path=str(Path(tempfile.mkdtemp()) / "pm.db"))
    fake_conn = MagicMock(wraps=pm._conn)
    fake_conn.close.side_effect = RuntimeError("boom-person")
    pm._conn = fake_conn

    captured = []
    with patch.object(mod.logger, "warning", side_effect=lambda *a, **k: captured.append((a, k))):
        pm.close()

    assert len(captured) == 1
    rendered = _rendered(captured[0])
    assert "%s" not in rendered
    assert "boom-person" in rendered


def test_suggestion_queue_close_logs_real_exception_text():
    from core.brain.suggestion_queue import SuggestionQueue
    import core.brain.suggestion_queue as mod

    sq = SuggestionQueue(db_path=str(Path(tempfile.mkdtemp()) / "sq.db"))
    fake_conn = MagicMock(wraps=sq._conn)
    fake_conn.close.side_effect = RuntimeError("boom-suggestion")
    sq._conn = fake_conn

    captured = []
    with patch.object(mod.logger, "warning", side_effect=lambda *a, **k: captured.append((a, k))):
        sq.close()

    assert len(captured) == 1
    rendered = _rendered(captured[0])
    assert "%s" not in rendered
    assert "boom-suggestion" in rendered


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
