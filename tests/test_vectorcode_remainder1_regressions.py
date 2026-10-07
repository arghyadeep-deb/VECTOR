"""Regression tests for the first unaudited vectorcode/src remainder batch."""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_mount_policy_blocks_nested_sensitive_paths_and_canonicalizes(tmp_path: Path) -> None:
    from core.sandbox.mount_security import AllowedRoot, MountAllowlist, validate_mounts

    root = tmp_path / "allowed"
    safe = root / "project"
    sensitive = safe / ".git" / "config"
    sensitive.parent.mkdir(parents=True)
    sensitive.write_text("credential", encoding="utf-8")

    policy = MountAllowlist(roots=[AllowedRoot(str(root))])
    with pytest.raises(ValueError, match="blocked"):
        validate_mounts([str(sensitive)], policy)

    safe.mkdir(exist_ok=True)
    assert validate_mounts([str(safe)], policy) == [str(safe.resolve())]


def test_empty_mount_allowlist_denies_mounts(tmp_path: Path) -> None:
    from core.sandbox.mount_security import MountAllowlist, validate_mounts

    candidate = tmp_path / "ordinary"
    candidate.mkdir()
    with pytest.raises(ValueError, match="allowed root"):
        validate_mounts([str(candidate)], MountAllowlist())


def test_container_output_without_protocol_markers_is_an_error() -> None:
    from core.sandbox.runner import ContainerRunner

    result = ContainerRunner._parse_output("ordinary stdout")
    assert result["error"] is True
    assert result["error_type"] == "protocol"


def test_mini_swe_defaults_to_isolated_environment() -> None:
    from vectorcode.src.mini_swe_runner import MiniSWERunner, create_environment, main

    assert inspect.signature(create_environment).parameters["env_type"].default == "docker"
    assert inspect.signature(MiniSWERunner).parameters["env_type"].default == "docker"
    assert inspect.signature(main).parameters["env"].default == "docker"


def test_unwired_approval_response_fails_closed() -> None:
    from vectorcode.src.mcp_serve import EventBridge

    bridge = EventBridge()
    bridge._pending_approvals["approval-1"] = {"approval_id": "approval-1"}
    result = bridge.respond_to_approval("approval-1", "allow-once")
    assert result.get("resolved") is not True
    assert result["error_type"] == "approval_gateway_unavailable"
    assert "approval-1" in bridge._pending_approvals


def test_closed_session_singleton_is_recreated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import vectorcode.src.session_db as session_db

    first = session_db.SessionDB(tmp_path / "one.db")
    monkeypatch.setattr(session_db, "_db", first)
    first.close()
    monkeypatch.setattr(session_db, "_DEFAULT_DB_PATH", tmp_path / "two.db")
    second = session_db.get_session_db()
    try:
        assert second is not first
        second.create_session("s", "m", "p", "mode")
    finally:
        second.close()


def test_credential_json_write_flushes_before_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import vectorcode.src.credential_sources as credential_sources

    calls: list[int] = []
    monkeypatch.setattr(credential_sources.os, "fsync", calls.append)
    target = tmp_path / "credentials.json"
    credential_sources.atomic_json_write(target, {"token": "value"})
    assert calls
    assert json.loads(target.read_text(encoding="utf-8")) == {"token": "value"}


def test_moe_save_uses_atomic_writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import vectorcode.src.neural_moe_router as moe

    written: dict[str, object] = {}

    def fake_atomic(path: Path, data: object, **kwargs: object) -> None:
        written["path"] = path
        written["data"] = data

    monkeypatch.setattr(moe, "atomic_json_write", fake_atomic, raising=False)
    router = moe.MoERouter(moe.MoERouterConfig(num_experts=2, input_dim=4, hidden_dim=3, top_k=1))
    destination = tmp_path / "weights.json"
    router.save(destination)
    assert written["path"] == destination
    assert isinstance(written["data"], dict)


def test_logging_explicit_zero_is_not_replaced_by_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import vectorcode.src.vector_logging as vector_logging

    captured: list[tuple[int, int]] = []
    monkeypatch.setattr(vector_logging, "_read_logging_config", lambda: ("INFO", 9, 7))
    monkeypatch.setattr(
        vector_logging,
        "_add_rotating_handler",
        lambda *args, **kwargs: captured.append((kwargs["max_bytes"], kwargs["backup_count"])),
    )
    monkeypatch.setattr(vector_logging, "_logging_initialized", False)
    vector_logging.setup_logging(
        vector_home=tmp_path,
        max_size_mb=0,
        backup_count=0,
        force=True,
    )
    assert captured
    assert captured[0] == (0, 0)


def test_wasm_runner_requires_an_executed_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.sandbox.wasm_runner import WasmRunner

    class Config:
        consume_fuel = False

    class Engine:
        def __init__(self, config: object) -> None:
            pass

    class Store:
        def __init__(self, engine: object) -> None:
            self.fuel = 0

        def set_fuel(self, fuel: int) -> None:
            self.fuel = fuel

        def get_fuel(self) -> int:
            return self.fuel

        def set_wasi(self, config: object) -> None:
            pass

    class Module:
        def __init__(self, engine: object, payload: bytes) -> None:
            pass

    class WasiConfig:
        def inherit_stdout(self) -> None:
            pass

        def inherit_stderr(self) -> None:
            pass

    class Instance:
        def exports(self, store: object) -> dict[str, object]:
            return {}

    class Linker:
        def __init__(self, engine: object) -> None:
            pass

        def define_wasi(self) -> None:
            pass

        def instantiate(self, store: object, module: object) -> Instance:
            return Instance()

    fake = SimpleNamespace(
        Config=Config,
        Engine=Engine,
        Store=Store,
        Module=Module,
        WasiConfig=WasiConfig,
        Linker=Linker,
        Func=type("Func", (), {}),
    )
    monkeypatch.setitem(sys.modules, "wasmtime", fake)
    result = WasmRunner().run(b"valid-enough-for-fake")
    assert result.success is False
    assert "entry point" in result.output
