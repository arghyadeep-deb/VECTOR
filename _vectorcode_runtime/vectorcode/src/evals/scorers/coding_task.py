# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:35+00:00

"""Coding task scorer — test pass rate + structural validation.

Extracts the function/class from model output and runs test cases
to determine correctness.
"""

from __future__ import annotations
from loguru import logger

import logging
import re
from typing import Any, Dict, Optional, Tuple

from vectorcode.src.evals.core.scorer import Scorer
from vectorcode.src.evals.core.types import EvalRecord

LOGGER = logging.getLogger(__name__)

def _extract_code(answer: str) -> str:
    """Extract Python code from model answer, handling markdown fences."""
    # Try markdown code fence first
    fence_match = re.search(
        r"```(?:python)?\s*\n(.*?)```",
        answer,
        re.DOTALL,
    )
    if fence_match:
        return fence_match.group(1).strip()

    # Look for function/class definitions
    lines = answer.strip().split("\n")
    code_lines = []
    in_code = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith(("def ", "class ", "from ", "import ")):
            in_code = True
        if in_code:
            code_lines.append(line)

    if code_lines:
        return "\n".join(code_lines)

    # Last resort: return the whole answer
    return answer.strip()

_SAFE_BUILTINS = {k: __builtins__[k] for k in ("print", "range", "len", "list", "dict", "float", "int", "str", "bool", "tuple", "set", "min", "max", "sum", "abs", "enumerate", "zip", "map", "filter", "any", "all", "sorted", "reversed", "isinstance", "hasattr", "getattr", "type", "True", "False", "None", "Exception", "ValueError", "TypeError", "KeyError", "IndexError", "AttributeError", "StopIteration", "iter", "next", "bytes", "bytearray", "chr", "ord", "hex", "oct", "bin", "pow", "round", "divmod", "hash", "id", "repr", "ascii", "format", "callable", "delattr", "dir", "vars", "super", "property", "staticmethod", "classmethod", "ZeroDivisionError", "OverflowError", "Warning", "SyntaxError", "IndentationError", "TabError") if k in __builtins__}

_EVAL_ESCAPE_PATTERNS = (
    "__subclasses__", "__bases__", "__mro__", "__builtins__",
    "__globals__", "__code__", "__reduce__", "__reduce_ex__", "importlib",
)

def _check_eval_code(code: str) -> Optional[str]:
    for pat in _EVAL_ESCAPE_PATTERNS:
        if pat in code:
            return f"Blocked: eval code contains prohibited pattern '{pat}'"
    return None

def _run_tests(code: str, test_cases: str) -> Tuple[int, int, str]:
    """Execute code + tests in a restricted namespace. Returns (passed, total, error)."""
    violation = _check_eval_code(code) or _check_eval_code(test_cases)
    if violation:
        return 0, 0, violation
    namespace: Dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}

    try:
        exec(code, namespace)  # noqa: S102
    except Exception as exc:
        return 0, 0, f"Code execution error: {exc}"

    # Parse individual test assertions
    test_lines = [
        line.strip() for line in test_cases.strip().split("\n") if line.strip()
    ]

    passed = 0
    total = 0

    # Some tests span multiple lines (setup + assert), so we run
    # the whole block together but count assertions
    try:
        exec(test_cases, namespace)  # noqa: S102
        # Count assertions in the test code
        total = sum(1 for line in test_lines if "assert " in line)
        passed = total
        return passed, total, ""
    except AssertionError as exc:
        # Count how many assertions were in the code
        total = sum(1 for line in test_lines if "assert " in line)
        # Run line by line to count individual passes
        passed = 0
        for line in test_lines:
            if "assert " not in line:
                try:
                    exec(line, namespace)  # noqa: S102
                except Exception as _sve:
                    logger.debug("[VECTOR][evals.scorers.coding_task] suppressed Exception: %s", exc)
                continue
            try:
                exec(line, namespace)  # noqa: S102
                passed += 1
            except (AssertionError, Exception) as _sve:
                logger.debug("[VECTOR][evals.scorers.coding_task] suppressed (AssertionError, Exception): %s", exc)
        return passed, total, str(exc)
    except Exception as exc:
        total = sum(1 for line in test_lines if "assert " in line)
        return 0, max(total, 1), f"Test execution error: {exc}"

class CodingTaskScorer(Scorer):
    """Score coding tasks by running test cases against model output."""

    scorer_id = "coding_task"

    def __init__(self, judge_backend=None, judge_model: str = "") -> None:
        # Accept same constructor args as LLMJudgeScorer for compatibility
        # but don't need the judge for this scorer
        self.judge_backend = judge_backend
        self.judge_model = judge_model

    def score(
        self,
        record: EvalRecord,
        model_answer: str,
    ) -> Tuple[Optional[bool], Dict[str, Any]]:
        if not model_answer or not model_answer.strip():
            return False, {"reason": "empty_response"}

        test_cases = record.metadata.get("test_cases", "")
        if not test_cases:
            return None, {"reason": "no_test_cases"}

        code = _extract_code(model_answer)
        if not code:
            return False, {"reason": "no_code_extracted"}

        passed, total, error = _run_tests(code, test_cases)

        if total == 0:
            return None, {"reason": "no_assertions_found"}

        pass_rate = passed / total
        is_correct = pass_rate == 1.0

        meta: Dict[str, Any] = {
            "match_type": "test_execution",
            "tests_passed": passed,
            "tests_total": total,
            "pass_rate": pass_rate,
        }
        if error:
            meta["error"] = error

        return is_correct, meta

__all__ = ["CodingTaskScorer"]
