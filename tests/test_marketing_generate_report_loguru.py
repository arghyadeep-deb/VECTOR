"""Regression for districts/marketing/ads/scripts/generate_report.py using
stdlib logging.getLogger() instead of loguru (CLAUDE.md rule 6), plus two
placeholder "[VECTOR] silent swallow"/"suppressed exception" messages that
discarded the real exception text. reportlab/matplotlib aren't installed in
every environment (the module calls sys.exit(1) on import if missing), so
this checks the source text directly rather than importing the module --
the same technique used by other source-lock regression tests this cycle
(e.g. tests/training/test_self_improvement_cycle.py's eval-gate check).
"""
from pathlib import Path

_SRC = (
    Path(__file__).resolve().parents[1]
    / "districts" / "marketing" / "ads" / "scripts" / "generate_report.py"
).read_text(encoding="utf-8")


def test_no_stdlib_logging_import():
    assert "import logging" not in _SRC
    assert "logging.basicConfig" not in _SRC
    assert "logging.getLogger" not in _SRC


def test_uses_loguru():
    assert "from loguru import logger" in _SRC


def test_no_placeholder_exception_messages():
    assert "silent swallow" not in _SRC
    assert "suppressed exception" not in _SRC


def test_verbose_flag_still_configures_debug_output():
    assert 'logger.add(sys.stderr, level="DEBUG")' in _SRC


if __name__ == "__main__":
    test_no_stdlib_logging_import()
    test_uses_loguru()
    test_no_placeholder_exception_messages()
    test_verbose_flag_still_configures_debug_output()
    print("OK test_marketing_generate_report_loguru.py")
