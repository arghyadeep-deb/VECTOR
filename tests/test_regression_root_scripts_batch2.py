"""Regression tests for the 2026-10-06 root scripts batch-2 audit."""
from __future__ import annotations

import ast
import importlib.util
import sqlite3
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"audit_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_function_without_module_side_effects(script: str, function: str, namespace=None):
    source = (ROOT / "scripts" / script).read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == function
    )
    isolated = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(isolated)
    scope = dict(namespace or {})
    exec(compile(isolated, script, "exec"), scope)
    return scope[function]


def test_integration_check_treats_false_predicate_as_failure():
    results = []
    check = _load_function_without_module_side_effects(
        "integration_check.py", "check", {"results": results},
    )

    check("false predicate", lambda: False)

    assert results == [(False, "false predicate", "predicate returned False")]


def test_full_integration_audit_exit_code_fails_when_any_check_failed():
    exit_code = _load_function_without_module_side_effects(
        "full_integration_audit.py", "_audit_exit_code"
    )

    assert exit_code(0) == 0
    assert exit_code(1) == 1


@pytest.mark.parametrize("script_name,function_name", [
    ("fix_pass_stubs.py", "_fix_file"),
    ("fix_finagent_base_stubs.py", "fix_file"),
])
def test_stub_rewriters_only_raise_for_explicit_abstract_methods(
    tmp_path, script_name, function_name
):
    module = _load_script(script_name)
    module.REPO_ROOT = tmp_path
    target = tmp_path / "base_example.py"
    target.write_text(
        "from abc import abstractmethod\n\n"
        "class BaseExample:\n"
        "    def optional_hook(self):\n"
        "        pass\n\n"
        "    @abstractmethod\n"
        "    def required_hook(self):\n"
        "        pass\n",
        encoding="utf-8",
    )

    changed = getattr(module, function_name)(target, dry_run=False)
    rewritten = target.read_text(encoding="utf-8")

    assert changed == 1
    assert "def optional_hook(self):\n        pass" in rewritten
    assert "BaseExample.required_hook must be implemented by subclass" in rewritten


def test_db_backup_preserves_existing_destination_when_raw_copy_fails(tmp_path, monkeypatch):
    module = _load_script("db_backup.py")
    source = tmp_path / "source.db"
    destination = tmp_path / "backup" / "source.db"
    source.write_bytes(b"not sqlite")
    destination.parent.mkdir()
    destination.write_bytes(b"known-good-backup")

    def partial_copy_then_fail(src, dst):
        Path(dst).write_bytes(b"partial")
        raise OSError("simulated interrupted copy")

    monkeypatch.setattr(module.shutil, "copy2", partial_copy_then_fail)
    with pytest.raises(OSError, match="interrupted copy"):
        module._sqlite_backup(source, destination)

    assert destination.read_bytes() == b"known-good-backup"


def test_db_backup_closes_connections_before_raw_copy_fallback(tmp_path, monkeypatch):
    module = _load_script("db_backup.py")
    source = tmp_path / "source.db"
    destination = tmp_path / "backup.db"
    source.write_bytes(b"not sqlite")
    connections = []

    class FakeConnection:
        def __init__(self):
            self.closed = False

        def backup(self, _other):
            raise sqlite3.DatabaseError("not a database")

        def close(self):
            self.closed = True

    def connect(_path):
        conn = FakeConnection()
        connections.append(conn)
        return conn

    monkeypatch.setattr(module.sqlite3, "connect", connect)
    monkeypatch.setattr(module, "_atomic_copy", lambda src, dst: None)
    module._sqlite_backup(source, destination)

    assert len(connections) == 2
    assert all(conn.closed for conn in connections)


def test_db_backup_preserves_relative_directories_to_avoid_name_collisions(tmp_path):
    module = _load_script("db_backup.py")
    module._BASE_DIR = tmp_path
    module.BACKUP_DIR = tmp_path / "backups"

    first = module._backup_path(tmp_path / "a__b" / "c.db", "stamp")
    second = module._backup_path(tmp_path / "a" / "b__c.db", "stamp")

    assert first != second
    assert first == module.BACKUP_DIR / "stamp" / "a__b" / "c.db"
    assert second == module.BACKUP_DIR / "stamp" / "a" / "b__c.db"


def test_diag_tier6_result_is_failure_when_any_query_is_empty_or_errors():
    module = _load_script("diag_tier6.py")

    assert module._diagnostic_exit_code(["OK", "OK"]) == 0
    assert module._diagnostic_exit_code(["OK", "EMPTY"]) == 1
    assert module._diagnostic_exit_code(["ERROR"]) == 1


def test_enrollment_requires_confirmation_before_overwriting_voiceprint(tmp_path):
    module = _load_script("enroll_owner_voice.py")
    voiceprint = tmp_path / "owner_voiceprint.npz"
    voiceprint.write_bytes(b"existing biometric")

    assert not module._confirm_overwrite(voiceprint, force=False, input_fn=lambda _: "no")
    assert module._confirm_overwrite(voiceprint, force=False, input_fn=lambda _: "yes")
    assert module._confirm_overwrite(voiceprint, force=True, input_fn=lambda _: "no")


def test_deepeval_smoke_requires_good_case_pass_and_bad_case_fail():
    module = _load_script("deepeval_smoke_test.py")

    assert module._smoke_succeeded(good_success=True, bad_success=False)
    assert not module._smoke_succeeded(good_success=False, bad_success=False)
    assert not module._smoke_succeeded(good_success=True, bad_success=True)


def test_find_agents_root_is_derived_from_script_location():
    source = (ROOT / "scripts" / "find_agents_needing_capabilities.py").read_text(
        encoding="utf-8"
    )

    assert 'Path(r"C:\\Users\\' not in source
    assert "Path(__file__).resolve().parent.parent" in source


def test_full_integration_audit_does_not_hardcode_telemetry_pass():
    source = (ROOT / "scripts" / "full_integration_audit.py").read_text(encoding="utf-8")

    assert 'check("Telemetry is intentionally no-op", True' not in source
    assert 'check("Telemetry is intentionally no-op", is_noop' in source


def test_generated_routers_log_with_loguru_and_hide_internal_errors():
    module = _load_script("create_routers.py")
    generated = module.build_router(
        "example.py", "/example", "example", [module.ep("/run", "get", "run", "Run.")]
    )

    assert 'logger.error("[VECTOR][example] run failed: {}", e)' in generated
    assert 'detail="internal server error"' in generated
    assert "detail=str(e)" not in generated


def test_gemini_judge_sends_api_key_in_header_not_url(monkeypatch):
    module = _load_script("langsmith_vector_eval.py")
    module.GEMINI_API_KEY = "secret-key"
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"score": 1, "reasoning": "ok"}'}]}}]}

    class Client:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return Response()

    monkeypatch.setattr(module.httpx, "Client", Client)
    assert module._judge_via_gemini("prompt")["score"] == 1.0
    assert "params" not in captured
    assert captured["headers"] == {"x-goog-api-key": "secret-key"}


def test_convert_dataset_rejects_empty_input_without_overwriting_output(tmp_path, monkeypatch):
    module = _load_script("convert_to_district_only.py")
    data = tmp_path / "data"
    data.mkdir()
    (data / "golden_intent_dataset.jsonl").write_text("", encoding="utf-8")
    output = data / "golden_intent_dataset_district_only.jsonl"
    output.write_text("existing", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert module.convert_dataset() is False
    assert output.read_text(encoding="utf-8") == "existing"
