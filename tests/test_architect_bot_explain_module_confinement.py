"""Regression for ArchitectBot.explain_module() reading any caller-supplied
path with zero confinement and feeding its contents into an LLM prompt --
same bug class fixed in code_reviewer.py/addy_code_reviewer.py this cycle.
Zero real callers today, fixed anyway since the confinement check is
narrow/mechanical with no legitimate-caller risk.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.coding.architect_bot import ArchitectBot


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_explain_module_rejects_path_outside_repo(tmp_path):
    bot = ArchitectBot()
    outside = tmp_path / "secret.py"
    outside.write_text("SECRET = 'nope'\n")
    result = _run(bot.explain_module(str(outside)))
    assert "outside repo" in result.lower() or "not a .py file" in result.lower()


def test_explain_module_rejects_non_py_suffix():
    bot = ArchitectBot()
    real_non_py = str(Path(__file__).parent.parent / "README.md")
    result = _run(bot.explain_module(real_non_py))
    assert "outside repo" in result.lower() or "not a .py file" in result.lower()


def test_explain_module_still_errors_cleanly_on_missing_real_py_path():
    bot = ArchitectBot()
    missing = str(Path(__file__).parent.parent / "districts" / "coding" / "__does_not_exist__.py")
    result = _run(bot.explain_module(missing))
    assert "not found" in result.lower()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
