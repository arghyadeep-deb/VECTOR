from __future__ import annotations

import sqlite3
from pathlib import Path


def test_backup_prunes_timestamped_snapshot(tmp_path: Path) -> None:
    from scripts.backup_dbs import prune_old_backups

    old = tmp_path / "2020-01-01T00-00-00"
    old.mkdir()
    assert prune_old_backups(tmp_path, keep_days=30) == 1
    assert not old.exists()


def test_backup_failure_preserves_existing_snapshot(tmp_path: Path, monkeypatch) -> None:
    from scripts import backup_dbs

    src = tmp_path / "source.db"
    with sqlite3.connect(src) as conn:
        conn.execute("CREATE TABLE sample(value TEXT)")
    dest_dir = tmp_path / "snapshot"
    dest_dir.mkdir()
    dest = dest_dir / src.name
    dest.write_bytes(b"previous-good-backup")
    real_connect = backup_dbs.sqlite3.connect

    def failing_connect(path: str):
        if Path(path).name.startswith(f".{src.name}."):
            raise sqlite3.OperationalError("simulated interrupted backup")
        return real_connect(path)

    monkeypatch.setattr(backup_dbs.sqlite3, "connect", failing_connect)
    assert backup_dbs.backup_db(src, dest_dir) is False
    assert dest.read_bytes() == b"previous-good-backup"
    assert not list(dest_dir.glob(f".{src.name}.*.tmp"))


def test_backup_round_trip_with_verification(tmp_path: Path) -> None:
    from scripts.backup_dbs import backup_db

    src = tmp_path / "source.db"
    with sqlite3.connect(src) as conn:
        conn.execute("CREATE TABLE sample(value TEXT)")
        conn.execute("INSERT INTO sample VALUES ('kept')")

    dest_dir = tmp_path / "snapshot"
    assert backup_db(src, dest_dir, verify=True)
    with sqlite3.connect(dest_dir / src.name) as conn:
        assert conn.execute("SELECT value FROM sample").fetchone() == ("kept",)


def test_capability_smoke_fails_when_reachability_fails(tmp_path: Path, monkeypatch) -> None:
    from scripts import capability_smoke

    monkeypatch.setattr(capability_smoke, "PROOFS_DIR", tmp_path)
    monkeypatch.setattr(
        capability_smoke,
        "check_reachability",
        lambda: {"example": [{"module": "broken", "status": "IMPORT_ERROR", "error": "boom"}]},
    )
    monkeypatch.setattr("sys.argv", ["capability_smoke.py", "--reachability"])
    assert capability_smoke.main() == 1


def test_soak_verdict_is_nonzero_without_evidence() -> None:
    from scripts.check_soak import verdict_exit_code

    assert verdict_exit_code(hands_ok=False, cron_ok=False) == 1
    assert verdict_exit_code(hands_ok=True, cron_ok=True) == 0


def test_exception_audit_does_not_call_unlogged_handlers_logged(tmp_path: Path) -> None:
    from scripts.audit_exceptions import classify_file

    sample = tmp_path / "sample.py"
    sample.write_text(
        "def handled():\n"
        "    try:\n"
        "        risky()\n"
        "    except ValueError:\n"
        "        return None\n\n"
        "def reraised():\n"
        "    try:\n"
        "        risky()\n"
        "    except RuntimeError:\n"
        "        raise\n",
        encoding="utf-8",
    )

    categories = [item["category"] for item in classify_file(sample)]
    assert categories == ["UNLOGGED_REAL", "RE_RAISED"]


def test_dependency_graph_resolves_from_imported_submodule(tmp_path: Path, monkeypatch) -> None:
    from scripts import _build_dep_graph as dep_graph

    package = tmp_path / "core"
    package.mkdir()
    init = package / "__init__.py"
    consumer = package / "consumer.py"
    helper = package / "helper.py"
    init.write_text("from . import helper\n", encoding="utf-8")
    consumer.write_text("from core import helper\n", encoding="utf-8")
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(dep_graph, "BASE", tmp_path)

    outgoing, _ = dep_graph.build_graph([init, consumer, helper])

    assert outgoing["core"] == {"core.helper"}
    assert outgoing["core.consumer"] == {"core.helper"}
