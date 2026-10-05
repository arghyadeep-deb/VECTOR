from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_remaining_learning_modules_use_loguru() -> None:
    checkpoint = (
        ROOT / "vectorcode/src/learning/distillation/checkpoint/store.py"
    ).read_text(encoding="utf-8")
    student = (
        ROOT / "vectorcode/src/learning/distillation/student_runner.py"
    ).read_text(encoding="utf-8")

    dspy = (ROOT / "vectorcode/src/learning/agents/dspy_optimizer.py").read_text(encoding="utf-8")
    gepa = (ROOT / "vectorcode/src/learning/agents/gepa_optimizer.py").read_text(encoding="utf-8")
    prompt_diff = (ROOT / "vectorcode/src/learning/distillation/plan/prompt_diff.py").read_text(encoding="utf-8")

    for source in (checkpoint, student, dspy, gepa, prompt_diff):
        assert "from loguru import logger" in source
        assert "import logging" not in source
        assert "logging.getLogger" not in source


def test_learning_initializer_uses_loguru_exception_api() -> None:
    source = (ROOT / "vectorcode/src/learning/__init__.py").read_text(encoding="utf-8")

    assert "exc_info=True" not in source
    assert source.count("logger.opt(exception=True).debug") == 4
