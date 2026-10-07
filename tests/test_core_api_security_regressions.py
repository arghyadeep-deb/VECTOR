"""Regression tests for security bugs found in the core/api depth audit."""

from __future__ import annotations

import asyncio
import inspect
import urllib.parse

from core.api.routers import oauth
from core.api.routers.websocket import require_auth_handshake, vector_ws_state


class _Client:
    def __init__(self, host: str) -> None:
        self.host = host


class _Socket:
    def __init__(self, host: str, payload: dict | None = None) -> None:
        self.client = _Client(host)
        self.payload = payload or {}
        self.closed: tuple[int, str] | None = None

    async def receive_json(self) -> dict:
        return self.payload

    async def close(self, code: int, reason: str) -> None:
        self.closed = (code, reason)


async def test_keyless_websocket_mode_rejects_remote_clients(monkeypatch) -> None:
    monkeypatch.setattr("core.api.routers.websocket.get_secret", lambda _name: "")
    ws = _Socket("203.0.113.10")
    assert await require_auth_handshake(ws) is False
    assert ws.closed and ws.closed[0] == 1008


def test_state_websocket_performs_authentication_before_subscribing() -> None:
    source = inspect.getsource(vector_ws_state)
    auth = source.index("require_auth_handshake")
    subscribe = source.index("get_event_bus")
    assert auth < subscribe


async def test_google_oauth_state_is_required_and_single_use(monkeypatch) -> None:
    monkeypatch.setattr(
        "core.config.CONFIG",
        {
            **__import__("core.config", fromlist=["CONFIG"]).CONFIG,
            "oauth_google_client_id": "client-id",
            "oauth_google_redirect_uri": "http://localhost/callback",
        },
    )
    oauth._pending_google_states.clear()
    result = await oauth.google_calendar_connect()
    query = urllib.parse.parse_qs(urllib.parse.urlparse(result["auth_url"]).query)
    state = query["state"][0]
    assert len(state) >= 32

    assert (await oauth.google_calendar_callback(code="code", state="wrong"))["error"]
    monkeypatch.setattr(oauth, "_consume_google_state", oauth._consume_google_state)
    assert oauth._consume_google_state(state) is True
    assert oauth._consume_google_state(state) is False


def test_hud_static_path_uses_component_aware_confinement() -> None:
    from core.api.app import create_app

    source = inspect.getsource(create_app)
    assert "file_path.is_relative_to(_hud_dir.resolve())" in source
    assert "str(file_path).startswith" not in source


def test_direct_api_llm_calls_hydrate_and_sync_inference_is_offloaded() -> None:
    from core.api.routers import inference, openai_compat, voice_ws

    inference_source = inspect.getsource(inference.inference_run)
    compat_source = inspect.getsource(openai_compat.chat_completions)
    stream_source = inspect.getsource(voice_ws._stream_respond)
    batch_source = inspect.getsource(voice_ws._llm_respond_with_personality)
    assert "session_hydration_prompt" in inference_source
    assert "asyncio.to_thread" in inference_source
    assert "session_hydration_prompt" in compat_source
    assert "session_hydration_prompt" in stream_source
    assert "session_hydration_prompt" in batch_source


def test_ads_output_paths_are_confined_and_cli_prompt_cannot_be_an_option() -> None:
    import pytest
    from pydantic import ValidationError
    from core.api.routers.ads import AdsGenerateRequest, AdsReportRequest

    with pytest.raises(ValidationError):
        AdsGenerateRequest(prompt="ok", output_dir="../outside")
    with pytest.raises(ValidationError):
        AdsReportRequest(audit_markdown="ok", output_path="C:/outside/report.pdf")
    with pytest.raises(ValidationError):
        AdsGenerateRequest(prompt="--batch")


def test_external_task_does_not_claim_acceptance_before_gateway_approval() -> None:
    from core.api.routers import tasks

    source = inspect.getsource(tasks.ingest_external_task)
    approval_check = source.index("if not result.approved")
    loop_injection = source.index("AutonomousLoop.get_instance")
    assert approval_check < loop_injection
    assert '"accepted": False' in source

    from core.api import tasks as internal_tasks
    internal_source = inspect.getsource(internal_tasks.submit_task)
    approval_check = internal_source.index("if not gateway_result.approved")
    loop_injection = internal_source.index("loop._pending_voice")
    assert approval_check < loop_injection
