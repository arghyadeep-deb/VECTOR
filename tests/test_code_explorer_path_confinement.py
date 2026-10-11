"""Regression for CodeExplorer.explain_file()/get_imports()/
get_classes_and_functions() reading any caller-supplied path with zero
confinement. explain_file() sends file content into an LLM prompt and is
directly Governor-dispatchable via run()'s task_type == "explain" (not
dormant) -- same bug class fixed in code_reviewer.py/architect_bot.py/
bug_hunter.py this cycle.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.coding.code_explorer import CodeExplorer


def _run(coro):
    return asyncio.run(coro)


def test_get_imports_returns_empty_for_path_outside_repo(tmp_path):
    agent = CodeExplorer()
    outside = tmp_path / "secret.py"
    outside.write_text("import os\n")
    assert agent.get_imports(str(outside)) == []


def test_get_classes_and_functions_returns_empty_for_path_outside_repo(tmp_path):
    agent = CodeExplorer()
    outside = tmp_path / "secret.py"
    outside.write_text("class Secret:\n    pass\n")
    result = agent.get_classes_and_functions(str(outside))
    assert result == {"classes": [], "functions": []}


def test_explain_file_errors_cleanly_for_path_outside_repo(tmp_path):
    agent = CodeExplorer()
    outside = tmp_path / "secret.py"
    outside.write_text("API_KEY = 'real-secret-value'\n")
    result = _run(agent.explain_file(str(outside)))
    assert result["status"] == "error"


def test_get_imports_still_works_on_a_real_in_repo_file():
    agent = CodeExplorer()
    real_py = str(Path(__file__).resolve())
    imports = agent.get_imports(real_py)
    assert isinstance(imports, list) and len(imports) > 0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
