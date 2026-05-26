import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Tests must never hang on unguarded network I/O. Several integration/E2E tests
# make blocking calls to live services (Ollama, Pushover, etc.); a global socket
# timeout makes any such call fail fast instead of stalling the whole suite.
import socket
socket.setdefaulttimeout(20)

import asyncio
import json
import sqlite3
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.loop.decision_engine import Candidate


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_ollama():
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "test response", "done": True}
        mock_response.text = json.dumps({"response": "test", "done": True})
        mock_instance = mock_client.return_value
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.post.return_value = mock_response
        mock_instance.get.return_value = mock_response
        yield mock_instance


@pytest.fixture
def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE IF NOT EXISTS test_memory (id INTEGER PRIMARY KEY, key TEXT, value TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, result TEXT, ts TEXT)")
    yield conn
    conn.close()


@pytest.fixture
def config_override():
    stack = []

    def apply(path_parts, value):
        d = CONFIG
        for part in path_parts[:-1]:
            d = d.setdefault(part, {})
        key = path_parts[-1]
        old = d.get(key)
        stack.append((path_parts, old))
        d[key] = value

    yield apply

    for path_parts, old in reversed(stack):
        d = CONFIG
        for part in path_parts[:-1]:
            d = d.setdefault(part, {})
        key = path_parts[-1]
        if old is None:
            d.pop(key, None)
        else:
            d[key] = old


@pytest.fixture
def sample_agent():
    return AgentBase(str(uuid.uuid4()), "TestAgent", "coding")


@pytest.fixture
def sample_candidates():
    return [
        Candidate(
            "search_web", {"query": "test query"},
            goal_ids=["g_test_1"], confidence=0.9, urgency=0.7,
            timing_score=1.0, estimated_cost_inr=0.5, source="user",
        ),
        Candidate(
            "set_timer", {"duration_sec": 60},
            goal_ids=[], confidence=0.5, urgency=0.3,
            timing_score=0.8, estimated_cost_inr=0.0, source="system",
        ),
        Candidate(
            "commit_code", {"repo": "VECTOR", "msg": "fix"},
            goal_ids=["g_test_2"], confidence=0.75, urgency=0.4,
            timing_score=0.6, estimated_cost_inr=2.0, source="system",
        ),
    ]


@pytest.fixture
def mock_psutil():
    with (
        patch("psutil.cpu_percent", return_value=25.0) as mock_cpu,
        patch("psutil.virtual_memory") as mock_vm,
        patch("psutil.disk_usage") as mock_du,
    ):
        mock_vm.return_value.percent = 50.0
        mock_vm.return_value.available = 8 * 1024 ** 3
        mock_vm.return_value.total = 16 * 1024 ** 3
        mock_du.return_value.percent = 60.0
        mock_du.return_value.free = 100 * 1024 ** 3
        mock_du.return_value.total = 500 * 1024 ** 3
        yield {"cpu": mock_cpu, "memory": mock_vm, "disk": mock_du}


@pytest.fixture
def mock_policy():
    p = MagicMock()
    p.get_score.return_value = 0.5
    p.update_from_outcome.return_value = None
    return p


@pytest.fixture
def mock_goals():
    g = MagicMock()
    g.get_active_goals.return_value = []
    return g


@pytest.fixture
def mock_memory():
    m = MagicMock()
    m.store.return_value = None
    return m


@pytest.fixture
def mock_epistemic():
    e = MagicMock()
    e.get_belief.return_value = None
    e.update_belief.return_value = None
    return e
