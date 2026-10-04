"""Regression for vectorcode/src/vc_tools/storage/dense.py's log_dedupe_report():

used stdlib `logging` (CLAUDE.md requires loguru) with %-style placeholders
and `level: int = logging.INFO`. Confirmed live: loguru's `Logger.log()`
does NOT crash on a %-style template, but also does not substitute it --
it just prints the literal "%s"/"%d" text unformatted -- so migrating this
file to loguru (required for consistency/policy, and because this bug
class has been found 70+ times elsewhere this audit) without also fixing
the placeholders would have silently broken this function's only reason
to exist (a human-readable dedupe summary). Zero real callers exist
anywhere in the repo (confirmed via grep), so the `level` parameter type
was also changed from a stdlib numeric level to a loguru level name
(str), which is the more correct contract for loguru's own `.log()` API.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_log_dedupe_report_formats_placeholders_correctly(capsys):
    from vectorcode.src.vc_tools.storage.dense import (
        DedupeReport,
        DuplicateGroup,
        log_dedupe_report,
    )
    from loguru import logger
    import sys as _sys

    sink_output = []
    handler_id = logger.add(lambda msg: sink_output.append(str(msg)), level="DEBUG")
    try:
        report = DedupeReport(
            input_count=10,
            output_count=7,
            groups=[
                DuplicateGroup(
                    kept_index=0,
                    kept_source="a.md",
                    dropped_indices=[1, 2],
                    dropped_sources=["b.md", "c.md"],
                    distinct_files=3,
                    sample_text="hello world",
                )
            ],
        )
        log_dedupe_report(report)
    finally:
        logger.remove(handler_id)

    joined = "\n".join(sink_output)
    # The bug: a %-style template through loguru prints the literal
    # unsubstituted text, e.g. "dedupe: %d -> %d chunks".
    assert "%d" not in joined and "%s" not in joined and "%.1f" not in joined
    assert "dedupe: 10 -> 7 chunks (3 removed, 30.0%) across 1 clusters" in joined
    assert "kept a.md" in joined and "dropped 2" in joined


def test_dense_py_uses_loguru_not_stdlib_logging():
    src = Path("vectorcode/src/vc_tools/storage/dense.py").read_text(encoding="utf-8")
    assert "from loguru import logger" in src
    assert "import logging" not in src


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
