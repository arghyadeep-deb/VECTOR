"""Regression proofs for the 2026-10 core engine/memory/voice audit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_episodic_wrapper_close_does_not_kill_shared_connection(isolated_vector_db):
    from core.memory import episodic

    first = episodic.EpisodicMemory()
    second = episodic.EpisodicMemory()
    shared = episodic.get_db_connection()

    first.close()

    assert episodic.get_db_connection() is shared
    assert second.remember("audit:singleton-survives-close", "yes") is True
    assert second.recall_fact("audit:singleton-survives-close")["value"] == "yes"


def test_wiki_export_confines_windows_style_source_ids_and_leaves_no_temp_files(tmp_path):
    from core.engine.memory_tree.tree_builder import MemoryTree
    from core.engine.memory_tree.wiki_formatter import WikiFormatter

    out = tmp_path / "wiki"
    tree = MemoryTree(db_dir=tmp_path / "db", wiki_dir=out)
    tree.ingest("conversation", r"..\..\escaped", "confined content", topic="audit")

    paths = WikiFormatter(tree).save_all(out)

    assert all(path.parent.resolve() == out.resolve() for path in paths)
    assert not (tmp_path / "escaped.md").exists()
    assert not list(out.glob("*.tmp"))
    tree.close()


def test_oauth_fallback_store_atomically_replaces_token_file(monkeypatch, tmp_path):
    from core.engine.oauth import flows

    monkeypatch.setattr(flows, "_TOKEN_DIR", tmp_path)
    monkeypatch.setattr(flows, "_KEYRING_AVAILABLE", False)
    manager = flows.OAuthFlowManager()

    manager.store_token("github", flows.OAuthToken(slug="github", access_token="new-token"))

    saved = json.loads((tmp_path / "github.json").read_text(encoding="utf-8"))
    assert saved["access_token"] == "new-token"
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.asyncio
async def test_oauth_refresh_endpoint_does_not_report_success_for_http_error(monkeypatch):
    from core.engine.oauth import server
    from core.engine.oauth.flows import OAuthToken

    if not server._FASTAPI_AVAILABLE:
        pytest.skip("FastAPI/httpx optional dependencies are unavailable")

    token = OAuthToken(slug="github", access_token="old", refresh_token="refresh")
    monkeypatch.setattr(server._flow_manager, "get_token", lambda slug: token)
    monkeypatch.setattr(server, "get_provider", lambda slug: type("Provider", (), {
        "token_url": "https://provider.invalid/token",
        "client_id": "client",
        "client_secret": "secret",
    })())

    class FailedResponse:
        def raise_for_status(self):
            import httpx
            raise httpx.HTTPStatusError("invalid grant", request=None, response=None)

        def json(self):
            return {"access_token": "should-not-be-used"}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FailedResponse()

    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kwargs: Client())
    route = next(
        route.endpoint for route in server.oauth_router.routes
        if route.path == "/refresh/{slug}"
    )

    with pytest.raises(server.HTTPException) as exc_info:
        await route("github")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail != "refreshed"


@pytest.mark.asyncio
async def test_subagent_default_llm_failure_is_not_reported_as_success(monkeypatch):
    from core.engine.agents.subagent_runner import SubagentOptions, SubagentRunner
    import core.inference.ollama_safe as ollama_safe

    monkeypatch.setattr(
        ollama_safe,
        "chat",
        lambda **kwargs: (_ for _ in ()).throw(ConnectionError("offline")),
    )
    monkeypatch.setattr(
        SubagentRunner,
        "_build_system_prompt",
        lambda self, options: "hydrated test prompt",
    )

    outcome = await SubagentRunner().run(SubagentOptions(agent_name="researcher", task="audit"))

    assert outcome.success is False
    assert outcome.result == ""
    assert "unavailable" in (outcome.error or "").lower()


def test_subagent_prompt_includes_session_hydration(monkeypatch):
    from core.engine.agents.subagent_runner import SubagentOptions, SubagentRunner
    from core.loop.context_engine import ContextEngine

    monkeypatch.setattr(ContextEngine, "session_hydration_prompt", lambda self: "LIVE HYDRATION")

    prompt = SubagentRunner()._build_system_prompt(
        SubagentOptions(agent_name="researcher", task="audit")
    )

    assert prompt.startswith("LIVE HYDRATION")


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_memory_mesh_retry_pass_terminates_and_does_not_duplicate(monkeypatch):
    from core.memory.multi_db_manager import MultiDBManager

    manager = MultiDBManager()
    manager.queue_sync({"table": "episodic_memory", "record": {"id": "offline"}, "attempt": 0})
    monkeypatch.setattr(manager, "_get_config", lambda key: None)
    monkeypatch.setattr(manager, "_push_local_to_cloud", lambda since: _async_value(0))
    monkeypatch.setattr(manager, "_pull_supabase", lambda: _async_value(None))
    monkeypatch.setattr(manager, "_pull_turso", lambda: _async_value(None))

    result = await manager.sync_all()

    assert result["queued"] == 1
    assert len(manager._sync_queue) == 1
    assert manager._sync_queue[0]["attempt"] == 1


@pytest.mark.asyncio
async def test_memory_mesh_does_not_claim_unconfigured_pulls(monkeypatch):
    from core.memory.multi_db_manager import MultiDBManager

    manager = MultiDBManager()
    monkeypatch.setattr(manager, "_get_config", lambda key: None)
    monkeypatch.setattr(manager, "_push_local_to_cloud", lambda since: _async_value(0))

    result = await manager.sync_all()

    assert result["pulled"] == 0
    assert manager.get_stats()["last_sync"]["supabase"] is None
    assert manager.get_stats()["last_sync"]["turso"] is None


@pytest.mark.asyncio
async def test_memory_mesh_does_not_advance_local_watermark_without_cloud(monkeypatch):
    from core.memory.multi_db_manager import MultiDBManager

    manager = MultiDBManager()
    monkeypatch.setattr(manager, "_get_config", lambda key: None)

    await manager.sync_all()

    assert manager.get_stats()["last_sync"]["local"] is None
