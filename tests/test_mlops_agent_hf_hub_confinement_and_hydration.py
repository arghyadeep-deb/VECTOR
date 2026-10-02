"""Regression for two bugs found in districts/coding/mlops_agent.py during
the Phase 3 whole-repo audit (2026-10-02):

1. hf_hub()'s upload action passed caller-supplied local_path straight into
   HfApi.upload_file() with zero confinement -- a real local file (not just
   a model checkpoint) could be read and uploaded to a real, caller-chosen
   HF Hub repo. Note: hf_hub's outer task type is already RED-tier (requires
   owner approval before execution at all, core/config.py's 2026-09-24
   finding) -- this fix narrows what a single approved call can actually
   touch, it does not replace that gate.

2. ml_research()/_answer_query() called core.inference.vectorcode_llm.chat()
   directly with no session_hydration_prompt() -- same RULE 1 gap already
   fixed in districts/marketing + 4 other districts/coding files this cycle.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from districts.coding.mlops_agent import MLOpsAgent


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_hf_hub_upload_rejects_path_outside_repo(tmp_path):
    agent = MLOpsAgent()
    outside = tmp_path / "secret.txt"
    outside.write_text("s")
    result = _run(agent.hf_hub(action="upload", repo_id="x/y",
                                path_in_repo="f.txt", local_path=str(outside)))
    assert result["status"] == "error"
    assert "outside repo root" in result["error"]


def test_hf_hub_upload_allows_path_inside_repo():
    agent = MLOpsAgent()
    inside = Path(__file__).resolve()  # this test file itself, inside the repo
    fake_hf_module = MagicMock()
    fake_api_instance = MagicMock()
    fake_hf_module.HfApi.return_value = fake_api_instance
    with patch.dict(sys.modules, {"huggingface_hub": fake_hf_module}):
        result = _run(agent.hf_hub(action="upload", repo_id="x/y",
                                    path_in_repo="f.txt", local_path=str(inside)))
    assert result["status"] == "ok"
    fake_api_instance.upload_file.assert_called_once()


def test_ml_research_hydrates_before_chat():
    agent = MLOpsAgent()
    with patch("core.inference.vectorcode_llm.chat", return_value="answer") as mock_chat:
        _run(agent.ml_research("LoRA fine-tuning"))
    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 0


def test_answer_query_hydrates_before_chat():
    agent = MLOpsAgent()
    with patch("core.inference.vectorcode_llm.chat", return_value="answer") as mock_chat:
        _run(agent._answer_query("what can you do?"))
    messages = mock_chat.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert len(messages[0]["content"]) > 0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
