"""Regression proofs for the 2026-10-06 misc-root audit."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ORCHESTRATOR_DIR = Path(__file__).resolve().parents[1] / "tools" / "vector_dev_orchestrator"
if str(ORCHESTRATOR_DIR) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_DIR))


def test_state_store_rejects_task_id_path_escape(tmp_path):
    from state_store import StateStore

    store = StateStore(tmp_path / "state")
    with pytest.raises(ValueError, match="task_id"):
        store.load("../../outside")


def test_supervisor_rejects_program_id_path_escape(tmp_path):
    from supervisor import Supervisor

    supervisor = Supervisor.__new__(Supervisor)
    supervisor.dir = tmp_path / "programs"
    supervisor.dir.mkdir()

    with pytest.raises(ValueError, match="program_id"):
        supervisor.load("../outside")


def test_worktree_add_terminates_options_before_caller_ref(tmp_path, monkeypatch):
    from worktree_manager import WorktreeManager

    manager = WorktreeManager.__new__(WorktreeManager)
    manager.worktree_root = tmp_path / "worktrees"
    monkeypatch.setattr(manager, "_branch_exists", lambda _name: False)
    seen = []
    monkeypatch.setattr(manager, "_run", lambda args: seen.append(args) or SimpleNamespace(stdout=""))

    manager.create("task", base_ref="--help")

    assert seen[0][4] == "--"
    assert seen[0][-1] == "--help"


def test_quota_write_fsyncs_before_replace(tmp_path, monkeypatch):
    import quota

    calls = []
    monkeypatch.setattr(quota.os, "fsync", lambda fd: calls.append(fd))
    quota.QuotaBoard(tmp_path / "quota.json")._write({"value": 1})
    assert calls


def test_worker_counter_corruption_fails_closed(tmp_path):
    from autonomous_worker import AutonomousWorker

    worker = AutonomousWorker.__new__(AutonomousWorker)
    worker.counter_path = tmp_path / "worker_state.json"
    worker.today_fn = lambda: "2026-10-06"
    worker.counter_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(RuntimeError, match="counter state is corrupt"):
        worker._count_today()


def test_worker_explicit_zero_max_tasks_is_not_replaced_by_default(tmp_path, monkeypatch):
    from autonomous_worker import AutonomousWorker, WorkerConfig

    worker = AutonomousWorker.__new__(AutonomousWorker)
    worker.config = WorkerConfig(refresh_quota_telemetry=False)
    worker.stop_path = tmp_path / "STOP"
    worker.lock_path = tmp_path / "lock"
    worker.backlog = SimpleNamespace(recover_interrupted=lambda: [])
    monkeypatch.setattr(worker, "_acquire_lock", lambda: True)
    monkeypatch.setattr(worker, "_release_lock", lambda: None)
    monkeypatch.setattr(worker, "reactivate_deferred", lambda: None)
    monkeypatch.setattr(worker, "resume_reviews", lambda: [])
    monkeypatch.setattr(
        worker.backlog,
        "next_pending",
        lambda **kwargs: pytest.fail("zero task limit must not inspect pending work"),
        raising=False,
    )

    summary = worker.run(max_tasks=0)
    assert summary.processed == []
    assert summary.stopped_because == "max tasks per run"


def test_adb_port_forward_reports_nonzero_exit_as_failure(monkeypatch):
    from phone_node import adb_bridge

    monkeypatch.setattr(
        adb_bridge.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )
    assert adb_bridge.setup_port_forward() is False


def test_adb_screenshot_does_not_report_missing_pull_as_success(tmp_path, monkeypatch):
    from phone_node import adb_bridge

    monkeypatch.setattr(adb_bridge, "_adb", lambda *args: "")
    assert adb_bridge.take_screenshot(tmp_path / "missing.png") is None


def test_phone_auth_uses_constant_time_comparison(monkeypatch):
    from phone_node import ambient_server

    seen = []
    monkeypatch.setattr(ambient_server, "API_KEY", "secret")
    monkeypatch.setattr(
        ambient_server.hmac,
        "compare_digest",
        lambda left, right: seen.append((left, right)) or True,
    )

    assert ambient_server._auth_ok("Bearer supplied") is True
    assert seen == [("Bearer supplied", "Bearer secret")]


async def test_comms_bridge_does_not_turn_falsy_delivery_into_success(monkeypatch):
    from cloud.comms_service import service

    class Bridge:
        def send_message(self, platform, to, message):
            return False

    monkeypatch.setattr(service, "_vc_bridge", Bridge())
    result = await service.send_message(
        {"platform": "unsupported", "to": "recipient", "message": "hello"},
        True,
    )
    assert result["ok"] is False
