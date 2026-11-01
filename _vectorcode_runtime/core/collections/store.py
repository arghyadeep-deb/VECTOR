"""Generic record CRUD + collection registry for the VECTOR collections engine.

Python reimplementation of PocketBase's record DAO and filter language
(apis/record_crud*.go, core record store). Provides:
  - CollectionStore: validated create/get/list/update/delete over any Collection,
    with a SAFE filter parser (field whitelist + bound parameters — never string SQL),
    sort, pagination and relation expansion.
  - CollectionEngine: persists collection definitions in a `_collections` table and
    creates/drops the backing `col_<name>` data tables.

Reuses VECTOR's existing encrypted SQLite connection (core.memory.episodic.get_db_connection).
The 5 sacred memory tables are never touched — collections live in their own namespace.
"""

from __future__ import annotations

from core.memory.db_utils import apply_pragmas
import sys

__all__ = [
    "FilterError",
    "parse_filter",
    "parse_sort",
    "CollectionStore",
    "CollectionEngine",
]


import json
import re
import secrets
import string
from datetime import datetime, timezone

from loguru import logger
from core.config import CONFIG  # noqa: F401

from core.collections.fields import FieldType, ValidationError
from core.collections.schema import Collection

_ID_ALPHABET = string.ascii_lowercase + string.digits
_OPS = {
    "=": "=", "!=": "!=", ">": ">", ">=": ">=", "<": "<", "<=": "<=",
    "~": "LIKE", "!~": "NOT LIKE",
}
# Longest-first so ">=" wins over ">", "!~" over "~", etc.
_OP_TOKENS = sorted(_OPS.keys(), key=len, reverse=True)
_TOKEN_RE = re.compile(
    r"""\s*(
        \(|\)|
        &&|\|\||
        >=|<=|!=|!~|=|>|<|~|
        "(?:[^"\\]|\\.)*"|
        '(?:[^'\\]|\\.)*'|
        [A-Za-z_][A-Za-z0-9_.]*|
        -?\d+(?:\.\d+)?
    )""",
    re.VERBOSE,
)


class FilterError(ValueError):
    """Raised when a filter expression is malformed or references unknown fields."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id() -> str:
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(15))


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _tokenize(expr: str) -> list[str]:
    tokens, pos = [], 0
    while pos < len(expr):
        if expr[pos].isspace():
            pos += 1
            continue
        m = _TOKEN_RE.match(expr, pos)
        if not m or m.start(1) == -1:
            raise FilterError(f"unexpected token near: {expr[pos:pos + 20]!r}")
        tokens.append(m.group(1))
        pos = m.end(1)
    return tokens


class _FilterParser:
    """Recursive-descent parser → (where_sql, params). Field names are whitelisted
    and emitted as quoted identifiers; all values become bound parameters."""

    def __init__(self, tokens: list[str], allowed_fields: set[str]):
        self.toks = tokens
        self.i = 0
        self.allowed = allowed_fields
        self.params: list = []

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def _next(self):
        tok = self._peek()
        self.i += 1
        return tok

    def parse(self) -> tuple[str, list]:
        sql = self._or()
        if self.i != len(self.toks):
            raise FilterError(f"trailing tokens after valid expression: {self.toks[self.i:]}")
        return sql, self.params

    def _or(self) -> str:
        left = self._and()
        while self._peek() == "||":
            self._next()
            right = self._and()
            left = f"({left} OR {right})"
        return left

    def _and(self) -> str:
        left = self._cmp()
        while self._peek() == "&&":
            self._next()
            right = self._cmp()
            left = f"({left} AND {right})"
        return left

    def _cmp(self) -> str:
        if self._peek() == "(":
            self._next()
            inner = self._or()
            if self._next() != ")":
                raise FilterError("missing closing parenthesis")
            return f"({inner})"

        field = self._next()
        if field is None or field in _OPS or field in ("(", ")", "&&", "||"):
            raise FilterError(f"expected a field name, got {field!r}")
        if field not in self.allowed:
            raise FilterError(f"unknown field in filter: {field!r}")

        op_tok = self._next()
        if op_tok not in _OPS:
            raise FilterError(f"expected an operator after {field!r}, got {op_tok!r}")
        sql_op = _OPS[op_tok]

        val_tok = self._next()
        if val_tok is None or val_tok in _OPS or val_tok in ("(", ")", "&&", "||"):
            raise FilterError(f"expected a value after {field!r} {op_tok}")
        value = self._coerce_value(val_tok)

        col = f'"{field}"'
        if sql_op in ("LIKE", "NOT LIKE"):
            self.params.append(f"%{_like_escape(str(value))}%")
            return f"{col} {sql_op} ? ESCAPE '\\'"
        if value is None:
            return f"{col} IS NULL" if sql_op == "=" else f"{col} IS NOT NULL"
        self.params.append(value)
        return f"{col} {sql_op} ?"

    @staticmethod
    def _coerce_value(tok: str):
        if (tok.startswith('"') and tok.endswith('"')) or (tok.startswith("'") and tok.endswith("'")):
            inner = tok[1:-1]
            return inner.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")
        if tok == "true":
            return 1
        if tok == "false":
            return 0
        if tok == "null":
            return None
        try:
            return int(tok)
        except ValueError:
            pass
        try:
            return float(tok)
        except ValueError:
            pass
        return tok  # bare word treated as string literal


def parse_filter(expr: str, allowed_fields: set[str]) -> tuple[str, list]:
    """Parse a PocketBase-style filter into a parameterized WHERE clause.

    Returns (where_sql, params). Raises FilterError on bad input or unknown fields.
    """
    if not expr or not expr.strip():
        return "", []
    tokens = _tokenize(expr)
    return _FilterParser(tokens, allowed_fields).parse()


def parse_sort(spec: str, allowed_fields: set[str]) -> str:
    """Parse "-created,title" into a safe ORDER BY clause. Unknown fields rejected."""
    if not spec or not spec.strip():
        return ""
    parts = []
    for raw in spec.split(","):
        raw = raw.strip()
        if not raw:
            continue
        desc = raw.startswith("-")
        name = raw[1:] if raw[0] in "+-" else raw
        if name not in allowed_fields:
            raise FilterError(f"unknown sort field: {name!r}")
        parts.append(f'"{name}" {"DESC" if desc else "ASC"}')
    return ", ".join(parts)


class CollectionStore:
    """Validated record CRUD for a single Collection over a shared DB connection."""

    def __init__(self, conn=None):
        if conn is None:
            from core.memory.episodic import get_db_connection
            conn = get_db_connection()
        self.conn = conn

    # ── helpers ────────────────────────────────────────────────────────────
    @staticmethod
    def _sortable(collection: Collection) -> set[str]:
        return {"id", "created", "updated", *collection.field_names()}

    def _row_to_record(self, collection: Collection, row) -> dict:
        cols = collection.all_column_names()
        rec = dict(zip(cols, row))
        for f in collection.fields:
            if f.type == FieldType.PASSWORD:
                rec.pop(f.name, None)            # never expose password hashes
                continue
            if f.stored_as_json() and rec.get(f.name) is not None:
                try:
                    rec[f.name] = json.loads(rec[f.name])
                except (TypeError, json.JSONDecodeError):
                    pass
            elif f.type == FieldType.BOOL and rec.get(f.name) is not None:
                rec[f.name] = bool(rec[f.name])
        return rec

    def _validate_payload(self, collection: Collection, data: dict, *, partial: bool) -> dict:
        out = {}
        for f in collection.fields:
            if f.type == FieldType.AUTODATE:
                continue  # system-managed
            if f.name not in data:
                if partial:
                    continue
                if f.required:
                    # validate(None) raises the required error with the field name
                    f.validate(None)
                continue
            out[f.name] = f.validate(data[f.name])
        return out

    # ── CRUD ───────────────────────────────────────────────────────────────
    def create(self, collection: Collection, data: dict, record_id: str | None = None) -> dict:
        values = self._validate_payload(collection, data, partial=False)
        rec_id = record_id or _gen_id()
        now = _now()
        values["id"] = rec_id
        values["created"] = now
        values["updated"] = now
        cols = list(values.keys())
        placeholders = ", ".join("?" for _ in cols)
        quoted = ", ".join(f'"{c}"' for c in cols)
        with self.conn:
            self.conn.execute(
                f'INSERT INTO "{collection.table}" ({quoted}) VALUES ({placeholders})',
                [values[c] for c in cols],
            )
        logger.debug(f"[VECTOR][collections] created {collection.name}/{rec_id}")
        return self.get(collection, rec_id)

    def get(self, collection: Collection, record_id: str) -> dict | None:
        cur = self.conn.execute(
            f'SELECT {", ".join(chr(34) + c + chr(34) for c in collection.all_column_names())} '
            f'FROM "{collection.table}" WHERE id = ?',
            (record_id,),
        )
        row = cur.fetchone()
        return self._row_to_record(collection, row) if row else None

    def list(self, collection: Collection, *, filter: str | None = None,
             sort: str | None = None, page: int = 1, per_page: int = 30,
             expand: list[str] | None = None) -> dict:
        allowed = set(collection.field_names()) | {"id", "created", "updated"}
        where_sql, params = parse_filter(filter or "", allowed)
        order_sql = parse_sort(sort or "", self._sortable(collection))

        per_page = max(1, min(int(per_page), 500))
        page = max(1, int(page))
        offset = (page - 1) * per_page

        base = f'FROM "{collection.table}"'
        if where_sql:
            base += f" WHERE {where_sql}"
        total = self.conn.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]

        select_cols = ", ".join(f'"{c}"' for c in collection.all_column_names())
        q = f"SELECT {select_cols} {base}"
        if order_sql:
            q += f" ORDER BY {order_sql}"
        else:
            q += ' ORDER BY "created" DESC'
        q += " LIMIT ? OFFSET ?"
        rows = self.conn.execute(q, [*params, per_page, offset]).fetchall()
        items = [self._row_to_record(collection, r) for r in rows]

        if expand:
            self._expand(collection, items, expand)

        return {
            "page": page,
            "per_page": per_page,
            "total_items": total,
            "total_pages": (total + per_page - 1) // per_page,
            "items": items,
        }

    def update(self, collection: Collection, record_id: str, data: dict) -> dict | None:
        values = self._validate_payload(collection, data, partial=True)
        if not values:
            return self.get(collection, record_id)
        values["updated"] = _now()
        sets = ", ".join(f'"{c}" = ?' for c in values)
        with self.conn:
            cur = self.conn.execute(
                f'UPDATE "{collection.table}" SET {sets} WHERE id = ?',
                [*values.values(), record_id],
            )
        if cur.rowcount == 0:
            return None
        return self.get(collection, record_id)

    def delete(self, collection: Collection, record_id: str) -> bool:
        with self.conn:
            cur = self.conn.execute(
                f'DELETE FROM "{collection.table}" WHERE id = ?', (record_id,)
            )
        return cur.rowcount > 0

    # ── relation expansion ───────────────────────────────────────────────────
    def _expand(self, collection: Collection, items: list[dict], expand: list[str]):
        for field_name in expand:
            f = collection.field(field_name)
            if f is None or f.type != FieldType.RELATION:
                continue
            target_name = f.options.get("collection")
            if not target_name:
                continue
            target = Collection(name=target_name, fields=[])  # minimal — we only need its id column
            target_table = f"col_{target_name}"
            for rec in items:
                ref = rec.get(field_name)
                if ref is None:
                    continue
                ids = ref if isinstance(ref, list) else [ref]
                expanded = []
                for rid in ids:
                    try:
                        row = self.conn.execute(
                            f'SELECT * FROM "{target_table}" WHERE id = ?', (rid,)
                        ).fetchone()
                    except Exception:
                        row = None
                    if row:
                        names = [d[0] for d in self.conn.execute(
                            f'SELECT * FROM "{target_table}" LIMIT 0').description]
                        expanded.append(dict(zip(names, row)))
                rec.setdefault("expand", {})[field_name] = (
                    expanded if isinstance(ref, list) else (expanded[0] if expanded else None)
                )


class CollectionEngine:
    """Top-level facade: persists collection definitions and owns their tables.

    If `hooks` is provided, record create/update/delete fire before/after hooks; a
    before-hook may mutate the payload or cancel (raising HookCancelled).
    """

    def __init__(self, conn=None, hooks=None):
        if conn is None:
            from core.memory.episodic import get_db_connection
            conn = get_db_connection()
        self.conn = conn
        self.store = CollectionStore(conn)
        self.hooks = hooks
        self._ensure_registry()

    def _ensure_registry(self):
        with self.conn:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS _collections ("
                "  name TEXT PRIMARY KEY,"
                "  schema TEXT NOT NULL,"
                "  created TEXT NOT NULL,"
                "  updated TEXT NOT NULL"
                ")"
            )

    def create_collection(self, collection: Collection) -> Collection:
        if self.get_collection(collection.name) is not None:
            raise ValidationError(f"collection {collection.name!r} already exists")
        now = _now()
        with self.conn:
            self.conn.execute(collection.create_table_sql())
            for stmt in collection.index_sql():
                self.conn.execute(stmt)
            self.conn.execute(
                "INSERT INTO _collections (name, schema, created, updated) VALUES (?, ?, ?, ?)",
                (collection.name, json.dumps(collection.to_dict()), now, now),
            )
        logger.info(f"[VECTOR][collections] created collection {collection.name!r}")
        return collection

    def get_collection(self, name: str) -> Collection | None:
        row = self.conn.execute(
            "SELECT schema FROM _collections WHERE name = ?", (name,)
        ).fetchone()
        return Collection.from_dict(json.loads(row[0])) if row else None

    def list_collections(self) -> list[Collection]:
        rows = self.conn.execute(
            "SELECT schema FROM _collections ORDER BY name"
        ).fetchall()
        return [Collection.from_dict(json.loads(r[0])) for r in rows]

    def delete_collection(self, name: str, *, drop_data: bool = True) -> bool:
        coll = self.get_collection(name)
        if coll is None:
            return False
        with self.conn:
            self.conn.execute("DELETE FROM _collections WHERE name = ?", (name,))
            if drop_data:
                self.conn.execute(f'DROP TABLE IF EXISTS "{coll.table}"')
        logger.info(f"[VECTOR][collections] deleted collection {name!r}")
        return True

    # delegation helpers used by the API router (fire hooks when configured)
    def create_record(self, name: str, data: dict, record_id=None) -> dict:
        coll = self._require(name)
        data = self._before("create", name, data=dict(data))
        rec = self.store.create(coll, data, record_id)
        self._after("create", name, record_id=rec["id"], record=rec)
        return rec

    def get_record(self, name: str, record_id: str):
        return self.store.get(self._require(name), record_id)

    def list_records(self, name: str, **kw) -> dict:
        return self.store.list(self._require(name), **kw)

    def update_record(self, name: str, record_id: str, data: dict):
        coll = self._require(name)
        data = self._before("update", name, record_id=record_id, data=dict(data))
        rec = self.store.update(coll, record_id, data)
        if rec is not None:
            self._after("update", name, record_id=record_id, record=rec)
        return rec

    def delete_record(self, name: str, record_id: str) -> bool:
        coll = self._require(name)
        self._before("delete", name, record_id=record_id)
        ok = self.store.delete(coll, record_id)
        if ok:
            self._after("delete", name, record_id=record_id)
        return ok

    # ── hook firing (no-ops when self.hooks is None) ──────────────────────────
    def _before(self, action: str, name: str, *, record_id=None, data=None):
        if not self.hooks:
            return data
        from core.collections.hooks import HookContext, HookCancelled
        ctx = HookContext(collection=name, action=action, phase="before",
                          record_id=record_id, data=data)
        self.hooks.fire(f"before_{action}", ctx)
        if ctx.cancelled:
            raise HookCancelled(ctx.cancel_reason or f"{action} cancelled by hook")
        return ctx.data

    def _after(self, action: str, name: str, *, record_id=None, record=None):
        if not self.hooks:
            return
        from core.collections.hooks import HookContext
        self.hooks.fire(f"after_{action}", HookContext(
            collection=name, action=action, phase="after",
            record_id=record_id, record=record))

    def _require(self, name: str) -> Collection:
        coll = self.get_collection(name)
        if coll is None:
            raise ValidationError(f"collection {name!r} does not exist")
        return coll


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile, os, sqlite3
    ok = True

    # Use an isolated temp DB so the self-test never touches vector_memory.db.
    tmp = tempfile.mkdtemp()
    conn = sqlite3.connect(os.path.join(tmp, "t.db"))
    apply_pragmas(conn)

    eng = CollectionEngine(conn)
    eng.create_collection(Collection(
        name="notes",
        fields=[
            {"name": "title", "type": "text", "required": True},
            {"name": "views", "type": "number", "options": {"only_int": True}},
            {"name": "pinned", "type": "bool"},
            {"name": "tags", "type": "select", "options": {"values": ["a", "b", "c"], "max_select": 3}},
        ],
    ))

    r1 = eng.create_record("notes", {"title": "hello", "views": 5, "pinned": True, "tags": ["a", "b"]})
    r2 = eng.create_record("notes", {"title": "world", "views": 12, "pinned": False, "tags": ["c"]})
    assert r1["title"] == "hello" and r1["pinned"] is True and r1["tags"] == ["a", "b"]

    # filter (safe parameterized) + sort + paginate
    res = eng.list_records("notes", filter='views > 4 && title ~ "ell"', sort="-views")
    assert res["total_items"] == 1 and res["items"][0]["title"] == "hello"

    res2 = eng.list_records("notes", filter='pinned = false')
    assert res2["total_items"] == 1 and res2["items"][0]["title"] == "world"

    # update + get
    eng.update_record("notes", r2["id"], {"views": 99})
    assert eng.get_record("notes", r2["id"])["views"] == 99

    # injection attempt → rejected as unknown field, not executed
    try:
        eng.list_records("notes", filter='title = "x"; DROP TABLE col_notes;--')
        ok = False
    except FilterError:
        pass
    # table must still exist
    assert eng.get_record("notes", r1["id"]) is not None

    # unknown sort field rejected
    try:
        eng.list_records("notes", sort="evil")
        ok = False
    except FilterError:
        pass

    # delete
    assert eng.delete_record("notes", r1["id"]) is True
    assert eng.get_record("notes", r1["id"]) is None

    # registry round-trip
    assert [c.name for c in eng.list_collections()] == ["notes"]
    assert eng.delete_collection("notes") is True
    assert eng.list_collections() == []

    conn.close()
    print("✅ store.py OK" if ok else "❌ FAILED")
