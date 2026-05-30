"""Integration tests for the VECTOR collections engine (PocketBase absorption).

Real round-trips against an isolated temp SQLite DB — no mocks of internal state,
and never touches the production vector_memory.db. Covers the data layer, the safe
filter parser, and (in later phases) migrations, storage, auth/RBAC and hooks.
"""

import sqlite3
import sys

import pytest


from core.collections import (
    Collection,
    CollectionEngine,
    FilterError,
    ValidationError,
    parse_filter,
)


@pytest.fixture()
def conn():
    # check_same_thread=False mirrors VECTOR's get_db_connection and lets the FastAPI
    # TestClient (which runs endpoints in a threadpool) share this connection.
    c = sqlite3.connect(":memory:", check_same_thread=False)
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


# ── migrations ─────────────────────────────────────────────────────────────
def _make_runner(conn):
    from core.collections.migrations import MigrationRunner, Migration, add_column_if_missing
    reg = {}
    r = MigrationRunner(conn, registry=reg)
    r.register(Migration(
        id="0001_create",
        up=lambda c: c.execute("CREATE TABLE widgets (id TEXT PRIMARY KEY)"),
        down=lambda c: c.execute("DROP TABLE widgets"),
    ))
    r.register(Migration(
        id="0002_add_color",
        up=lambda c: add_column_if_missing(c, "widgets", "color", "TEXT"),
        down=lambda c: None,
    ))
    return r


def test_migration_apply_pending(conn):
    from core.collections.migrations import table_exists, column_exists
    r = _make_runner(conn)
    applied = r.apply_pending()
    assert applied == ["0001_create", "0002_add_color"]
    assert table_exists(conn, "widgets")
    assert column_exists(conn, "widgets", "color")
    assert r.apply_pending() == []          # idempotent


def test_migration_revert_and_reapply(conn):
    r = _make_runner(conn)
    r.apply_pending()
    assert r.revert(steps=1) == ["0002_add_color"]
    assert "0002_add_color" not in r.applied_ids()
    assert r.apply_pending() == ["0002_add_color"]


def test_migration_full_revert_drops_table(conn):
    from core.collections.migrations import table_exists
    r = _make_runner(conn)
    r.apply_pending()
    r.revert(steps=2)
    assert not table_exists(conn, "widgets")


def test_add_column_if_missing_idempotent(conn):
    from core.collections.migrations import add_column_if_missing
    conn.execute("CREATE TABLE t (id TEXT)")
    assert add_column_if_missing(conn, "t", "extra", "INTEGER") is True
    assert add_column_if_missing(conn, "t", "extra", "INTEGER") is False


# ── file storage ─────────────────────────────────────────────────────────────
@pytest.fixture()
def storage(tmp_path):
    from core.collections.storage import FileStorage, LocalDriver
    return FileStorage(LocalDriver(str(tmp_path / "files")))


def test_storage_put_get_delete(storage):
    meta = storage.put("docs/a.txt", b"hello", content_type="text/plain")
    assert meta["size"] == 5
    assert storage.get("docs/a.txt") == b"hello"
    assert storage.exists("docs/a.txt")
    assert "docs/a.txt" in storage.list()
    assert storage.delete("docs/a.txt") is True
    assert not storage.exists("docs/a.txt")


@pytest.mark.parametrize("bad", ["../escape", "/etc/passwd", "C:/windows", "a/../../b"])
def test_storage_rejects_unsafe_keys(bad):
    from core.collections.storage import safe_key, StorageError
    with pytest.raises(StorageError):
        safe_key(bad)


def test_storage_normalizes_key():
    from core.collections.storage import safe_key
    assert safe_key("a//b/./c") == "a/b/c"


def test_storage_thumbnail():
    import io
    PIL = pytest.importorskip("PIL")
    from PIL import Image
    import tempfile
    from core.collections.storage import FileStorage, LocalDriver
    fs = FileStorage(LocalDriver(tempfile.mkdtemp()))
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), (0, 128, 255)).save(buf, format="PNG")
    fs.put("p.png", buf.getvalue(), content_type="image/png")
    thumb = fs.thumbnail("p.png", 50, 50)
    w, h = Image.open(io.BytesIO(thumb)).size
    assert w <= 50 and h <= 50


# ── auth + RBAC ──────────────────────────────────────────────────────────────
_SECRET = "x" * 40   # >=32 bytes to satisfy PyJWT HS256


def test_password_hash_roundtrip():
    from core.collections.auth import PasswordHasher
    h = PasswordHasher.hash("hunter2pass")
    assert h != "hunter2pass"
    assert PasswordHasher.verify("hunter2pass", h)
    assert not PasswordHasher.verify("wrong", h)


def test_jwt_issue_verify_refresh():
    from core.collections.auth import JWTManager
    jm = JWTManager(secret=_SECRET, access_ttl=3600)
    pair = jm.issue_pair("rec1", "users", extra={"email": "a@b.com"})
    claims = jm.verify(pair["token"], expected_type="access")
    assert claims["sub"] == "rec1" and claims["email"] == "a@b.com"
    new = jm.refresh(pair["refresh_token"])
    assert jm.verify(new["token"], expected_type="access")["sub"] == "rec1"


def test_jwt_expired_rejected():
    from core.collections.auth import JWTManager, AuthError
    expired = JWTManager(secret=_SECRET, access_ttl=-10).issue_pair("r", "users")
    with pytest.raises(AuthError):
        JWTManager(secret=_SECRET).verify(expired["token"])


def test_jwt_wrong_type_rejected():
    from core.collections.auth import JWTManager, AuthError
    jm = JWTManager(secret=_SECRET)
    pair = jm.issue_pair("r", "users")
    with pytest.raises(AuthError):
        jm.verify(pair["refresh_token"], expected_type="access")


@pytest.mark.parametrize("rule,record,auth,expected", [
    ("", None, None, True),                                              # public
    (None, None, None, False),                                          # admin-only
    ("@request.auth.id != ''", None, {"id": "u1"}, True),
    ("@request.auth.id != ''", None, None, False),
    ("owner = @request.auth.id", {"owner": "u1"}, {"id": "u1"}, True),
    ("owner = @request.auth.id", {"owner": "u2"}, {"id": "u1"}, False),
    ('status = "public" || @request.auth.role = "admin"', {"status": "x"}, {"role": "admin"}, True),
    ("views >= 10", {"views": 12}, None, True),
    ("views >= 10", {"views": 3}, None, False),
    ('title ~ "ell"', {"title": "hello"}, None, True),
])
def test_rule_engine(rule, record, auth, expected):
    from core.collections.auth import RuleEngine
    assert RuleEngine().evaluate(rule, record=record, auth=auth) is expected


def test_rule_engine_rejects_code_injection():
    from core.collections.auth import RuleEngine, AuthError
    with pytest.raises(AuthError):
        RuleEngine().evaluate("__import__('os').system('echo pwned')")


def test_auth_service_register_authenticate(conn):
    from core.collections.auth import AuthService, JWTManager, AuthError
    eng = CollectionEngine(conn)
    eng.create_collection(Collection(name="users", type="auth",
                                     fields=[{"name": "name", "type": "text"}]))
    svc = AuthService(eng, jwt=JWTManager(secret=_SECRET))
    user = svc.register("users", {"email": "a@b.com", "password": "longpass123", "name": "A"})
    assert "password" not in user
    res = svc.authenticate("users", "a@b.com", "longpass123")
    assert res["record"]["email"] == "a@b.com"
    assert svc.identity(res["token"])["email"] == "a@b.com"
    with pytest.raises(AuthError):
        svc.authenticate("users", "a@b.com", "wrongpass")


def test_auth_service_authorize_rule(conn):
    from core.collections.auth import AuthService, JWTManager
    eng = CollectionEngine(conn)
    eng.create_collection(Collection(
        name="docs", fields=[{"name": "owner", "type": "text"}],
        update_rule="owner = @request.auth.id"))
    svc = AuthService(eng, jwt=JWTManager(secret=_SECRET))
    assert svc.authorize("docs", "update", record={"owner": "u1"}, auth={"id": "u1"}) is True
    assert svc.authorize("docs", "update", record={"owner": "u1"}, auth={"id": "u2"}) is False


# ── hooks ──────────────────────────────────────────────────────────────────
def test_hook_priority_and_mutation_order():
    from core.collections.hooks import CollectionHooks, HookContext
    hooks = CollectionHooks(publish_events=False)
    order = []
    hooks.before_create(lambda c: order.append("hi"), priority=10)
    hooks.before_create(lambda c: order.append("lo"), priority=0)
    hooks.fire("before_create", HookContext("notes", "create", "before", data={}))
    assert order == ["lo", "hi"]


def test_engine_fires_hooks_around_crud(conn):
    from core.collections.hooks import CollectionHooks, HookCancelled
    hooks = CollectionHooks(publish_events=False)
    events = []
    hooks.before_create(lambda c: c.data.update(slug="auto"))
    hooks.after_create(lambda c: events.append(("after_create", c.record_id)))
    hooks.after_update(lambda c: events.append(("after_update", c.record_id)))
    hooks.after_delete(lambda c: events.append(("after_delete", c.record_id)))

    eng = CollectionEngine(conn, hooks=hooks)
    eng.create_collection(Collection(name="notes", fields=[
        {"name": "title", "type": "text", "required": True},
        {"name": "slug", "type": "text"},
    ]))
    rec = eng.create_record("notes", {"title": "Hi"})
    assert rec["slug"] == "auto"                      # before-hook mutation persisted
    eng.update_record("notes", rec["id"], {"title": "Bye"})
    eng.delete_record("notes", rec["id"])
    assert events == [
        ("after_create", rec["id"]),
        ("after_update", rec["id"]),
        ("after_delete", rec["id"]),
    ]


def test_before_hook_can_cancel_create(conn):
    from core.collections.hooks import CollectionHooks, HookCancelled
    hooks = CollectionHooks(publish_events=False)
    hooks.before_create(lambda c: c.cancel("not allowed"))
    eng = CollectionEngine(conn, hooks=hooks)
    eng.create_collection(Collection(name="notes", fields=[{"name": "title", "type": "text"}]))
    with pytest.raises(HookCancelled):
        eng.create_record("notes", {"title": "x"})
    assert eng.list_records("notes")["total_items"] == 0


def test_hook_broadcasts_to_event_bus():
    import asyncio

    async def run():
        from core.event_bus import AsyncEventBus, EventType
        from core.collections.hooks import CollectionHooks, HookContext
        bus = AsyncEventBus()
        await bus.start()
        got = []
        bus.subscribe(EventType.RECORD_CREATED, lambda e: got.append(e))
        hooks = CollectionHooks(bus=bus, publish_events=True)
        hooks.fire("after_create", HookContext("notes", "create", "after",
                                               record_id="r1", record={"id": "r1"}))
        await asyncio.sleep(0.2)
        await bus.stop()
        return got

    delivered = asyncio.run(run())
    assert len(delivered) == 1
    assert delivered[0].data["record_id"] == "r1"


# ── end-to-end HTTP (FastAPI TestClient, isolated in-memory DB) ───────────────
@pytest.fixture()
def api_client(conn, tmp_path, monkeypatch):
    fastapi = pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from core.api.routers import collections as col_router
    from core.collections import (
        CollectionEngine, AuthService, JWTManager, FileStorage, CollectionHooks,
    )
    from core.collections.storage import LocalDriver

    eng = CollectionEngine(conn, hooks=CollectionHooks(publish_events=False))
    svc = AuthService(eng, jwt=JWTManager(secret="x" * 40))
    store = FileStorage(LocalDriver(str(tmp_path / "files")))
    monkeypatch.setattr(col_router, "_engine", eng)
    monkeypatch.setattr(col_router, "_auth", svc)
    monkeypatch.setattr(col_router, "_storage", store)

    app = FastAPI()
    app.include_router(col_router.router)
    return TestClient(app)


def test_api_collection_and_record_crud(api_client):
    r = api_client.post("/api/collections", json={
        "name": "notes", "type": "base",
        "fields": [{"name": "title", "type": "text", "required": True},
                   {"name": "views", "type": "number", "options": {"only_int": True}}],
        "list_rule": "", "view_rule": "", "create_rule": "", "update_rule": "", "delete_rule": "",
    })
    assert r.status_code == 200, r.text

    r = api_client.post("/api/collections/notes/records", json={"title": "hello", "views": 3})
    assert r.status_code == 200, r.text
    rec_id = r.json()["id"]

    r = api_client.get("/api/collections/notes/records", params={"filter": "views >= 2"})
    assert r.status_code == 200 and r.json()["total_items"] == 1

    r = api_client.patch(f"/api/collections/notes/records/{rec_id}", json={"views": 50})
    assert r.status_code == 200 and r.json()["views"] == 50

    r = api_client.delete(f"/api/collections/notes/records/{rec_id}")
    assert r.status_code == 200
    assert api_client.get("/api/collections/notes/records").json()["total_items"] == 0


def test_api_bad_filter_returns_400(api_client):
    api_client.post("/api/collections", json={"name": "notes",
                    "fields": [{"name": "title", "type": "text"}], "list_rule": ""})
    r = api_client.get("/api/collections/notes/records", params={"filter": "bogus = 1"})
    assert r.status_code == 400


def test_api_rbac_blocks_anonymous_create(api_client):
    # create_rule requires an authenticated identity
    api_client.post("/api/collections", json={
        "name": "secure", "fields": [{"name": "title", "type": "text"}],
        "create_rule": "@request.auth.id != ''", "list_rule": "",
    })
    # anonymous create → 403
    r = api_client.post("/api/collections/secure/records", json={"title": "x"})
    assert r.status_code == 403


def test_api_auth_flow_and_token_gated_create(api_client):
    api_client.post("/api/collections", json={"name": "users", "type": "auth", "fields": []})
    api_client.post("/api/collections", json={
        "name": "secure", "fields": [{"name": "title", "type": "text"}],
        "create_rule": "@request.auth.id != ''",
    })
    reg = api_client.post("/api/collections/users/records-auth",
                          json={"email": "a@b.com", "password": "longpass123"})
    assert reg.status_code == 200, reg.text

    login = api_client.post("/api/collections/users/auth-with-password",
                            json={"email": "a@b.com", "password": "longpass123"})
    assert login.status_code == 200, login.text
    token = login.json()["token"]

    r = api_client.post("/api/collections/secure/records", json={"title": "ok"},
                        headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


def test_api_auth_with_oauth2(api_client):
    api_client.post("/api/collections", json={
        "name": "users", "type": "auth", "fields": [{"name": "name", "type": "text"}]})
    r = api_client.post("/api/collections/users/auth-with-oauth2",
                        json={"identity": {"email": "oauth@b.com", "name": "OAuthUser"}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token"] and body["record"]["email"] == "oauth@b.com"
    assert "password" not in body["record"]
    # second login finds the same record (no duplicate created)
    r2 = api_client.post("/api/collections/users/auth-with-oauth2",
                         json={"identity": {"email": "oauth@b.com"}})
    assert r2.status_code == 200
    assert r2.json()["record"]["id"] == body["record"]["id"]


def test_mcp_collection_tools(conn, monkeypatch):
    import asyncio
    pytest.importorskip("fastmcp")
    from fastmcp import FastMCP
    import core.memory.episodic as ep

    # point the engine the MCP tools build at our isolated in-memory DB
    monkeypatch.setattr(ep, "get_db_connection", lambda: conn)
    eng = CollectionEngine(conn)
    eng.create_collection(Collection(name="notes", fields=[{"name": "title", "type": "text"}]))
    eng.create_record("notes", {"title": "hello"})

    from core.mcp_server import _add_collections_tools
    mcp = FastMCP("test")
    _add_collections_tools(mcp)

    def _text(res):
        out = str(res)
        for attr in ("content", "data", "structured_content"):
            v = getattr(res, attr, None)
            if v:
                out += str(v)
        return out

    async def run():
        listed = await mcp.list_tools()
        names = set(listed.keys()) if isinstance(listed, dict) else {t.name for t in listed}
        assert {"collection_list", "collection_query", "collection_record_create"} <= names
        q = await mcp.call_tool("collection_query", {"name": "notes"})
        c = await mcp.call_tool("collection_record_create",
                                {"name": "notes", "data_json": '{"title": "made-via-mcp"}'})
        return _text(q), _text(c)

    q_text, c_text = asyncio.run(run())
    assert "hello" in q_text
    assert "made-via-mcp" in c_text
    assert eng.list_records("notes")["total_items"] == 2


def test_api_file_upload_download(api_client):
    api_client.post("/api/collections", json={
        "name": "docs", "fields": [{"name": "attachment", "type": "file"}],
        "update_rule": "", "create_rule": "", "view_rule": "",
    })
    rec = api_client.post("/api/collections/docs/records", json={}).json()
    up = api_client.post(
        f"/api/files/docs/{rec['id']}/attachment",
        files={"file": ("hi.txt", b"file bytes", "text/plain")},
    )
    assert up.status_code == 200, up.text
    dl = api_client.get(f"/api/files/docs/{rec['id']}/attachment/hi.txt")
    assert dl.status_code == 200 and dl.content == b"file bytes"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
