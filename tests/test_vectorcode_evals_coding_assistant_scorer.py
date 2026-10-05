"""Regression tests for Coding Assistant test execution."""

from vectorcode.src.evals.scorers.coding_assistant import _run_single_test


_TEST = """from solution import answer

def test_answer():
    assert answer() == 42
"""


def test_extracted_test_function_is_actually_invoked():
    assert _run_single_test("def answer(): return 0", _TEST) is False
    assert _run_single_test("def answer(): return 42", _TEST) is True


def test_model_code_cannot_import_arbitrary_modules():
    assert _run_single_test("import os\ndef answer(): return 42", _TEST) is False


if __name__ == "__main__":
    raise SystemExit("Run with pytest")
