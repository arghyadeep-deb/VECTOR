"""Integration tests for the VECTOR collections engine (PocketBase absorption).

Real round-trips against an isolated temp SQLite DB — no mocks of internal state,
and never touches the production vector_memory.db. Covers the data layer, the safe
filter parser, and (in later phases) migrations, storage, auth/RBAC and hooks.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.collections import (
    Collection,
    CollectionEngine,
    FilterError,
    ValidationError,
    parse_filter,
)


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA journal_mode=WAL")
    yield c
    c.close()


@pytest.fixture()
def engine(conn):
    return CollectionEngine(conn)


@pytest.fixture()
def notes(engine):
    return engine.create_collection(Collection(
        name="notes",
        fields=[
            {"name": "title", "type": "text", "required": True},
            {"name": "views", "type": "number", "options": {"only_int": True}},
            {"name": "pinned", "type": "bool"},
            {"name": "tags", "type": "select",
             "options": {"values": ["a", "b", "c"], "max_select": 3}},
        ],
    ))


# ── data layer ─────────────────────────────────────────────────────────────
def test_create_and_get_roundtrip(engine, notes):
    rec = engine.create_record("notes", {"title": "hello", "views": 5,
                                          "pinned": True, "tags": ["a", "b"]})
    assert rec["title"] == "hello"
    assert rec["pinned"] is True
    assert rec["tags"] == ["a", "b"]
    assert len(rec["id"]) == 15
    fetched = engine.get_record("notes", rec["id"])
    assert fetched == rec


def test_required_field_enforced(engine, notes):
    with pytest.raises(ValidationError):
        engine.create_record("notes", {"views": 1})


def test_update_is_partial(engine, notes):
    rec = engine.create_record("notes", {"title": "x", "views": 1})
    updated = engine.update_record("notes", rec["id"], {"views": 99})
    assert updated["views"] == 99
    assert updated["title"] == "x"            # untouched
    assert updated["updated"] >= rec["created"]


def test_delete(engine, notes):
    rec = engine.create_record("notes", {"title": "x"})
    assert engine.delete_record("notes", rec["id"]) is True
    assert engine.get_record("notes", rec["id"]) is None
    assert engine.delete_record("notes", rec["id"]) is False


def test_list_filter_sort_paginate(engine, notes):
    for i in range(10):
        engine.create_record("notes", {"title": f"n{i}", "views": i, "pinned": i % 2 == 0})
    res = engine.list_records("notes", filter="views >= 5", sort="-views", per_page=3, page=1)
    assert res["total_items"] == 5
    assert res["total_pages"] == 2
    assert [r["views"] for r in res["items"]] == [9, 8, 7]


def test_filter_like_operator(engine, notes):
    engine.create_record("notes", {"title": "hello world"})
    engine.create_record("notes", {"title": "goodbye"})
    res = engine.list_records("notes", filter='title ~ "world"')
    assert res["total_items"] == 1
    assert res["items"][0]["title"] == "hello world"


def test_boolean_filter(engine, notes):
    engine.create_record("notes", {"title": "a", "pinned": True})
    engine.create_record("notes", {"title": "b", "pinned": False})
    assert engine.list_records("notes", filter="pinned = true")["total_items"] == 1
    assert engine.list_records("notes", filter="pinned = false")["total_items"] == 1


# ── security: the filter parser must never execute injected SQL ──────────────
def test_filter_rejects_sql_injection(engine, notes):
    engine.create_record("notes", {"title": "keep"})
    with pytest.raises(FilterError):
        engine.list_records("notes", filter='title = "x"; DROP TABLE col_notes;--')
    # table intact
    assert engine.list_records("notes")["total_items"] == 1


def test_filter_rejects_unknown_field(engine, notes):
    with pytest.raises(FilterError):
        engine.list_records("notes", filter='secret = "x"')


def test_sort_rejects_unknown_field(engine, notes):
    with pytest.raises(FilterError):
        engine.list_records("notes", sort="evil")


def test_filter_values_are_bound_parameters():
    where, params = parse_filter('title = "o\'brien" && views > 3', {"title", "views"})
    assert "?" in where
    assert params == ["o'brien", 3]
    assert "o'brien" not in where          # value never inlined into SQL


def test_quoted_identifiers_only():
    where, _ = parse_filter("views >= 5", {"views"})
    assert where == '"views" >= ?'


# ── registry ─────────────────────────────────────────────────────────────────
def test_collection_registry_roundtrip(engine, notes):
    assert [c.name for c in engine.list_collections()] == ["notes"]
    again = engine.get_collection("notes")
    assert again.field_names() == ["title", "views", "pinned", "tags"]


def test_duplicate_collection_rejected(engine, notes):
    with pytest.raises(ValidationError):
        engine.create_collection(Collection(name="notes", fields=[{"name": "x", "type": "text"}]))


def test_reserved_name_rejected(engine):
    with pytest.raises(ValidationError):
        Collection(name="episodic_memory", fields=[{"name": "x", "type": "text"}])


def test_auth_collection_has_identity_fields(engine):
    coll = engine.create_collection(Collection(
        name="users", type="auth", fields=[{"name": "displayName", "type": "text"}]))
    assert "email" in coll.field_names()
    assert "password" in coll.field_names()
    rec = engine.create_record("users", {"email": "a@b.com", "password": "longenough123",
                                         "displayName": "A"})
    assert "password" not in rec            # password never returned


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
