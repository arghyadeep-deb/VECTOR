"""Regression for a repeated off-by-one Path(__file__).parent chain in
districts/interview_prep/{feedback_analyst,report_generator}.py -- each had
one extra `.parent`, which silently walked past the repo root into its
sibling directory on disk (`V.E.C.T.O.R/` instead of
`V.E.C.T.O.R/V.E.C.T.O.R. Codebase/`).

This means FeedbackAnalyst/ReportGenerator have been reading and writing real
interview data to a stray folder outside the git repo (and outside the
`VECTOR_DATA_DIR`/`VECTOR_TEST_DATA_DIR` test-isolation override every other
data_path() consumer in the codebase respects) for as long as the bug has
existed -- confirmed live: `V.E.C.T.O.R/data/interview_feedback.json` (341KB)
and `V.E.C.T.O.R/data/interview_reports/` already exist on disk, sibling to
the repo, not inside it.

districts/data_analytics/performance_benchmarker.py had the identical
off-by-one in a `sys.path.insert` for `vectorcode/src`, fixed alongside these
as the same drive-by correctness cleanup -- but it is NOT independently
regression-tested here: `ensure_paths()` (called at this module's own import
time) already puts the correct `vectorcode/src` on `sys.path`, so the buggy
extra insert was dead code with no observable behavioral effect either way.
"""
from __future__ import annotations

from pathlib import Path

from core.runtime_paths import data_path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_feedback_analyst_data_file_resolves_inside_repo():
    """_data_file must track core.runtime_paths.data_path() -- the same
    VECTOR_DATA_DIR/VECTOR_TEST_DATA_DIR-aware root every other data_path()
    consumer uses -- not a hardcoded Path(__file__) chain that silently
    computes a different, unrelated directory."""
    import districts.interview_prep.feedback_analyst as mod

    agent = mod.FeedbackAnalyst()
    expected = data_path("interview_feedback.json").resolve()
    resolved = agent._data_file.resolve()
    assert resolved == expected, (
        f"_data_file {resolved} does not match data_path() root {expected} -- "
        "the off-by-one .parent chain regressed"
    )


def test_report_generator_reports_dir_resolves_inside_repo():
    import districts.interview_prep.report_generator as mod

    agent = mod.ReportGenerator()
    expected = data_path("interview_reports").resolve()
    resolved = agent._reports_dir.resolve()
    assert resolved == expected, (
        f"_reports_dir {resolved} does not match data_path() root {expected} -- "
        "the off-by-one .parent chain regressed"
    )


if __name__ == "__main__":
    test_feedback_analyst_data_file_resolves_inside_repo()
    test_report_generator_reports_dir_resolves_inside_repo()
    print("✅ test_districts_off_by_one_parent_paths.py OK")
