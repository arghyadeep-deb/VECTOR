"""
TDD wiring tests — coding-district reviewer agents must route run(task) by
task["type"] to their real review methods, instead of relying on the
AgentBase fake-success stub or an undifferentiated params dict.

Governor calls: await agent.run(task) where task = {"type": ..., "params": {...}}
See core/city/governor.py dispatch() line ~1100: `result = await agent.run(task)`.

Also verifies ObraCodeReviewer is a real AgentBase instance with a working .id
(it already subclasses AgentBase transitively via PromptAgent — this test
locks that in so it can never silently regress).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from core.city.agent_base import AgentBase
from districts.coding.fastapi_reviewer import FastAPIReviewer
from districts.coding.obra_code_reviewer import ObraCodeReviewer
from districts.coding.python_reviewer import PythonReviewer
from districts.coding.security_reviewer import SecurityReviewer


# --- ObraCodeReviewer: AgentBase identity check ---

async def test_obra_code_reviewer_is_agent_base_instance_with_real_id():
    agent = ObraCodeReviewer()
    assert isinstance(agent, AgentBase), "ObraCodeReviewer must be an AgentBase instance"
    assert isinstance(agent.id, str) and agent.id, "agent.id must be a real non-empty string"
    assert hasattr(agent, "health_points")
    assert agent.health_points == 500


async def test_obra_code_reviewer_real_chat_dispatch_answers_free_text_query(monkeypatch):
    """Real production shape: governor's classify_chat_intent() invents a
    task_type string that matches none of ObraCodeReviewer's branches (it
    has none — it's a PromptAgent). PromptAgent.run() (core/city/prompt_agent.py)
    ignores task["type"] entirely and always extracts task["params"]["query"]
    and calls self.ask() with it, so ObraCodeReviewer is ALREADY correctly
    wired for real chat traffic — unlike its sibling static-analysis
    reviewers (FastAPIReviewer/PythonReviewer/SecurityReviewer below, which
    error out on this exact shape). Mock only the LLM transport
    (core.inference.vectorcode_llm.chat), not run() itself, per testing.md.
    """
    import core.inference.vectorcode_llm as _vcl
    monkeypatch.setattr(
        _vcl, "chat",
        lambda *a, **k: "Second opinion: the diff looks reasonable, but watch for an N+1 query in the loop.",
    )
    agent = ObraCodeReviewer()
    task = {
        "type": "second_opinion_on_diff",
        "params": {
            "query": "Can you give a second opinion on this pull request diff?",
            "content": "Can you give a second opinion on this pull request diff?",
            "source": "api_command",
        },
    }
    result = await agent.run(task)
    assert result["status"] == "ok"
    assert len(result.get("response", "")) > 0


# --- FastAPIReviewer: task["type"] routing ---

async def test_fastapi_reviewer_review_fastapi_task_type():
    agent = FastAPIReviewer()
    task = {
        "type": "review_fastapi",
        "params": {
            "code": (
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                'add_middleware("CORSMiddleware", allow_origins=["*"], allow_credentials=True)\n'
                "@app.get('/items')\n"
                "def get_items():\n"
                "    raise Exception('oops')\n"
            ),
            "filename": "router.py",
        },
    }
    result = await agent.run(task)
    assert result["agent"] == "FastAPIReviewer"
    # Must have actually unwrapped task["params"]["code"] and run the static scan —
    # this sample has CORS + sync-handler + bare-Exception violations.
    assert result["issue_count"] > 0


async def test_fastapi_reviewer_unhandled_type_returns_error():
    agent = FastAPIReviewer()
    task = {"type": "nonexistent_task_type", "params": {}}
    result = await agent.run(task)
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result


async def test_fastapi_reviewer_real_chat_dispatch_unmatched_type_with_query_still_errors():
    """LIVE BUG (documented, not fixed here — tests are TESTS ONLY):
    real production shape from governor._dispatch_to_district is
    task={"type": <classifier-invented string>, "params": {"query": ...}}.
    FastAPIReviewer.run() checks `if task_type not in self._SUPPORTED_TASK_TYPES`
    and returns the error stub BEFORE ever reading params, so its own
    _answer_query() free-text fallback (which does exist and does work) is
    unreachable for this exact real-world dispatch shape — it only fires
    when task_type IS 'review_fastapi'/'review' but params lacks code. A
    real user question routed here by the classifier currently gets an
    error, not an answer. This test locks in the CURRENT (broken) behavior
    so it doesn't silently regress further, and flags the bug for a future
    session to fix in districts/coding/fastapi_reviewer.py.
    """
    agent = FastAPIReviewer()
    task = {
        "type": "explain_fastapi_dependency_injection",
        "params": {
            "query": "How does FastAPI's Depends() work for auth checks?",
            "content": "How does FastAPI's Depends() work for auth checks?",
            "source": "api_command",
        },
    }
    result = await agent.run(task)
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]


# --- PythonReviewer: task["type"] routing ---

async def test_python_reviewer_review_python_task_type(monkeypatch):
    monkeypatch.setenv("VECTOR_PYTHON_REVIEW_LLM", "0")
    agent = PythonReviewer()
    task = {
        "type": "review_python",
        "params": {
            "code": "import pickle\nprint('hi')\n",
            "filename": "bad.py",
        },
    }
    result = await agent.run(task)
    assert result["agent"] == "PythonReviewer"
    assert result["issue_count"] > 0


async def test_python_reviewer_keeps_static_findings_when_llm_fails(monkeypatch):
    import core.inference.provider_client as provider_module

    class FailingProvider:
        async def complete(self, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setenv("VECTOR_PYTHON_REVIEW_LLM", "1")
    monkeypatch.setattr(provider_module, "ProviderClient", FailingProvider)

    result = await PythonReviewer().review("import pickle\n", "bad.py")

    assert result["degraded"] is True
    assert result["issue_count"] > 0
    assert result["issue_count"] == result["static_issue_count"]


async def test_python_reviewer_unhandled_type_returns_error():
    agent = PythonReviewer()
    task = {"type": "not_a_real_type", "params": {}}
    result = await agent.run(task)
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result


async def test_python_reviewer_real_chat_dispatch_unmatched_type_with_query_still_errors():
    """LIVE BUG (documented, not fixed here): same bug class as
    FastAPIReviewer above — PythonReviewer.run() gates on
    `task_type not in self._SUPPORTED_TASK_TYPES` before ever reading
    params, so a classifier-invented task_type with a real free-text query
    still hits the error stub instead of PythonReviewer's own
    _answer_query() fallback. Locks in current (broken) behavior.
    """
    agent = PythonReviewer()
    task = {
        "type": "explain_python_asyncio_gotcha",
        "params": {
            "query": "Why does my asyncio task silently swallow exceptions?",
            "content": "Why does my asyncio task silently swallow exceptions?",
            "source": "api_command",
        },
    }
    result = await agent.run(task)
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]


# --- SecurityReviewer: task["type"] routing ---

async def test_security_reviewer_scan_vulnerabilities_task_type(monkeypatch):
    monkeypatch.setenv("VECTOR_SECURITY_REVIEW_LLM", "0")
    agent = SecurityReviewer()
    task = {
        "type": "scan_vulnerabilities",
        "params": {
            "code": "import pickle\npassword = 'hunter2'\n",
            "filename": "bad.py",
        },
    }
    result = await agent.run(task)
    assert result["agent"] == "SecurityReviewer"
    assert result["issue_count"] > 0
    assert "critical_count" in result


async def test_security_reviewer_keeps_static_findings_when_llm_fails(monkeypatch):
    import core.inference.provider_client as provider_module

    class FailingProvider:
        async def complete(self, **kwargs):
            raise RuntimeError("provider unavailable")

    monkeypatch.setenv("VECTOR_SECURITY_REVIEW_LLM", "1")
    monkeypatch.setattr(provider_module, "ProviderClient", FailingProvider)

    result = await SecurityReviewer().review("password = 'hunter2'\n", "bad.py")

    assert result["degraded"] is True
    assert result["issue_count"] > 0
    assert result["issue_count"] == result["static_issue_count"]


async def test_security_reviewer_unhandled_type_returns_error():
    agent = SecurityReviewer()
    task = {"type": "totally_unknown", "params": {}}
    result = await agent.run(task)
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result


async def test_security_reviewer_real_chat_dispatch_unmatched_type_with_query_still_errors():
    """LIVE BUG (documented, not fixed here): same bug class as
    FastAPIReviewer/PythonReviewer above — SecurityReviewer.run() gates on
    `task_type not in self._SUPPORTED_TASK_TYPES` before ever reading
    params, so a classifier-invented task_type with a real free-text query
    still hits the error stub instead of SecurityReviewer's own
    _answer_query() fallback. Locks in current (broken) behavior.
    """
    agent = SecurityReviewer()
    task = {
        "type": "explain_sql_injection_risk",
        "params": {
            "query": "Is string formatting into a raw SQL query always unsafe?",
            "content": "Is string formatting into a raw SQL query always unsafe?",
            "source": "api_command",
        },
    }
    result = await agent.run(task)
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]


if __name__ == "__main__":
    import asyncio

    async def _smoke():
        await test_obra_code_reviewer_is_agent_base_instance_with_real_id()
        await test_obra_code_reviewer_real_chat_dispatch_answers_free_text_query(
            _monkeypatch_stub_for_smoke()
        )
        await test_fastapi_reviewer_review_fastapi_task_type()
        await test_fastapi_reviewer_unhandled_type_returns_error()
        await test_fastapi_reviewer_real_chat_dispatch_unmatched_type_with_query_still_errors()
        await test_python_reviewer_review_python_task_type()
        await test_python_reviewer_unhandled_type_returns_error()
        await test_python_reviewer_real_chat_dispatch_unmatched_type_with_query_still_errors()
        await test_security_reviewer_scan_vulnerabilities_task_type()
        await test_security_reviewer_unhandled_type_returns_error()
        await test_security_reviewer_real_chat_dispatch_unmatched_type_with_query_still_errors()
        print("✅ test_coding_reviewers_run_wiring.py OK")

    class _MiniMonkeypatch:
        """Minimal monkeypatch stand-in for the __main__ smoke path (which
        runs outside pytest, so the real `monkeypatch` fixture isn't
        available). Mirrors just the .setattr() call used above."""
        def __init__(self):
            self._saved = []

        def setattr(self, obj, name, value):
            self._saved.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

    def _monkeypatch_stub_for_smoke():
        return _MiniMonkeypatch()

    asyncio.run(_smoke())
