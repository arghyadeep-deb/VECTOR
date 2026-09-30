"""Regression test for a systemic printf-style (`%s`) loguru logging bug found
across core/api/routers/ batch 2 (Phase 3 whole-repo audit, Claude/Codex 50/50
split, 2026-09-30).

loguru's logger.<level>(message, *args) formats positional args with
str.format() semantics ({}), not printf (%s) -- confirmed directly:
`logger.error("failed: %s", e)` prints the literal string "failed: %s" and
silently drops `e` entirely. Same bug class already found and fixed twice
this cycle in core/brain/ (person_model.py, suggestion_queue.py -- commit
bd5f842da), but here it was systemic: 74 instances across 14 of this batch's
30 files (agency, analytics, brain, calls, chief, city, design,
documentation, finance, health, interview, karpathy, languages, learning),
every error-path log call in those routers. Fixed mechanically (verified via
AST, not just grep) by replacing %s with {} in every affected logger call's
format string -- zero behavior change to the actual HTTP error responses
(those already correctly used str(e) directly), purely restores server-log
diagnostic visibility.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.api.routers.finance import budget_analyze, BudgetAnalyzeReq
from core.api.routers.calls import screen_call, ScreenCallReq
from core.api.routers.brain import get_person
from fastapi import HTTPException

_FIXED_FILES = [
    "agency", "analytics", "brain", "calls", "chief", "city", "design",
    "documentation", "finance", "health", "interview", "karpathy",
    "languages", "learning",
]


def _capture_loguru():
    from loguru import logger
    logged: list[str] = []
    handler_id = logger.add(lambda msg: logged.append(str(msg)), level="DEBUG")
    return logged, handler_id


@pytest.mark.asyncio
async def test_finance_single_arg_logs_real_exception():
    logged, handler_id = _capture_loguru()
    from loguru import logger
    try:
        with patch(
            "core.city.governor.GovernorCouncil.dispatch",
            new=AsyncMock(side_effect=RuntimeError("ledger corrupt")),
        ):
            with pytest.raises(HTTPException):
                await budget_analyze(BudgetAnalyzeReq())
    finally:
        logger.remove(handler_id)

    assert any("ledger corrupt" in line for line in logged), (
        "budget_analyze's error log must render the real exception, not a literal %s"
    )
    assert not any("%s" in line for line in logged), (
        "no log line should contain a literal, un-substituted %s placeholder"
    )


@pytest.mark.asyncio
async def test_calls_single_arg_logs_real_exception():
    logged, handler_id = _capture_loguru()
    from loguru import logger
    try:
        with patch(
            "core.city.governor.GovernorCouncil.dispatch",
            new=AsyncMock(side_effect=RuntimeError("spam db unreachable")),
        ):
            with pytest.raises(HTTPException):
                await screen_call(ScreenCallReq(caller_number="+1555"))
    finally:
        logger.remove(handler_id)

    assert any("spam db unreachable" in line for line in logged)


@pytest.mark.asyncio
async def test_brain_two_arg_logs_both_real_values():
    """brain.py's get_person() is the one multi-arg case
    (`"person model failed for {}: {}"`, person_id, e) -- verify BOTH
    substitutions happened, not just the first."""
    logged, handler_id = _capture_loguru()
    from loguru import logger
    try:
        with patch(
            "core.brain.person_model.PersonModel.get_model",
            side_effect=RuntimeError("db locked"),
        ):
            with pytest.raises(HTTPException):
                await get_person("owner_123")
    finally:
        logger.remove(handler_id)

    assert any("owner_123" in line and "db locked" in line for line in logged), (
        "both positional args (person_id and the exception) must be substituted"
    )


def test_no_printf_style_logger_calls_remain_in_fixed_files():
    """Golden test: AST-scan every fixed file and assert zero
    logger.<level>(...) calls still use a %s/%d/%r placeholder in their
    format string."""
    root = Path(__file__).parent.parent
    offenders = []
    for name in _FIXED_FILES:
        path = root / "core" / "api" / "routers" / f"{name}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in (
                "error", "warning", "info", "debug", "exception", "critical",
                "success", "trace",
            ):
                continue
            if not (isinstance(node.func.value, ast.Name) and node.func.value.id == "logger"):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            fmt = node.args[0].value
            if isinstance(fmt, str) and any(p in fmt for p in ("%s", "%d", "%r")):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"printf-style logger calls still present: {offenders}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
