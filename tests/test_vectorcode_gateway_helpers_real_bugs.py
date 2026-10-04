"""Regression for vectorcode/src/gateway/platforms/helpers.py.

Two real bugs fixed this cycle:

1. `from loguru import logger` was trapped inside the module docstring
   (never executed as code). The real logger binding was
   `import logging` + `logger = logging.getLogger(__name__)` -- a
   CLAUDE.md rule-6 violation (stdlib logging instead of loguru) shared
   by every helper class in this shared module.

2. ThreadParticipationTracker._load()/_save() "fail-open destroys data":
   if the JSON state file exists but fails to parse, _load() returned an
   empty set, indistinguishable from "no file yet". The next mark() call
   then called _save(), silently overwriting the real file and
   destroying every previously tracked thread id. Same bug class as
   vector_cli/vault_cmd.py and gateway/platforms/webhook.py this cycle.
   Fix: _load() now sets a _load_failed flag on parse failure, and
   _save() refuses to write while that flag is set.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import vector_constants
from gateway.platforms import helpers
from gateway.platforms.helpers import ThreadParticipationTracker


def test_module_uses_loguru_not_stdlib_logging():
    assert "logging" not in dir(helpers) or not hasattr(helpers, "logging")
    import inspect
    src = inspect.getsource(helpers)
    assert "import logging" not in src
    assert "from loguru import logger" in src


def test_load_of_missing_file_does_not_set_failed_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(vector_constants, "get_vector_home", lambda: tmp_path)
    tracker = ThreadParticipationTracker("unit_test_platform")
    assert tracker._load_failed is False
    assert tracker._threads == set()


def test_mark_persists_normally_when_file_is_valid(tmp_path, monkeypatch):
    monkeypatch.setattr(vector_constants, "get_vector_home", lambda: tmp_path)
    state_file = tmp_path / "unit_test_platform_threads.json"
    state_file.write_text(json.dumps(["existing-thread-1", "existing-thread-2"]), encoding="utf-8")

    tracker = ThreadParticipationTracker("unit_test_platform")
    assert tracker._load_failed is False
    tracker.mark("new-thread-3")

    saved = set(json.loads(state_file.read_text(encoding="utf-8")))
    assert saved == {"existing-thread-1", "existing-thread-2", "new-thread-3"}


def test_corrupt_file_does_not_get_silently_overwritten_on_mark(tmp_path, monkeypatch):
    # This is the actual regression: a corrupt state file used to be
    # indistinguishable from "no file yet", so the very next mark() call
    # would overwrite it with just the newly marked thread, destroying
    # every previously tracked thread id.
    monkeypatch.setattr(vector_constants, "get_vector_home", lambda: tmp_path)
    state_file = tmp_path / "unit_test_platform_threads.json"
    state_file.write_text("{not valid json!!", encoding="utf-8")

    tracker = ThreadParticipationTracker("unit_test_platform")
    assert tracker._load_failed is True
    assert tracker._threads == set()

    tracker.mark("new-thread")

    # The corrupt file must be left untouched -- _save() must refuse to
    # run while _load_failed is set, instead of overwriting it.
    assert state_file.read_text(encoding="utf-8") == "{not valid json!!"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
