"""Wave 3 tests — providers, gateway, sessions, MCP, plugins, ACP, cron."""
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

# conftest.py adds VC paths


# ── Providers ─────────────────────────────────────────────────────────────────

def test_provider_router_importable():
    from providers import ModelRouter
    router = ModelRouter()
    assert router is not None


def test_provider_router_parse_anthropic():
    from providers import ModelRouter
    r = ModelRouter()
    p, m = r.parse("anthropic/claude-sonnet-4-5")
    assert p == "anthropic"
    assert m == "claude-sonnet-4-5"


def test_provider_router_parse_openai():
    from providers import ModelRouter
    r = ModelRouter()
    p, m = r.parse("openai/gpt-4o")
    assert p == "openai"
    assert m == "gpt-4o"


def test_provider_router_parse_groq():
    from providers import ModelRouter
    r = ModelRouter()
    p, m = r.parse("groq/llama-4-scout")
    assert p == "groq"
    assert m == "llama-4-scout"


def test_provider_router_parse_bare_ollama():
    from providers import ModelRouter
    r = ModelRouter()
    p, m = r.parse("vector-fast")
    assert p == "ollama"
    assert m == "vector-fast"


def test_get_model_router_singleton():
    from providers import get_model_router
    a = get_model_router()
    b = get_model_router()
    assert a is b


# ── Session DB ────────────────────────────────────────────────────────────────

def test_session_db_create_and_query():
    from session_db import SessionDB
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "test.db"
        db = SessionDB(db_path)
        sid = str(uuid.uuid4())
        db.create_session(sid, model="test", project="p", mode="repl")
        db.add_message(sid, "user", "hello")
        msgs = db.get_messages(sid)
        assert len(msgs) >= 1
        db._conn.close()


def test_session_db_search_fts():
    from session_db import SessionDB
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "test.db"
        db = SessionDB(db_path)
        sid = str(uuid.uuid4())
        db.create_session(sid, model="test", project="p", mode="repl")
        db.add_message(sid, "user", "Find this unique searchterm xyz")
        results = db.search_messages("searchterm")
        assert isinstance(results, list)
        db._conn.close()


def test_session_db_migration():
    from session_db import SessionDB
    import sqlite3
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "test.db"
        db = SessionDB(db_path)
        sid = str(uuid.uuid4())
        db.create_session(sid, model="test", project="p", mode="repl")
        db.migrate_up()
        conn = sqlite3.connect(str(db_path))
        ver = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        assert ver == 10
        cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        assert "parent_session_id" in cols
        conn.close()
        db._conn.close()


# ── Gateway ───────────────────────────────────────────────────────────────────

def test_gateway_server_importable():
    from gateway.server import GatewayServer
    gw = GatewayServer(host="127.0.0.1", port=18123)
    assert gw is not None


def test_gateway_build_app():
    from gateway.server import GatewayServer
    gw = GatewayServer(port=18124)
    try:
        app = gw.build_app()
        # Must have key routes
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/health" in paths
        assert "/run" in paths
    except RuntimeError as e:
        if "FastAPI" in str(e):
            pytest.skip("FastAPI not installed")
        raise


# ── MCP client ────────────────────────────────────────────────────────────────

def test_mcp_client_importable():
    """MCP client module exists somewhere."""
    found = False
    for mod_name in ["mcp_client.client", "mcp_client", "mcp.client"]:
        try:
            __import__(mod_name)
            found = True
            break
        except ImportError:
            continue
    if not found:
        pytest.skip("MCP client not in this build")
    assert found


def test_mcp_bridge_groups():
    from mcp_client.bridge import TOOL_GROUPS, get_group_for_tool
    assert "intelligence" in TOOL_GROUPS
    assert "agents" in TOOL_GROUPS
    assert "memory" in TOOL_GROUPS
    g = get_group_for_tool("agent_spawn")
    assert g == "agents"
    g = get_group_for_tool("memory_read")
    assert g == "memory"


# ── Plugins ───────────────────────────────────────────────────────────────────

def test_plugin_loader_importable():
    from plugins.loader import discover_plugins, load_plugin
    plugins = discover_plugins()
    assert isinstance(plugins, list)


# ── Skills ────────────────────────────────────────────────────────────────────

def test_skill_loader_importable():
    try:
        from skills.loader import SkillRegistry
        reg = SkillRegistry()
        assert reg is not None
    except ImportError:
        pytest.skip("SkillRegistry not in this build")


def test_sparc_coordinator():
    try:
        from skills.builtin.sparc.coordinator import SPARC_STAGES, run_sparc_stage
        assert "specification" in SPARC_STAGES
        assert "completion" in SPARC_STAGES
        assert len(SPARC_STAGES) == 5
    except ImportError:
        pytest.skip("SPARC not in this build")


# ── Credentials ───────────────────────────────────────────────────────────────

def test_credential_pool_basics():
    from credentials import CredentialPool, PooledCredential
    pool = CredentialPool("test", [])
    assert pool.has_available() is False


def test_credential_pool_with_entries():
    from credentials import CredentialPool, PooledCredential
    creds = [PooledCredential(provider="test", id=f"k{i}", label=f"key{i}",
                              source="env:K", api_key=f"sk-{i}") for i in range(3)]
    pool = CredentialPool("test", creds)
    assert pool.has_available() is True
    assert len(pool.entries()) == 3


def test_credential_pool_rotate():
    from credentials import CredentialPool, PooledCredential, STATUS_EXHAUSTED
    cred = PooledCredential(provider="test", id="c1", label="key1",
                            source="env:K", api_key="sk-test")
    pool = CredentialPool("test", [cred])
    assert pool.has_available()
    pool.rotate()
    assert cred.status == STATUS_EXHAUSTED


# ── Cron ──────────────────────────────────────────────────────────────────────

def test_cron_module_importable():
    """Cron scheduler module exists."""
    found = False
    for mod_name in ["cron", "cron.scheduler", "cron.jobs"]:
        try:
            mod = __import__(mod_name, fromlist=["*"])
            if hasattr(mod, "__name__"):
                found = True
                break
        except ImportError:
            continue
    if not found:
        pytest.skip("cron module not in this build")
    assert found


# ── Memory ────────────────────────────────────────────────────────────────────

def test_memory_manager_importable():
    from memory.manager import MemoryManager
    assert MemoryManager is not None


# ── Engine ────────────────────────────────────────────────────────────────────

def test_engine_aiagent_init():
    from engine import AIAgent
    a = AIAgent(model="test")
    assert a.model == "test"
    assert a.budget.max_total == 90


def test_engine_iteration_budget():
    from engine import IterationBudget
    b = IterationBudget(max_total=3)
    assert b.consume() is True
    assert b.consume() is True
    assert b.consume() is True
    assert b.consume() is False  # exhausted
    b.refund()
    assert b.consume() is True


def test_engine_safe_writer():
    from engine.safety import _SafeWriter

    class Broken:
        def write(self, x): raise OSError("pipe broken")
        def flush(self): raise ValueError("closed")
        def fileno(self): return -1
        def isatty(self): raise OSError()

    w = _SafeWriter(Broken())
    # Must not raise
    w.write("hi")
    w.flush()
    assert w.isatty() is False


def test_engine_sanitize_surrogates():
    from engine.safety import _sanitize_surrogates
    text = "ok \ud83d bad"
    sanitized = _sanitize_surrogates(text)
    assert "\ud83d" not in sanitized
    assert "ok" in sanitized


def test_engine_destructive_command_detection():
    from engine.safety import _is_destructive_command
    assert _is_destructive_command("rm -rf /tmp/foo") is True
    assert _is_destructive_command("cat README.md") is False
    assert _is_destructive_command("git reset --hard HEAD") is True
    assert _is_destructive_command("ls -la") is False


def test_engine_parallel_safety():
    from engine.tool_exec import _should_parallelize_tool_batch, _PARALLEL_SAFE_TOOLS
    # Two parallel-safe reads with different paths → parallelizable
    calls = [
        {"id": "1", "name": "read_file", "arguments": '{"path": "/tmp/a.txt"}'},
        {"id": "2", "name": "read_file", "arguments": '{"path": "/tmp/b.txt"}'},
    ]
    assert _should_parallelize_tool_batch(calls) is True

    # One unsafe tool → not parallelizable
    calls2 = [
        {"id": "1", "name": "bash", "arguments": "{}"},
        {"id": "2", "name": "read_file", "arguments": '{"path": "/tmp/a.txt"}'},
    ]
    assert _should_parallelize_tool_batch(calls2) is False


# ── Utils ─────────────────────────────────────────────────────────────────────

def test_utils_atomic_json_write():
    from utils import atomic_json_write
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "test.json"
        atomic_json_write(p, {"a": 1, "b": 2})
        data = json.loads(p.read_text())
        assert data == {"a": 1, "b": 2}


def test_utils_safe_json_loads():
    from utils import safe_json_loads
    assert safe_json_loads('{"a": 1}') == {"a": 1}
    assert safe_json_loads("garbage", default={}) == {}
    assert safe_json_loads(None, default="fallback") == "fallback"


def test_utils_env_var_enabled():
    from utils import env_var_enabled
    os.environ["_TEST_W3"] = "1"
    assert env_var_enabled("_TEST_W3") is True
    os.environ["_TEST_W3"] = "false"
    assert env_var_enabled("_TEST_W3") is False
    del os.environ["_TEST_W3"]


def test_utils_base_url_host_matches():
    from utils import base_url_host_matches
    assert base_url_host_matches("https://api.openai.com/v1", "openai.com") is True
    assert base_url_host_matches("https://evil.com/api.openai.com/v1", "openai.com") is False


# ── Vector constants ──────────────────────────────────────────────────────────

def test_vector_constants():
    import vector_constants as vc
    assert callable(vc.get_vector_home)
    assert callable(vc.get_vector_skills_dir)
    home = vc.get_vector_home()
    assert isinstance(home, Path)


def test_vector_constants_compat_aliases():
    import vector_constants as vc
    assert callable(vc.get_config_path)
    assert callable(vc.get_subprocess_home)
    assert callable(vc.display_vector_home)


# ── ACP ───────────────────────────────────────────────────────────────────────

def test_acp_server_importable():
    try:
        from acp.server import ACPServer
        srv = ACPServer(host="127.0.0.1", port=18765)
        assert srv is not None
    except ImportError:
        pytest.skip("ACP not in this build")


# ── Display ───────────────────────────────────────────────────────────────────

def test_display_spinner():
    from display import VectorSpinner, KawaiiSpinner
    assert VectorSpinner is KawaiiSpinner  # alias


def test_display_get_tool_emoji():
    from display import get_tool_emoji
    e = get_tool_emoji("read_file")
    assert isinstance(e, str)


# ── Context ───────────────────────────────────────────────────────────────────

def test_context_compactor_importable():
    from context.compactor import ContextCompactor
    assert ContextCompactor is not None


def test_context_references_importable():
    from context import expand_context_references, ContextReferenceResult
    assert callable(expand_context_references)


# ── Vector_state DB ──────────────────────────────────────────────────────────

def test_vector_state_module_loads():
    """vector_state.py (formerly hermes_state) loads."""
    try:
        import vector_state
        assert hasattr(vector_state, "__name__")
    except ImportError:
        pytest.skip("vector_state not in this build")


# ── Vector_logging ───────────────────────────────────────────────────────────

def test_vector_logging_module_loads():
    try:
        import vector_logging
        assert hasattr(vector_logging, "__name__")
    except ImportError:
        pytest.skip("vector_logging not in this build")


# ── Vector_time ──────────────────────────────────────────────────────────────

def test_vector_time_module_loads():
    try:
        import vector_time
        assert callable(vector_time.now)
    except ImportError:
        pytest.skip("vector_time not in this build")


# ── Tool result helpers ───────────────────────────────────────────────────────

def test_tool_error_returns_json():
    from tools.registry import tool_error
    s = tool_error("test error")
    parsed = json.loads(s)
    assert isinstance(parsed, dict)


def test_tool_result_returns_json():
    from tools.registry import tool_result
    s = tool_result({"x": 1})
    parsed = json.loads(s)
    assert parsed is not None
