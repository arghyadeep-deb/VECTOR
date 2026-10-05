"""Regression for vectorcode/src/learning/distillation/storage/session_store.py:

the module correctly imported `from loguru import logger` at the top, then
immediately shadowed it a few lines later with
`logger = logging.getLogger(__name__)` -- the systemic bug found 20+ times
in this directory already. The one log call in _migrate() also used a
%-style placeholder, which stdlib's logger happened to render correctly
(masking the shadow bug) but would have silently failed once the shadow
was fixed and loguru took over again.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from learning.distillation.storage import session_store


def test_logger_is_loguru_not_stdlib():
    assert type(session_store.logger).__module__.startswith("loguru")


def test_no_percent_style_placeholders_remain():
    src = inspect.getsource(session_store)
    assert "suppressed sqlite3.OperationalError: %s" not in src
    assert "suppressed sqlite3.OperationalError: {}" in src


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
