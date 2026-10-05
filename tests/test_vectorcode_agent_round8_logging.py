"""Regression coverage for round-8 Loguru shadowing fixes."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from loguru import logger


VECTORCODE_SRC = Path(__file__).resolve().parents[1] / "vectorcode" / "src"
if str(VECTORCODE_SRC) not in sys.path:
    sys.path.insert(0, str(VECTORCODE_SRC))


def test_round8_modules_keep_loguru_logger():
    modules = (
        "agent.curator_backup",
        "agent.display",
        "agent.error_classifier",
        "agent.i18n",
        "agent.image_gen_provider",
        "agent.image_gen_registry",
        "agent.image_routing",
        "agent.nous_rate_guard",
        "agent.onboarding",
        "agent.plugin_llm",
        "agent.prompt_builder",
        "agent.subdirectory_hints",
        "agent.title_generator",
        "agent.video_gen_provider",
        "agent.video_gen_registry",
        "agent.web_search_registry",
    )
    for module_name in modules:
        path = VECTORCODE_SRC / (module_name.replace(".", "/") + ".py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports_loguru_logger = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "loguru"
            and any(alias.name == "logger" for alias in node.names)
            for node in tree.body
        )
        assert imports_loguru_logger, module_name


def test_round8_modules_have_no_stdlib_logging_arguments():
    agent_dir = VECTORCODE_SRC / "agent"
    changed = (
        "curator_backup.py",
        "display.py",
        "error_classifier.py",
        "i18n.py",
        "image_routing.py",
        "nous_rate_guard.py",
        "onboarding.py",
        "plugin_llm.py",
        "prompt_builder.py",
        "subdirectory_hints.py",
        "title_generator.py",
        "video_gen_registry.py",
        "web_search_registry.py",
    )
    combined = "\n".join((agent_dir / name).read_text(encoding="utf-8") for name in changed)
    assert "logging.getLogger" not in combined
    assert "exc_info=True" not in combined


def test_credential_pool_uses_loguru_exception_api():
    source = (VECTORCODE_SRC / "agent" / "credential_pool.py").read_text(encoding="utf-8")
    assert "exc_info=True" not in source
