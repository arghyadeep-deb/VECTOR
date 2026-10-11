"""Regression tests for launcher smoke storage isolation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_smoke_mode_sets_main_db_under_the_smoke_data_root(monkeypatch):
    import run_vector

    captured = {}

    async def fake_smoke_test():
        captured["db"] = run_vector.os.environ.get("VECTOR_DB_PATH")
        captured["data"] = run_vector.os.environ.get("VECTOR_TEST_DATA_DIR")
        return {"status": "ok"}

    monkeypatch.setattr(run_vector, "parse_args", lambda: SimpleNamespace(mode="smoke"))
    monkeypatch.setattr(run_vector, "smoke_test", fake_smoke_test)
    monkeypatch.delenv("VECTOR_DB_PATH", raising=False)
    monkeypatch.delenv("VECTOR_TEST_DATA_DIR", raising=False)

    assert run_vector.main() == 0

    assert captured["data"]
    assert captured["db"]
    assert captured["db"].startswith(captured["data"])
    assert captured["db"].endswith("vector_memory.db")


def test_smoke_mode_uses_a_fresh_data_root_each_run(monkeypatch):
    import run_vector

    roots: list[str] = []

    async def fake_smoke_test():
        roots.append(run_vector.os.environ["VECTOR_TEST_DATA_DIR"])
        return {"status": "ok"}

    monkeypatch.setattr(run_vector, "parse_args", lambda: SimpleNamespace(mode="smoke"))
    monkeypatch.setattr(run_vector, "smoke_test", fake_smoke_test)
    monkeypatch.delenv("VECTOR_DB_PATH", raising=False)
    monkeypatch.delenv("VECTOR_TEST_DATA_DIR", raising=False)

    assert run_vector.main() == 0
    monkeypatch.delenv("VECTOR_DB_PATH", raising=False)
    monkeypatch.delenv("VECTOR_TEST_DATA_DIR", raising=False)
    assert run_vector.main() == 0

    assert len(roots) == 2
    assert roots[0] != roots[1]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
