"""Regression for the systemic loguru-shadowed-by-stdlib-logging bug across
20 files in vectorcode/src/learning/ not covered by prior audit rounds.

Each of these files either imported stdlib `logging` and built its logger
via `logging.getLogger(__name__)` (with zero loguru import anywhere in the
file), or -- in agents/skill_optimizer.py's case -- had a correct top-level
`from loguru import logger` shadowed by a second, stdlib-backed `LOGGER`
name used at several call sites. Either way, every `%s`/`%d`/`%r`/`%.Nf`
placeholder in those calls would silently fail to substitute once pointed
at loguru's `{}`-style formatter -- confirmed as the dominant bug class
this audit cycle. learning_orchestrator.py additionally had a *local*
re-shadow: one `except` branch did a fresh `import logging;
logging.getLogger(__name__).warning(...)` instead of using the module's
own (now-fixed) logger.

distillation/execute/loop.py is notable: a prior round's summary claimed
this file was already fully reviewed, but it still had the raw
stdlib-logging shadow -- confirming that claim was inaccurate for this
specific file.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    ROOT / "vectorcode/src/learning/distillation/diagnose/runner.py",
    ROOT / "vectorcode/src/learning/distillation/diagnose/teacher_agent.py",
    ROOT / "vectorcode/src/learning/distillation/execute/loop.py",
    ROOT / "vectorcode/src/learning/distillation/gate/benchmark_gate.py",
    ROOT / "vectorcode/src/learning/distillation/gate/cold_start.py",
    ROOT / "vectorcode/src/learning/distillation/orchestrator.py",
    ROOT / "vectorcode/src/learning/distillation/plan/planner.py",
    ROOT / "vectorcode/src/learning/distillation/plan/risk_tier.py",
    ROOT / "vectorcode/src/learning/intelligence/orchestrator/grpo_trainer.py",
    ROOT / "vectorcode/src/learning/intelligence/orchestrator/policy_model.py",
    ROOT / "vectorcode/src/learning/intelligence/orchestrator/sft_trainer.py",
    ROOT / "vectorcode/src/learning/learning_orchestrator.py",
    ROOT / "vectorcode/src/learning/optimize/feedback/judge.py",
    ROOT / "vectorcode/src/learning/optimize/llm_optimizer.py",
    ROOT / "vectorcode/src/learning/optimize/optimizer.py",
    ROOT / "vectorcode/src/learning/optimize/trial_runner.py",
    ROOT / "vectorcode/src/learning/routing/learned_router.py",
    ROOT / "vectorcode/src/learning/routing/router.py",
    ROOT / "vectorcode/src/learning/training/lora.py",
    ROOT / "vectorcode/src/learning/agents/skill_optimizer.py",
)


def test_all_modules_parse_as_valid_python():
    for path in MODULES:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_no_module_imports_stdlib_logging():
    for path in MODULES:
        src = path.read_text(encoding="utf-8")
        assert "import logging" not in src, f"{path} still imports stdlib logging"


def test_every_module_imports_loguru():
    for path in MODULES:
        src = path.read_text(encoding="utf-8")
        assert "from loguru import logger" in src, f"{path} is missing the loguru import"


def test_no_percent_style_placeholders_remain_in_logger_calls():
    import re

    call_re = re.compile(
        r"(?:logger|LOGGER)\.(?:debug|info|warning|error|critical|exception|opt)\([^)]*\)",
        re.DOTALL,
    )
    percent_re = re.compile(r"%[sdr]|%\.\d+f")
    for path in MODULES:
        src = path.read_text(encoding="utf-8")
        for match in call_re.finditer(src):
            call_text = match.group(0)
            assert not percent_re.search(call_text), (
                f"{path} still has a %-style placeholder in a logger call: {call_text!r}"
            )


def test_learning_orchestrator_has_no_local_stdlib_logging_reimport():
    src = (ROOT / "vectorcode/src/learning/learning_orchestrator.py").read_text(encoding="utf-8")
    assert "import logging" not in src
    assert "logging.getLogger" not in src


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
