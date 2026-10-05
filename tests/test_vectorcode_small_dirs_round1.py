"""Regression tests for the small vectorcode source-directory audit."""

from __future__ import annotations

from types import SimpleNamespace

from loguru import logger
import pytest

from vectorcode.src.a2a.protocol import AgentCard
from vectorcode.src.a2a.server import A2AServer
from vectorcode.src.operators.manager import OperatorManager
from vectorcode.src.operators.types import OperatorManifest
from vectorcode.src.persona import person_model as person_model_module
from vectorcode.src.persona.person_model import PersonModel
from vectorcode.src.recipes.composer import recipe_to_operator
from vectorcode.src.recipes.loader import Recipe, load_recipe
from vectorcode.src.vc_sessions.store import SessionStore
from vectorcode.src.transports.chat_completions import ChatCompletionsTransport
from vectorcode.src.transports import list_transports


def test_a2a_handler_failure_is_logged_with_exception() -> None:
    messages: list[str] = []
    sink = logger.add(messages.append, format="{message} | {exception}")
    server = A2AServer(
        AgentCard(name="test", description="test", url="http://localhost"),
        handler=lambda _text: (_ for _ in ()).throw(RuntimeError("handler broke")),
    )
    try:
        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "request-1",
                "method": "tasks/send",
                "params": {"input": "hello"},
            }
        )
    finally:
        logger.remove(sink)

    assert response["result"]["state"] == "failed"
    assert any("handler failed" in message for message in messages)
    assert any("RuntimeError: handler broke" in message for message in messages)


class _Store:
    def __init__(self) -> None:
        self.tasks: dict[str, dict] = {}

    def save_task(self, task: dict) -> None:
        self.tasks[task["id"]] = dict(task)

    def delete_task(self, task_id: str) -> None:
        del self.tasks[task_id]


class _Scheduler:
    def __init__(self) -> None:
        self._store = _Store()

    def list_tasks(self) -> list:
        return []

    def create_task(self, **kwargs):
        task = SimpleNamespace(
            id="random-id",
            status="active",
            to_dict=lambda: {"id": "random-id", "status": "active", **kwargs},
        )
        self._store.save_task(task.to_dict())
        return task


def test_operator_activation_replaces_random_scheduler_task() -> None:
    scheduler = _Scheduler()
    manager = OperatorManager(SimpleNamespace(scheduler=scheduler))
    manager.register(OperatorManifest(id="daily", name="Daily"))

    assert manager.activate("daily") == "operator:daily"
    assert set(scheduler._store.tasks) == {"operator:daily"}


def test_operator_logging_uses_loguru_formatting() -> None:
    messages: list[str] = []
    sink = logger.add(messages.append, format="{message}")
    try:
        manager = OperatorManager(SimpleNamespace(scheduler=None))
        manager.register(OperatorManifest(id="daily", name="Daily"))
    finally:
        logger.remove(sink)

    assert "Registered operator: daily\n" in messages
    assert all("%s" not in message for message in messages)


@pytest.mark.parametrize("session_id", ["../escape", "..\\escape", "a/b", "a\\b"])
def test_json_session_store_rejects_path_traversal(tmp_path, session_id: str) -> None:
    store = SessionStore(tmp_path / "sessions")

    with pytest.raises(ValueError, match="Invalid session_id"):
        store.save(session_id, {"secret": "value"})

    assert list(tmp_path.rglob("*.json")) == []


def test_json_session_store_does_not_treat_corruption_as_missing(tmp_path) -> None:
    store = SessionStore(tmp_path)
    (tmp_path / "valid-id.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match="corrupt"):
        store.load("valid-id")


def test_recipe_max_tokens_is_loaded_and_forwarded(tmp_path) -> None:
    recipe_path = tmp_path / "recipe.toml"
    recipe_path.write_text(
        '[recipe]\nname = "bounded"\n[agent]\nmax_tokens = 321\n',
        encoding="utf-8",
    )

    recipe = load_recipe(recipe_path)

    assert recipe.max_tokens == 321
    assert recipe.to_builder_kwargs()["max_tokens"] == 321


def test_operator_recipe_preserves_zero_temperature() -> None:
    manifest = recipe_to_operator(
        Recipe(name="deterministic", schedule_type="interval", temperature=0.0)
    )

    assert manifest.temperature == 0.0


def test_chat_transport_preserves_usage_from_json_response() -> None:
    response = {
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
            "prompt_tokens_details": {"cached_tokens": 5, "cache_write_tokens": 2},
        },
    }

    transport = ChatCompletionsTransport()
    normalized = transport.normalize_response(response)

    assert normalized.usage is not None
    assert normalized.usage.prompt_tokens == 11
    assert normalized.usage.completion_tokens == 7
    assert normalized.usage.total_tokens == 18
    assert transport.extract_cache_stats(response) == {
        "cached_tokens": 5,
        "creation_tokens": 2,
    }


def test_transport_modules_register_with_their_own_package() -> None:
    assert set(list_transports()) >= {"anthropic_messages", "chat_completions"}


def test_person_profile_name_cannot_escape_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(person_model_module, "_STORE", tmp_path)
    model = PersonModel()

    with pytest.raises(ValueError, match="Invalid person_name"):
        model.learn_from_messages("../outside", [{"content": "hello"}])

    assert list(tmp_path.rglob("*.json")) == []
