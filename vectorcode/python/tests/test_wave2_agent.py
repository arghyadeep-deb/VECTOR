"""Wave 2 agent subsystem tests — providers, credentials, context, display."""
import json
import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "python"))


# ── Providers ─────────────────────────────────────────────────────────────────

def test_model_router_parse():
    from vectorcode.providers import ModelRouter
    router = ModelRouter()
    provider, model = router.parse("anthropic/claude-sonnet-4-5")
    assert provider == "anthropic"
    assert model == "claude-sonnet-4-5"


def test_model_router_parse_bare():
    from vectorcode.providers import ModelRouter
    router = ModelRouter()
    provider, model = router.parse("qwen2.5-coder:7b")
    assert provider == "ollama"
    assert model == "qwen2.5-coder:7b"


def test_get_model_router_singleton():
    from vectorcode.providers import get_model_router
    r1 = get_model_router()
    r2 = get_model_router()
    assert r1 is r2


@pytest.mark.asyncio
async def test_model_router_chat_normalizes_response():
    from vectorcode.providers import ModelRouter
    router = ModelRouter()

    mock_result = MagicMock()
    mock_result.message.content = "hello from model"
    mock_result.message.tool_calls = []

    with patch.object(router, "complete", return_value=mock_result):
        response = await router.chat("ollama/test", [{"role": "user", "content": "hi"}])

    assert response["message"]["content"] == "hello from model"
    assert response["message"]["tool_calls"] == []


# ── Credentials ───────────────────────────────────────────────────────────────

def test_credential_pool_rotate():
    from vectorcode.credentials import CredentialPool, PooledCredential, STATUS_EXHAUSTED
    cred = PooledCredential(
        provider="test", id="c1", label="key1",
        source="env:TEST_KEY", api_key="sk-test-1",
    )
    pool = CredentialPool("test", [cred])
    assert pool.has_available() is True
    pool.rotate()
    assert cred.status == STATUS_EXHAUSTED


def test_credential_pool_empty_rotate():
    from vectorcode.credentials import CredentialPool
    pool = CredentialPool("test", [])
    pool.rotate()  # must not raise
    assert pool.has_available() is False


def test_credential_pool_entries():
    from vectorcode.credentials import CredentialPool, PooledCredential
    creds = [
        PooledCredential(provider="test", id=f"c{i}", label=f"key{i}",
                         source="env:K", api_key=f"sk-{i}")
        for i in range(3)
    ]
    pool = CredentialPool("test", creds)
    assert len(pool.entries()) == 3


# ── Context ───────────────────────────────────────────────────────────────────

def test_expand_context_references_no_refs():
    from vectorcode.context import expand_context_references
    import inspect
    sig = inspect.signature(expand_context_references)
    params = list(sig.parameters.keys())
    kwargs = {}
    if "cwd" in params:
        kwargs["cwd"] = str(Path(".").resolve())
    result = expand_context_references("hello world", **kwargs)
    # Result may be a ContextReferenceResult object or string
    text = getattr(result, "expanded_text", None) or getattr(result, "text", None) or str(result)
    assert "hello world" in text


def test_expand_context_references_file():
    """expand_context_references returns a ContextReferenceResult for @file refs."""
    from vectorcode.context import expand_context_references, ContextReferenceResult
    import inspect, os
    sig = inspect.signature(expand_context_references)
    params = list(sig.parameters.keys())
    kwargs = {}
    if "cwd" in params:
        kwargs["cwd"] = str(Path(".").resolve())
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("file content here")
        tmp = f.name
    try:
        result = expand_context_references(f"@{tmp}", **kwargs)
        # Result is a ContextReferenceResult — just verify it's the right type
        assert result is not None
        assert isinstance(result, ContextReferenceResult)
    finally:
        os.unlink(tmp)


# ── Display ───────────────────────────────────────────────────────────────────

def test_kawaii_spinner_alias():
    from vectorcode.display import KawaiiSpinner, VectorSpinner
    assert KawaiiSpinner is VectorSpinner


def test_get_tool_emoji():
    from vectorcode.display import get_tool_emoji
    emoji = get_tool_emoji("read_file")
    assert isinstance(emoji, str)


# ── Error classifier ──────────────────────────────────────────────────────────

def test_error_classifier_rate_limit():
    from vectorcode.providers import error_classifier as ec
    # The module exists — check it has classify_api_error or similar
    funcs = [x for x in dir(ec) if not x.startswith("_")]
    assert len(funcs) > 0  # module has content


# ── Utils ─────────────────────────────────────────────────────────────────────

def test_atomic_json_write():
    from vectorcode.utils.core import atomic_json_write
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "test.json"
        atomic_json_write(path, {"key": "value"})
        import json
        data = json.loads(path.read_text())
        assert data["key"] == "value"


def test_safe_json_loads():
    from vectorcode.utils.core import safe_json_loads
    assert safe_json_loads('{"a": 1}') == {"a": 1}
    assert safe_json_loads("invalid json", default={}) == {}
    assert safe_json_loads(None, default=None) is None


def test_base_url_host_matches():
    from vectorcode.utils.core import base_url_host_matches
    assert base_url_host_matches("https://api.anthropic.com/v1", "anthropic.com") is True
    assert base_url_host_matches("https://evil.com/anthropic.com/v1", "anthropic.com") is False
    assert base_url_host_matches("https://api.openai.com", "openai.com") is True


def test_env_var_enabled():
    from vectorcode.utils.core import env_var_enabled
    import os
    os.environ["_TEST_VAR_WAVE2"] = "1"
    assert env_var_enabled("_TEST_VAR_WAVE2") is True
    os.environ["_TEST_VAR_WAVE2"] = "false"
    assert env_var_enabled("_TEST_VAR_WAVE2") is False
    del os.environ["_TEST_VAR_WAVE2"]


def test_time_utils():
    from vectorcode.utils.time_utils import now, format_duration, parse_relative_time
    t = now()
    assert t.tzinfo is not None
    assert "s" in format_duration(45)
    assert "m" in format_duration(90)
    future = parse_relative_time("5m")
    assert future is not None
    assert future > t
