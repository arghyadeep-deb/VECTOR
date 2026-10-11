"""Regression for 2 real bugs found in core/code_conductor/ during the
Phase 3 whole-repo audit (2026-10-02):

1. orchestrator.py's CodingOrchestrator._llm() called
   core.inference.vectorcode_llm.chat() directly with no
   session_hydration_prompt() -- RULE 1 gap. This drives real file edits
   via str_replace/write_file, so unhydrated plans/edits were a real gap,
   not a cosmetic one.

2. git_eval.py's GitEvalRunner._get_commit_info()/_get_target_diff()/
   _checkout_pre_commit() passed caller-supplied commit_sha/parent_sha
   straight into git log/diff/worktree with no validation -- a value
   starting with "-" (e.g. "--output=<path>") is a real arbitrary-file-
   write primitive on git log/diff. Dormant for the one real production
   caller (run_suite() only ever passes trusted SHAs from `git log
   --pretty=%H`), fixed anyway per this cycle's established bar.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.code_conductor.orchestrator import CodingOrchestrator
from core.code_conductor.git_eval import GitEvalRunner


def _run(coro):
    return asyncio.run(coro)


def test_orchestrator_llm_hydrates_before_chat():
    orch = CodingOrchestrator()
    with patch("core.inference.vectorcode_llm.chat", return_value="plan") as mock_chat:
        _run(orch._llm("do something", system="sys prompt"))
    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 0
    # the caller-supplied system prompt still comes through, after hydration
    assert messages[1]["content"] == "sys prompt"
    assert messages[-1]["content"] == "do something"


def test_git_eval_rejects_option_like_commit_sha():
    runner = GitEvalRunner(cwd=str(Path(__file__).parent.parent))
    with pytest.raises(ValueError):
        runner._get_commit_info("--output=/tmp/pwned")
    with pytest.raises(ValueError):
        runner._get_target_diff("--upload-pack=x")


def test_git_eval_rejects_option_like_parent_sha_in_checkout(tmp_path):
    runner = GitEvalRunner(cwd=str(Path(__file__).parent.parent))
    with pytest.raises(ValueError):
        runner._checkout_pre_commit("--output=/tmp/pwned", str(tmp_path))


def test_git_eval_accepts_real_sha_unchanged():
    """Confirms the fix doesn't change behavior for legitimate SHAs --
    a bare "--" separator would have (verified: git log --pretty=%s --
    <sha> silently returns empty instead of the real commit message)."""
    runner = GitEvalRunner(cwd=str(Path(__file__).parent.parent))
    message, parent = runner._get_commit_info("262c9d7db")
    assert message  # real commit message, not empty
    assert parent


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
