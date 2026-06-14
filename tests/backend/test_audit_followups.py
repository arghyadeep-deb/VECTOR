from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import importlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]


def test_fincept_base_points_to_absorbed_vector_finagent_tree() -> None:
    from districts.investment import finagent_agent

    assert finagent_agent._FINCEPT_BASE.name == "vector_finagent"
    assert finagent_agent._FINCEPT_BASE.exists()
    assert (finagent_agent._FINCEPT_BASE / "agents" / "TraderInvestorsAgent").exists()
    assert finagent_agent._load_investor_personas()


def test_voice_tts_accepts_profile_name_keyword() -> None:
    from core.voice.tts import VoiceTTS

    signature = inspect.signature(VoiceTTS.speak)
    assert "profile_name" in signature.parameters
    tts = VoiceTTS()
    assert "profile_name" in tts.speak.__code__.co_varnames


def test_voice_profile_reference_storage_uses_local_driver(tmp_path: Path) -> None:
    from core.collections.storage import FileStorage, LocalDriver
    from core.voice.voice_profiles import ProfileType, VoiceProfile, VoiceProfileStore

    store = VoiceProfileStore(storage=FileStorage(LocalDriver(tmp_path)))
    name = f"AuditVoice_{uuid.uuid4().hex[:8]}"
    profile = VoiceProfile(name=name, type=ProfileType.CLONED)
    store.create(profile)

    key = store.upload_reference(name, b"RIFFfake-wave", "reference.wav")

    assert key.startswith(f"voice_profiles/{name}/")
    assert store.get_reference_bytes(name) == b"RIFFfake-wave"


def test_comfyui_adapter_exposes_operational_sidecar_methods() -> None:
    from districts.content.comfyui_adapter import ComfyUIAdapter

    adapter = ComfyUIAdapter()
    for method in (
        "get_system_stats",
        "get_node_info",
        "list_model_types",
        "list_models_by_type",
        "get_history",
        "get_jobs",
        "interrupt",
        "free_memory",
        "upload_image",
    ):
        assert hasattr(adapter, method)


def test_comfyui_upload_image_rejects_missing_file() -> None:
    from districts.content.comfyui_adapter import ComfyUIAdapter

    result = asyncio.run(ComfyUIAdapter().upload_image("does-not-exist.png"))

    assert result["status"] == "error"
    assert "image not found" in result["error"]


def test_template_python_expression_rejects_dunder_breakout() -> None:
    from vectorcode.src.vc_tools.templates.loader import ToolTemplate

    template = ToolTemplate(
        {
            "name": "unsafe_expr",
            "action": {
                "type": "python",
                "expression": "__import__('os').system('echo unsafe')",
            },
        }
    )

    result = template.execute()

    assert result.success is False
    assert "not allowed" in result.content or "unknown name" in result.content


def test_template_shell_rejects_substitution_payloads() -> None:
    from vectorcode.src.vc_tools.templates.loader import ToolTemplate

    template = ToolTemplate(
        {
            "name": "unsafe_shell",
            "action": {"type": "shell", "command": "echo {value}"},
        }
    )

    for payload in ("$(whoami)", "`whoami`", "ok; whoami", "ok\nwhoami", "ok > out"):
        result = template.execute(value=payload)
        assert result.success is False
        assert "Rejected unsafe shell parameter" in result.content


def test_slack_daemon_spawn_keeps_tokens_out_of_argv(monkeypatch) -> None:
    from vectorcode.src.comms import slack_daemon

    captured: dict = {}

    class DummyPopen:
        pid = 4242

        def __init__(self, args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs

    monkeypatch.setattr(subprocess, "Popen", DummyPopen)

    pid = slack_daemon.start_slack_daemon("xoxb-secret", "xapp-secret", model="m")

    assert pid == 4242
    assert "xoxb-secret" not in captured["args"]
    assert "xapp-secret" not in captured["args"]
    assert captured["kwargs"]["env"]["SLACK_BOT_TOKEN"] == "xoxb-secret"
    assert captured["kwargs"]["env"]["SLACK_APP_TOKEN"] == "xapp-secret"


def test_optional_engine_shims_import_without_process_exit() -> None:
    nexa = importlib.import_module("vectorcode.src.vc_engine.nexa_shim")
    apple = importlib.import_module("vectorcode.src.vc_engine.apple_fm_shim")

    assert hasattr(nexa, "app")
    assert hasattr(apple, "app")


def _load_brain_app(module_name: str):
    cloud_dir = ROOT / "cloud" / "brain_server"
    sys.path.insert(0, str(cloud_dir))
    try:
        spec = importlib.util.spec_from_file_location(module_name, cloud_dir / "main.py")
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod.app
    finally:
        try:
            sys.path.remove(str(cloud_dir))
        except ValueError:
            pass


def test_brain_server_fails_closed_without_api_key_in_production(monkeypatch) -> None:
    monkeypatch.setenv("VECTOR_ENV", "production")
    monkeypatch.delenv("VECTOR_API_KEY", raising=False)

    client = TestClient(_load_brain_app("brain_server_no_key_test"))

    assert client.get("/status").status_code == 200
    response = client.get("/agents")
    assert response.status_code == 503


def test_brain_server_rejects_wrong_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("VECTOR_ENV", "production")
    monkeypatch.setenv("VECTOR_API_KEY", "k" * 40)

    client = TestClient(_load_brain_app("brain_server_wrong_key_test"))

    response = client.get("/agents", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_code_interpreter_disabled_by_default(monkeypatch) -> None:
    from vectorcode.src.vc_tools.code_interpreter import CodeInterpreterTool

    monkeypatch.delenv("VECTOR_ENABLE_UNTRUSTED_CODE", raising=False)

    result = CodeInterpreterTool().execute(code="print('hello')")

    assert result.success is False
    assert "disabled by default" in result.content


def test_repl_disabled_by_default(monkeypatch) -> None:
    from vectorcode.src.vc_tools.repl import ReplTool

    monkeypatch.delenv("VECTOR_ENABLE_UNTRUSTED_CODE", raising=False)

    result = ReplTool().execute(code="1 + 1")

    assert result.success is False
    assert "disabled by default" in result.content


def test_core_errors_uses_vector_specific_timeout_name() -> None:
    import core.errors as errors

    assert hasattr(errors, "VectorTimeoutError")
    assert not hasattr(errors, "TimeoutError")
    assert "VectorTimeoutError" in errors.__all__
    assert "TimeoutError" not in errors.__all__


def test_context_engine_sense_cache_snapshot_is_thread_safe() -> None:
    from core.loop.context_engine import (
        get_sense_cache_snapshot,
        update_sense_cache,
    )

    def writer(index: int) -> str:
        update_sense_cache(screen_summary=f"screen {index}", presence="present")
        return get_sense_cache_snapshot()["presence"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(writer, range(100)))

    snapshot = get_sense_cache_snapshot()
    assert all(result == "present" for result in results)
    assert snapshot["presence"] == "present"
    assert snapshot["screen_summary"].startswith("screen ")


def test_sqlite_memory_falls_back_when_rust_bridge_unavailable(tmp_path, monkeypatch) -> None:
    import vectorcode.src._rust_bridge as rust_bridge
    from vectorcode.src.vc_tools.storage.sqlite import SQLiteMemory

    def unavailable():
        raise RuntimeError("rust disabled for test")

    monkeypatch.setattr(rust_bridge, "get_rust_module", unavailable)

    memory = SQLiteMemory(tmp_path / "memory.db")
    try:
        doc_id = memory.store(
            "VECTOR stores production memories",
            source="audit",
            metadata={"phase": "fallback"},
        )
        results = memory.retrieve("production", top_k=1)

        assert memory.count() == 1
        assert results[0].content == "VECTOR stores production memories"
        assert results[0].metadata["phase"] == "fallback"
        assert memory.delete(doc_id) is True
        assert memory.count() == 0
    finally:
        memory.close()


def test_spawned_agent_registry_returns_isolated_snapshot() -> None:
    from vectorcode.src.vc_tools import agent_tools

    with agent_tools._SPAWNED_AGENTS_LOCK:
        agent_tools._SPAWNED_AGENTS.clear()

    result = agent_tools.AgentSpawnTool().execute(
        agent_type="simple",
        agent_id="audit-agent",
    )
    assert result.success is True

    snapshot = agent_tools.get_spawned_agents_snapshot()
    snapshot["audit-agent"]["status"] = "tampered"

    fresh_snapshot = agent_tools.get_spawned_agents_snapshot()
    assert fresh_snapshot["audit-agent"]["status"] == "running"

    listed = agent_tools.AgentListTool().execute()
    assert json.loads(listed.content)[0]["agent_id"] == "audit-agent"


def test_async_streaming_engines_do_not_use_blocking_httpx_streams() -> None:
    for rel_path in (
        "vectorcode/src/vc_engine/_openai_compat.py",
        "vectorcode/src/vc_engine/ollama.py",
    ):
        source = (ROOT / rel_path).read_text(encoding="utf-8")
        assert "httpx.AsyncClient" in source
        assert "async with self._async_client.stream" in source
        assert "async for line in resp.aiter_lines()" in source
        assert "with self._client.stream" not in source
        assert "for line in resp.iter_lines()" not in source


def test_vectorcode_core_imports_work_outside_repo_cwd(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    code = """
import vectorcode
import vectorcode.src.command_registry
import vectorcode.src.event_bus_hooks
import vectorcode.src.vc_agents.tool_agent
import vectorcode.src.vc_system.core
import core.config
print("ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_security_block_error_has_single_canonical_class() -> None:
    from vectorcode.src.vc_security.boundary import SecurityBlockError as BoundaryError
    from vectorcode.src.vc_security.guardrails import SecurityBlockError as GuardrailsError

    assert BoundaryError is GuardrailsError


def test_issue_06_secret_fallbacks_are_not_hardcoded() -> None:
    checked_files = (
        "vectorcode/src/tools/terminal_tool.py",
        "vectorcode/src/gateway/platforms/webhook.py",
        "vectorcode/src/vector_cli/webhook.py",
        "districts/governance/federation_agent.py",
        "core/network/ofp_protocol.py",
        "core/training/openmythos/forward.py",
    )
    forbidden = (
        "change-me-in-dotenv",
        "vector-default-secret",
        "vector_default_secret",
    )

    for rel_path in checked_files:
        source = (ROOT / rel_path).read_text(encoding="utf-8")
        assert not re.search(
            r"^\s*password\s*=\s*['\"]SUDO_PASSWORD['\"]",
            source,
            flags=re.MULTILINE,
        )
        for marker in forbidden:
            assert marker not in source, f"{marker!r} still present in {rel_path}"

    cli_webhook = (ROOT / "vectorcode/src/vector_cli/webhook.py").read_text(encoding="utf-8")
    assert "your-global-hmac-secret" not in cli_webhook
    assert "your-global-secret" not in cli_webhook


def test_webhook_adapter_rejects_placeholder_and_insecure_prod_secret(monkeypatch) -> None:
    import vectorcode  # noqa: F401
    from gateway.config import PlatformConfig
    from gateway.platforms.webhook import WebhookAdapter

    adapter = WebhookAdapter(
        PlatformConfig(
            enabled=True,
            extra={"routes": {"bad": {"secret": "your-global-secret"}}},
        )
    )
    try:
        asyncio.run(adapter.connect())
    except ValueError as exc:
        assert "placeholder HMAC secret" in str(exc)
    else:
        raise AssertionError("placeholder webhook secret was accepted")

    monkeypatch.setenv("VECTOR_ENV", "production")
    prod_adapter = WebhookAdapter(
        PlatformConfig(
            enabled=True,
            extra={"routes": {"bad": {"secret": "INSECURE_NO_AUTH"}}},
        )
    )
    try:
        asyncio.run(prod_adapter.connect())
    except ValueError as exc:
        assert "disables HMAC auth in production" in str(exc)
    else:
        raise AssertionError("INSECURE_NO_AUTH was accepted in production")


def test_sqlite_runtime_stores_tolerate_concurrent_writes(tmp_path: Path) -> None:
    from core.city.meta_cognition import MetaCognition
    from core.memory.causal_graph import CausalGraph
    from core.memory.counterfactual import CounterfactualMemory
    from districts.emergency.log import EmergencyLog, EmergencyLogEntry
    from districts.predictive_analytics.prediction_store import PredictionStore

    counterfactual = CounterfactualMemory(str(tmp_path / "counterfactual.db"))
    meta = MetaCognition(str(tmp_path / "meta.db"))
    emergency = EmergencyLog(str(tmp_path / "emergency.db"))
    prediction = PredictionStore(str(tmp_path / "prediction.db"))
    causal = CausalGraph(str(tmp_path / "causal.json"))

    def write(index: int) -> None:
        counterfactual.record_rejection(
            f"decision-{index}",
            f"proposal {index}",
            "audit concurrency check",
        )
        meta.observe(f"thought {index}", 0.6, "success", "audit")
        emergency.append(
            EmergencyLogEntry(
                event_id=f"evt-{index}",
                severity="LOW",
                domain="audit",
                signal_name="concurrency",
                detected_at=time.time() + index,
            )
        )
        prediction.store_accuracy(
            {
                "forecast_id": f"forecast-{index}",
                "metric_name": "audit",
                "model_used": "test",
                "rmse": 0.1,
                "actual_value": index,
                "predicted_value": index,
            }
        )
        causal.add_node(f"node-{index}", "audit", f"node {index}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write, range(40)))

    assert counterfactual.get_rejection_patterns()["total_rejections"] == 40
    assert meta.get_self_report()["total_thoughts"] == 40
    assert emergency.summary(days=10000)["total_emergencies"] == 40
    assert len(prediction.get_model_leaderboard("audit")) == 1
    assert causal.get_graph_summary()["total_nodes"] == 40

    counterfactual.close()
    meta.close()
    prediction.close()


def test_issue_26_semantic_memory_search_returns_persisted_concepts() -> None:
    from core.memory.semantic import SemanticMemory

    semantic = SemanticMemory()
    token = f"audit_semantic_{uuid.uuid4().hex}"
    semantic.store(token, f"production hardening search value {token}", category="audit")

    results = semantic.search("production hardening", limit=5, category="audit")

    assert any(result["concept"] == token for result in results)


def test_issue_26_reasoning_memory_search_returns_stored_chains() -> None:
    from core.memory.reasoning_memory import ReasoningMemory

    reasoning = ReasoningMemory()
    token = f"audit_reasoning_{uuid.uuid4().hex}"
    chain_id = reasoning.store_chain(
        situation=f"{token} user asked for production readiness",
        goal_ids=["audit"],
        steps=["inspect", "patch", "verify"],
        action="fix_audit_issue",
        outcome=f"{token} issue verified",
        reward=0.91,
    )

    results = reasoning.search_chains(token, limit=3)
    injected = reasoning.inject_past_reasoning(token, limit=1)

    assert chain_id
    assert any(result["id"] == chain_id for result in results)
    assert "PAST REASONING" in injected


def test_issue_26_digest_evaluator_is_not_a_fixed_perfect_score() -> None:
    from vectorcode.src.vc_agents.digest_evaluator import DigestEvaluator

    evaluator = DigestEvaluator()
    empty_score, empty_feedback = evaluator.evaluate({}, "")
    useful_score, useful_feedback = evaluator.evaluate(
        {"schedule": "meeting", "tasks": ["review production readiness"]},
        (
            "Today has a production readiness review. The priority is to check "
            "security tasks, confirm test results, and prepare a short follow-up "
            "message with any remaining blockers."
        ),
    )

    assert empty_score == 0.0
    assert useful_score > empty_score
    assert useful_score < 10.0
    assert "empty" in empty_feedback.lower()
    assert useful_feedback


def test_digest_store_compat_import_uses_canonical_hardened_store() -> None:
    from vectorcode.src.agents.digest_store import DigestStore as LegacyDigestStore
    from vectorcode.src.vc_agents.digest_store import DigestStore as CanonicalDigestStore

    assert LegacyDigestStore is CanonicalDigestStore


def test_digest_store_tolerates_concurrent_writes(tmp_path: Path) -> None:
    from datetime import datetime

    from vectorcode.src.vc_agents.digest_store import DigestArtifact, DigestStore

    store = DigestStore(str(tmp_path / "digest.db"))

    def save(index: int) -> None:
        store.save(
            DigestArtifact(
                text=f"digest {index}",
                audio_path=Path(""),
                sections={"summary": str(index)},
                sources_used=["audit"],
                generated_at=datetime.utcnow(),
                model_used="test",
                voice_used="test",
                quality_score=7.5,
                evaluator_feedback="ok",
            )
        )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(save, range(30)))

        assert len(store.history(limit=100)) == 30
        assert store.get_latest() is not None
    finally:
        store.close()


def test_security_audit_log_tolerates_concurrent_hash_chain_writes(tmp_path: Path) -> None:
    from vectorcode.src.vc_security.audit import AuditLogger
    from vectorcode.src.vc_security.types import SecurityEvent, SecurityEventType

    audit = AuditLogger(tmp_path / "audit.db")

    def log(index: int) -> None:
        audit.log(
            SecurityEvent(
                event_type=SecurityEventType.TOOL_BLOCKED,
                timestamp=time.time() + index,
                content_preview=f"event {index}",
                action_taken="blocked",
            )
        )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(log, range(30)))

        assert audit.count() == 30
        assert audit.verify_chain() == (True, None)
    finally:
        audit.close()


def test_agent_manager_tolerates_concurrent_state_writes(tmp_path: Path) -> None:
    from vectorcode.src.vc_agents.manager import AgentManager

    manager = AgentManager(str(tmp_path / "agents.db"))
    agent = manager.create_agent("audit-agent")
    agent_id = agent["id"]

    def write(index: int) -> None:
        task = manager.create_task(agent_id, f"task {index}")
        manager.update_task(task["id"], status="done", progress={"index": index})
        manager.send_message(agent_id, f"user message {index}")
        manager.store_agent_response(agent_id, f"agent response {index}")
        manager.save_checkpoint(
            agent_id,
            f"tick-{index}",
            {"messages": [index]},
            {"tools": []},
        )
        manager.add_learning_log(agent_id, "audit", data={"index": index})
        manager.update_summary_memory(agent_id, f"summary {index}")

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write, range(30)))

        assert len(manager.list_tasks(agent_id)) == 30
        assert len(manager.list_messages(agent_id, limit=100)) == 60
        assert len(manager.list_checkpoints(agent_id)) <= manager._CHECKPOINT_RETENTION
        assert len(manager.list_learning_log(agent_id, limit=100)) == 30
    finally:
        manager.close()


def test_vector_state_handoff_reads_are_serialized_with_writes(tmp_path: Path) -> None:
    from vectorcode.src.vector_state import SessionDB

    db = SessionDB(tmp_path / "state.db")
    session_ids = [f"handoff-{index}" for index in range(24)]
    for session_id in session_ids:
        db.create_session(session_id, "audit")

    def exercise(index: int) -> None:
        session_id = session_ids[index % len(session_ids)]
        db.request_handoff(session_id, "web")
        state = db.get_handoff_state(session_id)
        assert state is None or state["state"] in {"pending", "running", "completed"}
        db.list_pending_handoffs()
        if db.claim_handoff(session_id):
            db.complete_handoff(session_id)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(exercise, range(80)))

        assert db.session_count(source="audit") == len(session_ids)
    finally:
        db.close()


def test_swarm_database_tolerates_concurrent_access(tmp_path: Path, monkeypatch) -> None:
    import vectorcode.src.memory.swarm_db as swarm_db

    monkeypatch.setattr(swarm_db, "_DB_ROOT", tmp_path)
    db = swarm_db.SwarmDatabase("audit")

    def write(index: int) -> None:
        agent_id = f"agent-{index % 5}"
        db.save_agent_state(
            agent_id,
            {
                "name": agent_id,
                "type": "audit",
                "hp": 500 + index,
                "status": "idle",
                "tasks_completed": index,
            },
        )
        db.record_task(f"task-{index}", f"task {index}", agent_id, outcome="completed")
        db.record_decision(f"decision-{index}", {"task": f"task {index}"})
        db.record_metric(active=index % 3, idle=1, busy=2, topology="audit")
        assert db.load_agent_state(agent_id) is not None
        db.get_swarm_history(limit=20)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write, range(40)))

        history = db.get_swarm_history(limit=100)
        assert len(history["agents"]) == 5
        assert len(history["tasks"]) == 40
        assert len(history["decisions"]) == 40
    finally:
        db.close()


def test_district_runtime_histories_are_bounded(monkeypatch) -> None:
    import httpx

    from districts.calls.call_screener import CallScreener, _MAX_CALL_HISTORY
    from districts.calls.voice_responder import VoiceResponder, _MAX_RESPONSE_HISTORY
    from districts.content.uploader import Uploader, _MAX_UPLOAD_HISTORY
    import districts.startups._base as startup_base
    from districts.startups.competitor_spy import CompetitorSpy, _MAX_COMPETITOR_MOVES
    from districts.startups.market_scanner import MarketScanner, _MAX_SCAN_HISTORY

    class _DummyObsidian:
        pass

    monkeypatch.setattr(startup_base, "ObsidianSync", _DummyObsidian)

    screener = CallScreener()
    for index in range(_MAX_CALL_HISTORY + 5):
        screener._call_history.append({"timestamp": str(index)})
    monkeypatch.setattr(screener, "_analyze_spam_with_llm", lambda *a, **k: {"score": 0.0, "reason": "test"})
    screener.screen_call("1111111111")
    assert len(screener._call_history) == _MAX_CALL_HISTORY

    class _FakeOllamaResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"response": "ok"}

    responder = VoiceResponder()
    responder._response_history = [{"timestamp": str(i)} for i in range(_MAX_RESPONSE_HISTORY + 5)]
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _FakeOllamaResponse())
    responder.generate_response("hello")
    assert len(responder._response_history) == _MAX_RESPONSE_HISTORY

    uploader = Uploader()
    for index in range(_MAX_UPLOAD_HISTORY + 5):
        uploader._remember_upload({"platform": "test", "timestamp": str(index)})
    assert len(uploader._upload_history) == _MAX_UPLOAD_HISTORY

    scanner = MarketScanner()
    scanner.scan_history = [{"niche": str(i)} for i in range(_MAX_SCAN_HISTORY + 5)]
    monkeypatch.setattr(scanner, "_call_ollama", lambda *a, **k: "{}")
    scanner.scan_market("audit")
    assert len(scanner.scan_history) == _MAX_SCAN_HISTORY

    spy = CompetitorSpy()
    spy.movement_history["audit"] = [{"move": str(i)} for i in range(_MAX_COMPETITOR_MOVES + 5)]
    monkeypatch.setattr(
        spy,
        "_call_ollama",
        lambda *a, **k: '{"recent_moves":[{"move_type":"x","description":"y"}]}',
    )
    spy.track_movements("audit")
    assert len(spy.movement_history["audit"]) == _MAX_COMPETITOR_MOVES


def test_session_store_tolerates_concurrent_message_writes(tmp_path: Path) -> None:
    from vectorcode.src.server.session_store import SessionStore

    store = SessionStore(str(tmp_path / "sessions.db"))
    store.get_or_create("audit-user", "web")

    def write(index: int) -> None:
        store.append_message("audit-user", "web", "user", f"message {index}")
        store.set_pending_response("audit-user", "web", f"pending {index}")

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write, range(40)))

        session = store.get_or_create("audit-user", "web")
        assert len(session["conversation_history"]) == 20
        assert session["pending_response"].startswith("pending ")
    finally:
        store.close()


def test_knowledge_graph_store_tolerates_concurrent_writes(tmp_path: Path) -> None:
    from vectorcode.src.vc_tools.storage.knowledge_graph import (
        Entity,
        KnowledgeGraphMemory,
        Relation,
    )

    graph = KnowledgeGraphMemory(tmp_path / "knowledge_graph.db")

    def write(index: int) -> None:
        source = Entity(f"source-{index}", "audit", f"source {index}")
        target = Entity(f"target-{index}", "audit", f"target {index}")
        graph.add_entity(source)
        graph.add_entity(target)
        graph.add_relation(Relation(source.entity_id, target.entity_id, "links"))

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write, range(30)))

        assert graph.entity_count() == 60
        assert graph.relation_count() == 30
        assert graph.neighbors("source-0", relation_type="links")[0].entity_id == "target-0"
    finally:
        graph.close()


def test_mcp_security_and_hp_validator_tolerate_concurrent_access(tmp_path: Path) -> None:
    from core.security.hp_validator import HPValidator
    from core.security.mcp_security import MCPSecurityMiddleware, ToolCallRecord

    middleware = MCPSecurityMiddleware(tmp_path / "mcp_audit.db")
    validator = HPValidator(tmp_path / "hp_validator.db")

    def write(index: int) -> None:
        assert middleware.check_rate_limit(f"district-{index % 4}", "read_file")
        middleware.audit_call(
            ToolCallRecord(
                tool_name="read_file",
                source_district=f"district-{index % 4}",
                params={"index": index},
                timestamp=time.time() + index,
                allowed=True,
                risk_level="low",
            )
        )
        validator.validate(float(index % 10), f"agent-{index % 3}", "audit", {})

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write, range(40)))

    assert len(middleware.get_recent_calls(limit=100)) == 40
    assert len(validator.get_agent_history("agent-0", days=1)) > 0


def test_telemetry_trace_and_connector_stores_tolerate_concurrent_access(tmp_path: Path) -> None:
    from core.telemetry.aggregator import TelemetryAggregator
    from core.telemetry.store import TelemetryStore
    from vectorcode.src.connectors.attachment_store import AttachmentStore
    from vectorcode.src.connectors.store import KnowledgeStore
    from vectorcode.src.vc_core.types import StepType, TelemetryRecord, Trace, TraceStep
    from vectorcode.src.vc_traces.store import TraceStore

    telemetry = TelemetryStore(tmp_path / "telemetry.db")
    traces = TraceStore(tmp_path / "traces.db")
    knowledge = KnowledgeStore(tmp_path / "knowledge.db")
    attachments = AttachmentStore(str(tmp_path / "attachments"))

    def write(index: int) -> None:
        telemetry.record(
            TelemetryRecord(
                timestamp=time.time() + index,
                model_id="audit-model",
                total_tokens=index + 1,
                engine="audit",
            )
        )
        traces.save(
            Trace(
                trace_id=f"trace-{index}",
                query=f"query {index}",
                agent="audit",
                result=f"result {index}",
                started_at=time.time() + index,
                steps=[
                    TraceStep(
                        step_type=StepType.GENERATE,
                        timestamp=time.time(),
                        output={"tokens": index},
                    )
                ],
            )
        )
        knowledge.store(
            f"production hardening connector chunk {index}",
            source="audit",
            doc_id=f"doc-{index}",
        )
        attachments.store(
            f"attachment-{index}".encode("utf-8"),
            filename=f"{index}.txt",
            source_doc_id=f"doc-{index}",
        )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write, range(25)))

        assert len(telemetry.list_recent(limit=100)) == 25
        assert TelemetryAggregator(tmp_path / "telemetry.db").record_count() == 25
        assert traces.count() == 25
        assert len(traces.search("query", agent="audit", limit=50)) == 25
        assert knowledge.count() == 25
        assert len(knowledge.retrieve("production", source="audit", top_k=30)) == 25
    finally:
        telemetry.close()
        traces.close()
        knowledge.close()
        attachments.close()


def test_session_and_response_stores_tolerate_concurrent_access(tmp_path: Path) -> None:
    from vectorcode.src.gateway.platforms.api_server import ResponseStore
    from vectorcode.src.vc_sessions.session import SessionStore as CrossChannelSessionStore

    sessions = CrossChannelSessionStore(tmp_path / "cross_channel_sessions.db")
    session = sessions.get_or_create("audit-user")
    responses = ResponseStore(max_size=100, db_path=str(tmp_path / "responses.db"))

    def write(index: int) -> None:
        sessions.save_message(session.session_id, "user", f"message {index}")
        response_id = f"resp-{index}"
        responses.put(response_id, {"index": index})
        responses.set_conversation(f"conversation-{index % 4}", response_id)
        assert responses.get(response_id)["index"] == index

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write, range(30)))

        loaded = sessions.get_or_create("audit-user")
        assert len(loaded.messages) >= 30
        assert all(responses.get_conversation(f"conversation-{i}") for i in range(4))
    finally:
        sessions.close()
        responses.close()


def test_system_legacy_package_reexports_canonical_vc_system() -> None:
    from vectorcode.src.system import SystemBuilder as LegacyBuilder
    from vectorcode.src.system import VectorSystem as LegacySystem
    from vectorcode.src.system.builder import SystemBuilder as LegacyBuilderModule
    from vectorcode.src.system.core import VectorSystem as LegacySystemModule
    from vectorcode.src.vc_system import SystemBuilder as CanonicalBuilder
    from vectorcode.src.vc_system import VectorSystem as CanonicalSystem

    assert LegacyBuilder is CanonicalBuilder
    assert LegacyBuilderModule is CanonicalBuilder
    assert LegacySystem is CanonicalSystem
    assert LegacySystemModule is CanonicalSystem


def test_tools_storage_legacy_adapters_use_canonical_implementations(tmp_path: Path) -> None:
    from vectorcode.src.tools.storage import ChunkConfig, chunk_text, ingest_path
    from vectorcode.src.tools.storage.context import ContextConfig
    from vectorcode.src.tools.storage.sqlite import SQLiteMemory as LegacySQLiteMemory
    from vectorcode.src.vc_tools.storage.context import ContextConfig as CanonicalContextConfig
    from vectorcode.src.vc_tools.storage.sqlite import SQLiteMemory as CanonicalSQLiteMemory

    source = tmp_path / "note.txt"
    source.write_text("alpha beta gamma delta epsilon", encoding="utf-8")

    assert ChunkConfig(size=10, overlap=2).to_canonical().chunk_size == 10
    assert chunk_text("alpha beta gamma", chunk_size=10, overlap=2)
    assert ingest_path(source) >= 1
    assert LegacySQLiteMemory is CanonicalSQLiteMemory
    assert ContextConfig is CanonicalContextConfig


def test_mcp_call_json_helper_returns_json_error() -> None:
    import json

    from core.mcp_server import _mcp_call_json

    def fail() -> None:
        raise RuntimeError("audit boom")

    payload = json.loads(_mcp_call_json("audit_test", fail))

    assert payload == {"error": "audit boom"}


def test_issue_26_investment_runtime_stubs_fail_closed_without_notimplemented(monkeypatch) -> None:
    import pytest

    from districts.investment.execution_engine import ExecutionEngine
    from districts.investment.vector_finagent.agents.finagent_core.paper_trading_bridge import (
        HostBridgeUnavailableError,
        PaperTradingBridge,
    )

    monkeypatch.delenv("ZERODHA_API_KEY", raising=False)
    monkeypatch.delenv("ZERODHA_ACCESS_TOKEN", raising=False)

    engine = ExecutionEngine()
    with pytest.raises(RuntimeError, match="Live trading is disabled"):
        asyncio.run(engine._execute_via_broker("TEST", "BUY", 1, "market", 0.0))

    bridge = PaperTradingBridge(use_host_bridge=True)
    with pytest.raises(HostBridgeUnavailableError, match="requires host runtime"):
        bridge.list_portfolios()


# ── Fix 17 follow-up tests: 3 newly-locked SQLite files ────────────────────


def test_faiss_index_metadata_crud_with_lock(tmp_path: Path) -> None:
    from vectorcode.src.memory.faiss_index import FAISSIndex

    idx = FAISSIndex(index_path=str(tmp_path / "test_idx"), dim=4)
    try:
        idx._meta_insert("doc-1", {"label": "alpha"})
        idx._meta_insert("doc-2", {"label": "beta"})
        assert idx._meta_get("doc-1") == {"label": "alpha"}
        assert idx._meta_get("doc-2") == {"label": "beta"}
        assert idx._meta_get("missing") == {}
        assert sorted(idx._meta_all_ids()) == ["doc-1", "doc-2"]
        idx._meta_delete("doc-1")
        assert idx._meta_get("doc-1") == {}
        assert idx._meta_all_ids() == ["doc-2"]
    finally:
        idx._meta_conn.close()


def test_faiss_index_add_search_delete_numpy_fallback(tmp_path: Path) -> None:
    import vectorcode.src.memory.faiss_index as faiss_mod
    from vectorcode.src.memory.faiss_index import FAISSIndex

    was_available = faiss_mod._FAISS_AVAILABLE
    faiss_mod._FAISS_AVAILABLE = False
    idx = None
    try:
        idx = FAISSIndex(index_path=str(tmp_path / "np_idx"), dim=3)
        idx.add("v1", [1.0, 0.0, 0.0], {"name": "x"})
        idx.add("v2", [0.0, 1.0, 0.0], {"name": "y"})
        idx.add("v3", [0.9, 0.1, 0.0], {"name": "z"})
        results = idx.search([1.0, 0.0, 0.0], k=2)
        assert len(results) == 2
        assert results[0]["id"] in ("v1", "v3")
        assert idx.size() == 3
        idx.delete("v2")
        assert idx.size() == 2
    finally:
        faiss_mod._FAISS_AVAILABLE = was_available
        if idx is not None:
            idx._meta_conn.close()


def test_faiss_index_concurrent_metadata_writes(tmp_path: Path) -> None:
    from vectorcode.src.memory.faiss_index import FAISSIndex

    idx = FAISSIndex(index_path=str(tmp_path / "concurrent_idx"), dim=4)

    def write_meta(index: int) -> None:
        idx._meta_insert(f"cid-{index}", {"i": index})

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write_meta, range(50)))

        all_ids = idx._meta_all_ids()
        assert len(all_ids) == 50
    finally:
        idx._meta_conn.close()


def test_post_job_tracker_full_lifecycle(tmp_path: Path) -> None:
    from districts.content.post_job import JobStatus, PostJobTracker

    tracker = PostJobTracker(db_path=tmp_path / "lifecycle.db")

    jid = tracker.create("youtube", "Test Video", {"video_id": "abc123"})
    job = tracker.get(jid)
    assert job is not None
    assert job.status == JobStatus.PENDING
    assert job.platform == "youtube"
    assert job.title == "Test Video"

    tracker.mark_publishing(jid)
    job = tracker.get(jid)
    assert job.status == JobStatus.PUBLISHING
    assert job.attempt_count == 1

    tracker.mark_published(jid, url="https://youtube.com/watch?v=abc123", metrics={"views": 0})
    job = tracker.get(jid)
    assert job.status == JobStatus.PUBLISHED
    assert job.url == "https://youtube.com/watch?v=abc123"
    assert job.is_terminal

    assert tracker.get("nonexistent") is None


def test_post_job_tracker_retry_exhaustion(tmp_path: Path) -> None:
    from districts.content.post_job import JobStatus, PostJobTracker

    tracker = PostJobTracker(db_path=tmp_path / "retry.db")

    jid = tracker.create("instagram", "Post", max_retries=2)
    tracker.mark_publishing(jid)
    tracker.mark_retrying(jid, error="timeout")
    assert tracker.get(jid).status == JobStatus.RETRYING
    tracker.mark_publishing(jid)
    tracker.mark_retrying(jid, error="timeout again")
    assert tracker.get(jid).status == JobStatus.FAILED
    assert len(tracker.get(jid).error_log) == 2


def test_post_job_tracker_cancel_and_queries(tmp_path: Path) -> None:
    from districts.content.post_job import JobStatus, PostJobTracker

    tracker = PostJobTracker(db_path=tmp_path / "queries.db")

    j1 = tracker.create("youtube", "V1")
    j2 = tracker.create("instagram", "V2")
    j3 = tracker.create("twitter", "V3")

    tracker.mark_publishing(j1)
    tracker.mark_published(j1, url="https://youtube.com/1")
    tracker.cancel(j3)

    pending = tracker.list_pending()
    assert len(pending) == 1
    assert pending[0].job_id == j2

    published = tracker.list_by_status(JobStatus.PUBLISHED)
    assert len(published) == 1
    assert published[0].job_id == j1

    cancelled = tracker.list_by_status(JobStatus.CANCELLED)
    assert len(cancelled) == 1

    yt = tracker.list_by_platform("youtube")
    assert len(yt) == 1

    s = tracker.summary()
    assert s.get("published") == 1
    assert s.get("cancelled") == 1


def test_post_job_tracker_concurrent_writes(tmp_path: Path) -> None:
    from districts.content.post_job import PostJobTracker

    tracker = PostJobTracker(db_path=tmp_path / "concurrent_jobs.db")

    def write(index: int) -> None:
        jid = tracker.create("platform", f"Job {index}")
        tracker.mark_publishing(jid)
        if index % 3 == 0:
            tracker.mark_published(jid, url="https://example.com")
        elif index % 3 == 1:
            tracker.mark_retrying(jid, error="timeout")
        else:
            tracker.mark_failed(jid, error="fatal")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write, range(40)))

    summary = tracker.summary()
    total = sum(summary.values())
    assert total == 40


def test_post_job_tracker_update_metrics(tmp_path: Path) -> None:
    from districts.content.post_job import PostJobTracker

    tracker = PostJobTracker(db_path=tmp_path / "metrics.db")

    jid = tracker.create("youtube", "Metrics Video")
    tracker.mark_publishing(jid)
    tracker.mark_published(jid, url="https://youtube.com/1", metrics={"views": 100})
    tracker.update_metrics(jid, {"views": 200, "likes": 50})

    job = tracker.get(jid)
    assert job.metrics["views"] == 200
    assert job.metrics["likes"] == 50


def test_data_engineer_pipeline_health_reports_structure() -> None:
    from districts.data_analytics.data_engineer import DataEngineer

    agent = DataEngineer()
    health = agent.inspect_pipeline_health()
    assert "db_exists" in health
    assert "tables" in health
    assert "health_score" in health
    assert "wal_mode" in health
    assert "issues" in health
    assert 0 <= health["health_score"] <= 100


def test_data_engineer_bronze_to_silver_rejects_invalid_table() -> None:
    from districts.data_analytics.data_engineer import DataEngineer

    agent = DataEngineer()
    result = agent.run_bronze_to_silver("not_a_bronze_table", ["strip_whitespace"])
    assert "error" in result
    assert "not a Bronze table" in result["error"]


def test_data_engineer_db_lock_attribute_exists() -> None:
    from districts.data_analytics.data_engineer import DataEngineer

    agent = DataEngineer()
    assert hasattr(agent, "_db_lock")
    import threading
    assert isinstance(agent._db_lock, type(threading.RLock()))


def test_slack_daemon_channels_shim_reexports_comms() -> None:
    from vectorcode.src.channels import slack_daemon as channels_shim
    from vectorcode.src.comms import slack_daemon as comms_canonical

    assert channels_shim.is_running is comms_canonical.is_running
    assert channels_shim.run_slack_daemon is comms_canonical.run_slack_daemon
    assert channels_shim.start_slack_daemon is comms_canonical.start_slack_daemon
    assert channels_shim.stop_daemon is comms_canonical.stop_daemon


def test_faiss_index_lock_attribute_is_rlock(tmp_path: Path) -> None:
    from vectorcode.src.memory.faiss_index import FAISSIndex
    import threading

    idx = FAISSIndex(index_path=str(tmp_path / "lock_check"), dim=4)
    try:
        assert isinstance(idx._lock, type(threading.RLock()))
    finally:
        idx._meta_conn.close()


def test_post_job_tracker_lock_attribute_is_rlock(tmp_path: Path) -> None:
    from districts.content.post_job import PostJobTracker
    import threading

    tracker = PostJobTracker(db_path=tmp_path / "lock_check.db")
    assert isinstance(tracker._lock, type(threading.RLock()))


def test_manage_tools_share_markdown_store_base() -> None:
    """Issue 27f: memory_manage / user_profile_manage de-duplicated onto a
    shared CRUD base instead of two byte-identical copies."""
    from vectorcode.src.vc_tools._markdown_store import MarkdownStoreTool
    from vectorcode.src.vc_tools.memory_manage import MemoryManageTool
    from vectorcode.src.vc_tools.user_profile_manage import UserProfileManageTool

    assert issubclass(MemoryManageTool, MarkdownStoreTool)
    assert issubclass(UserProfileManageTool, MarkdownStoreTool)
    # The CRUD implementation must live only on the base, not be redefined.
    for meth in ("_read", "_add", "_update", "_remove", "execute"):
        assert meth not in MemoryManageTool.__dict__
        assert meth not in UserProfileManageTool.__dict__


def test_manage_tools_crud_roundtrip(tmp_path: Path) -> None:
    """Behaviour is preserved after the dedup refactor."""
    from vectorcode.src.vc_tools.memory_manage import MemoryManageTool

    tool = MemoryManageTool(tmp_path / "MEMORY.md")
    assert tool.spec.name == "memory_manage"
    assert tool.spec.category == "memory"
    assert tool.execute(action="add", entry="likes coffee").success
    assert "likes coffee" in tool.execute(action="read").content
    assert tool.execute(action="update", entry="likes coffee", new_entry="likes tea").success
    assert "likes tea" in tool.execute(action="read").content
    # Guards preserved
    assert not tool.execute(action="add", entry="").success
    assert not tool.execute(action="remove", entry="missing").success


def test_mcp_server_no_longer_monolith() -> None:
    """Issue 24: the 3.1k-line _add_expansion_tools was lifted out of
    core/mcp_server.py into core/mcp_tools/expansion.py."""
    from pathlib import Path as _P

    server_src = _P("core/mcp_server.py").read_text(encoding="utf-8")
    # The giant function body must no longer live in the server module.
    assert "def _add_expansion_tools(mcp)" not in server_src
    # It is imported from the focused module instead.
    assert "from core.mcp_tools.expansion import add_expansion_tools" in server_src
    assert _P("core/mcp_tools/expansion.py").exists()
    # Server module is back to a reasonable size.
    assert server_src.count("\n") < 1600, "mcp_server.py is still a monolith"


def test_mcp_tool_inventory_unchanged_after_split() -> None:
    """The split must not add, drop, or rename a single registered MCP tool."""
    import asyncio
    import hashlib
    import core.mcp_server as m

    srv = m._make_server()
    names = sorted(t.name for t in asyncio.run(srv.list_tools()))
    assert len(names) == 353, f"tool count changed: {len(names)}"
    sha = hashlib.sha256("\n".join(names).encode()).hexdigest()[:16]
    assert sha == "3824d04807007a5b", f"tool name set changed: {sha}"
