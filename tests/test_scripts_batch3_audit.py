"""Regression tests for the first audit of root scripts/ batch 3."""
from __future__ import annotations

import importlib.util
import sqlite3
import subprocess
import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"audit_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_keyring_migrator_uses_path_repo_root():
    module = _load("migrate_secrets_to_keyring")
    assert isinstance(module._repo_root, Path)


def test_sqlcipher_migration_is_complete_and_refuses_overwrite(tmp_path):
    module = _load("migrate_to_encrypted")
    source = tmp_path / "plain.db"
    destination = tmp_path / "encrypted.db"
    with sqlite3.connect(source) as conn:
        conn.executescript(
            "CREATE TABLE items(id INTEGER PRIMARY KEY, value TEXT);"
            "CREATE INDEX items_value ON items(value);"
            "CREATE TRIGGER items_trim AFTER INSERT ON items "
            "BEGIN UPDATE items SET value=trim(value) WHERE id=NEW.id; END;"
            "INSERT INTO items(value) VALUES (' x ');"
        )
    fake_sqlcipher = SimpleNamespace(connect=sqlite3.connect)
    module.migrate(source, destination, "key'with-quote", fake_sqlcipher)
    with sqlite3.connect(destination) as conn:
        assert conn.execute("SELECT value FROM items").fetchone() == ("x",)
        objects = dict(conn.execute(
            "SELECT name, type FROM sqlite_master WHERE name IN ('items_value','items_trim')"
        ))
    assert objects == {"items_value": "index", "items_trim": "trigger"}
    try:
        module.migrate(source, destination, "another", fake_sqlcipher)
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing encrypted destination must not be overwritten")


def test_precommit_gate_blocks_when_git_diff_fails(monkeypatch, capsys):
    module = _load("precommit_syntax_gate")

    def fail(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 128, stdout="", stderr="fatal: unavailable")

    monkeypatch.setattr(module.subprocess, "run", fail)
    assert module.main() == 1
    assert "COMMIT BLOCKED" in capsys.readouterr().err


def test_precommit_gate_blocks_when_staged_blob_cannot_be_read(monkeypatch):
    module = _load("precommit_syntax_gate")
    monkeypatch.setattr(module, "staged_files", lambda: ["broken.py"])
    monkeypatch.setattr(module, "staged_content", lambda _path: (_ for _ in ()).throw(RuntimeError("missing blob")))
    assert module.main() == 1


def test_wake_window_stream_includes_exact_and_final_windows():
    module = _load("train_wake_head")
    import numpy as np

    exact = np.zeros((16, 96), dtype=np.float32)
    assert module.window_stream(exact).shape == (1, 16, 96)
    longer = np.zeros((24, 96), dtype=np.float32)
    assert module.window_stream(longer, win=16, hop=8).shape == (2, 16, 96)


def test_wake_trainers_never_replace_live_model_with_rejected_candidate(tmp_path):
    for script in ("train_wake_head", "train_wake_v2"):
        module = _load(script)
        live = tmp_path / f"{script}.onnx"
        candidate = tmp_path / f"{script}.candidate.onnx"
        live.write_bytes(b"known-good")
        candidate.write_bytes(b"bad-model")
        assert module._promote_candidate(candidate, live, False) is False
        assert live.read_bytes() == b"known-good"
        assert not candidate.exists()


def test_link_skills_include_deprecated_flag_is_honored(tmp_path, monkeypatch):
    module = _load("link_skills")
    repo = tmp_path / "source"
    deprecated = repo / "skills" / "deprecated" / "old_skill"
    deprecated.mkdir(parents=True)
    (deprecated / "SKILL.md").write_text("description: old\n", encoding="utf-8")
    monkeypatch.setattr(module, "DEST", tmp_path / "installed")
    module.link_skills(repo, include_deprecated=True)
    assert (module.DEST / "old_skill" / "SKILL.md").is_file()


def test_smoke_test_isolates_database_before_importing_core():
    source = (ROOT / "scripts" / "smoke_test.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    env_line = next(
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Subscript) for target in node.targets)
        and "VECTOR_DB_PATH" in ast.get_source_segment(source, node)
    )
    core_import_line = next(
        node.lineno for node in tree.body
        if isinstance(node, ast.Import) and any(alias.name == "core.config" for alias in node.names)
    )
    assert env_line < core_import_line


if __name__ == "__main__":
    raise SystemExit(0)
