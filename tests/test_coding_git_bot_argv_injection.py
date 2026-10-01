"""Regression: GitBot.gitnexus_impact()/analyze_with_gitnexus() passed
caller-controlled symbol/repo_path straight into a subprocess argv list
with no check for a leading '-' -- the same argument-injection shape
already fixed ~25 times elsewhere this cycle (core/mcp_tools' git/perf/
pytest tools, vectorcode/src/tools/git_tools.py). Both now reject a
leading '-' before ever building the subprocess command.
"""
import asyncio

import pytest

from districts.coding.git_bot import GitBot


@pytest.mark.asyncio
async def test_gitnexus_impact_rejects_dash_prefixed_symbol():
    bot = GitBot()
    result = await bot.gitnexus_impact("--help", repo_path=".")
    assert result["status"] == "error"
    assert "invalid" in result["error"].lower()


@pytest.mark.asyncio
async def test_gitnexus_impact_rejects_dash_prefixed_repo_path():
    bot = GitBot()
    result = await bot.gitnexus_impact("real_symbol", repo_path="--upload-pack=evil")
    assert result["status"] == "error"
    assert "invalid" in result["error"].lower()


@pytest.mark.asyncio
async def test_analyze_with_gitnexus_rejects_dash_prefixed_repo_path():
    bot = GitBot()
    result = await bot.analyze_with_gitnexus(repo_path="--exec=evil")
    assert result["status"] == "error"
    assert "invalid" in result["error"].lower()


if __name__ == "__main__":
    asyncio.run(test_gitnexus_impact_rejects_dash_prefixed_symbol())
    asyncio.run(test_gitnexus_impact_rejects_dash_prefixed_repo_path())
    asyncio.run(test_analyze_with_gitnexus_rejects_dash_prefixed_repo_path())
    print("OK test_coding_git_bot_argv_injection.py")
