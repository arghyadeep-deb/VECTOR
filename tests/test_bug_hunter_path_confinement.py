"""Regression for BugHunter.scan_file()/find_pattern_issues()/analyze_with_llm()
reading any caller-supplied path with zero confinement. scan_file() is
directly Governor-dispatchable via run()'s params["file"] -- a secret-shaped
pattern match (SECURITY_PATTERNS) in an out-of-repo file would leak an
excerpt back in the response. analyze_with_llm() (zero real callers today)
sends the full file content to a cloud LLM provider -- same severity as the
already-fixed code_reviewer.py finding.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.coding.bug_hunter import BugHunter


def test_scan_file_rejects_path_outside_repo(tmp_path):
    hunter = BugHunter()
    outside = tmp_path / "secret.py"
    outside.write_text("api_key = 'sk-real-secret-value'\n")
    try:
        hunter.scan_file(str(outside))
        assert False, "expected FileNotFoundError for an out-of-repo path"
    except FileNotFoundError as e:
        assert "outside repo" in str(e).lower() or "not a .py file" in str(e).lower()


def test_find_pattern_issues_rejects_path_outside_repo(tmp_path):
    hunter = BugHunter()
    outside = tmp_path / "secret.py"
    outside.write_text("token = 'real-token'\n")
    try:
        hunter.find_pattern_issues(str(outside))
        assert False, "expected FileNotFoundError for an out-of-repo path"
    except FileNotFoundError:
        pass


def test_analyze_with_llm_rejects_path_outside_repo(tmp_path):
    hunter = BugHunter()
    outside = tmp_path / "secret.py"
    outside.write_text("print('hello')\n")
    try:
        hunter.analyze_with_llm(str(outside))
        assert False, "expected FileNotFoundError for an out-of-repo path"
    except FileNotFoundError:
        pass


def test_scan_file_rejects_non_py_suffix():
    hunter = BugHunter()
    real_non_py = str(Path(__file__).parent.parent / "README.md")
    try:
        hunter.scan_file(real_non_py)
        assert False, "expected FileNotFoundError for a non-.py file"
    except FileNotFoundError:
        pass


def test_scan_file_still_works_on_a_real_in_repo_file():
    hunter = BugHunter()
    real_py = str(Path(__file__).resolve())
    result = hunter.scan_file(real_py)
    assert "total_bugs" in result


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
