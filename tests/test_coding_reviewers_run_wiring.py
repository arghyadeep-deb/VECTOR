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


# --- PythonReviewer: task["type"] routing ---

async def test_python_reviewer_review_python_task_type():
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


async def test_python_reviewer_unhandled_type_returns_error():
    agent = PythonReviewer()
    task = {"type": "not_a_real_type", "params": {}}
    result = await agent.run(task)
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result


# --- SecurityReviewer: task["type"] routing ---

async def test_security_reviewer_scan_vulnerabilities_task_type():
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


async def test_security_reviewer_unhandled_type_returns_error():
    agent = SecurityReviewer()
    task = {"type": "totally_unknown", "params": {}}
    result = await agent.run(task)
    assert result["status"] == "error"
    assert "unhandled type" in result["error"]
    assert "supported" in result


if __name__ == "__main__":
    import asyncio

    async def _smoke():
        await test_obra_code_reviewer_is_agent_base_instance_with_real_id()
        await test_fastapi_reviewer_review_fastapi_task_type()
        await test_fastapi_reviewer_unhandled_type_returns_error()
        await test_python_reviewer_review_python_task_type()
        await test_python_reviewer_unhandled_type_returns_error()
        await test_security_reviewer_scan_vulnerabilities_task_type()
        await test_security_reviewer_unhandled_type_returns_error()
        print("✅ test_coding_reviewers_run_wiring.py OK")

    asyncio.run(_smoke())
