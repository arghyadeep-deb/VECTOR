"""Collection schema definitions for the VECTOR collections engine.

Python reimplementation of PocketBase's collection model (core/collection_model*.go):
a Collection is a named, typed set of Fields plus per-action access rules. Two kinds:
  - base: ordinary data collection
  - auth: data collection that also carries identity (email/password/tokenKey) and
          can be authenticated against (see core/collections/auth.py).

Access rules are PocketBase-style rule strings (e.g. "@request.auth.id != ''"). They
are evaluated safely by RuleEngine in auth.py — never with python eval().
"""

import sys

__all__ = [
    "CollectionType",
    "Collection",
    "RESERVED_NAMES",
]


import re
from dataclasses import dataclass, field as dc_field
from enum import Enum

from core.config import CONFIG  # noqa: F401

from core.collections.fields import Field, FieldType, build_field, ValidationError

_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{0,62}$")

# Never let a collection shadow VECTOR's sacred memory tables or engine tables.
RESERVED_NAMES = {
    "episodic_memory", "episodic_memory_fts", "semantic_memory", "policy_memory",
    "reasoning_chains", "agent_history", "skill_memory",
    "_collections", "_migrations", "sqlite_master", "sqlite_sequence",
}

# Auth collections always carry these system fields in addition to user fields.
_AUTH_SYSTEM_FIELDS = [
    {"name": "email", "type": "email", "required": True, "unique": True},
    {"name": "password", "type": "password", "required": True, "options": {"min": 8}},
    {"name": "verified", "type": "bool"},
]


class CollectionType(str, Enum):
    BASE = "base"
    AUTH = "auth"


@dataclass
class Collection:
    """A dynamic table definition.

    System columns present on every record (not in `fields`): id, created, updated.
    Rules are None ⇒ admin-only; "" (empty string) ⇒ public; otherwise a rule expr.
    """
    name: str
    type: CollectionType = CollectionType.BASE
    fields: list = dc_field(default_factory=list)
    indexes: list = dc_field(default_factory=list)   # list[list[str]] — each inner list = composite index
    list_rule: str | None = None
    view_rule: str | None = None
    create_rule: str | None = None
    update_rule: str | None = None
    delete_rule: str | None = None

    def __post_init__(self):
        if isinstance(self.type, str):
            self.type = CollectionType(self.type)
        if not _NAME_RE.match(self.name):
            raise ValidationError(
                f"collection name {self.name!r} invalid (letters/digits/_, must start with a letter, ≤63 chars)"
            )
        if self.name in RESERVED_NAMES:
            raise ValidationError(f"collection name {self.name!r} is reserved")
        # Normalize fields → Field objects.
        norm: list[Field] = []
        for f in self.fields:
            norm.append(f if isinstance(f, Field) else build_field(f))
        # Auth collections get system identity fields prepended (dedup by name).
        if self.type == CollectionType.AUTH:
            existing = {f.name for f in norm}
            for spec in _AUTH_SYSTEM_FIELDS:
                if spec["name"] not in existing:
                    norm.insert(0, build_field(spec))
        # Reject duplicate field names and clashes with system columns.
        seen = set()
        for f in norm:
            if f.name in {"id", "created", "updated"}:
                raise ValidationError(f"field {f.name!r} clashes with a system column")
            if f.name in seen:
                raise ValidationError(f"duplicate field {f.name!r}")
            seen.add(f.name)
        self.fields = norm

    @property
    def table(self) -> str:
        """Physical SQLite table name — namespaced to avoid collisions."""
        return f"col_{self.name}"

    def field(self, name: str) -> Field | None:
        for f in self.fields:
            if f.name == name:
                return f
        return None

    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    def all_column_names(self) -> list[str]:
        return ["id", "created", "updated", *self.field_names()]

    def create_table_sql(self) -> str:
        cols = [
            "id TEXT PRIMARY KEY",
            "created TEXT NOT NULL",
            "updated TEXT NOT NULL",
        ]
        for f in self.fields:
            col = f"{f.name} {f.sql_type()}"
            if f.required and f.type != FieldType.AUTODATE:
                col += " NOT NULL DEFAULT ''" if f.sql_type() == "TEXT" else " NOT NULL DEFAULT 0"
            cols.append(col)
        return f'CREATE TABLE IF NOT EXISTS "{self.table}" (\n  ' + ",\n  ".join(cols) + "\n)"

    def index_sql(self) -> list[str]:
        stmts = []
        for f in self.fields:
            if f.unique:
                stmts.append(
                    f'CREATE UNIQUE INDEX IF NOT EXISTS "ux_{self.name}_{f.name}" '
                    f'ON "{self.table}" ("{f.name}")'
                )
        for i, cols in enumerate(self.indexes):
            safe = [c for c in cols if self.field(c) or c in ("id", "created", "updated")]
            if not safe:
                continue
            quoted = ", ".join(f'"{c}"' for c in safe)
            stmts.append(
                f'CREATE INDEX IF NOT EXISTS "ix_{self.name}_{i}" ON "{self.table}" ({quoted})'
            )
        return stmts

    def rule_for(self, action: str) -> str | None:
        return {
            "list": self.list_rule,
            "view": self.view_rule,
            "create": self.create_rule,
            "update": self.update_rule,
            "delete": self.delete_rule,
        }.get(action)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type.value,
            "fields": [f.to_dict() for f in self.fields],
            "indexes": self.indexes,
            "list_rule": self.list_rule,
            "view_rule": self.view_rule,
            "create_rule": self.create_rule,
            "update_rule": self.update_rule,
            "delete_rule": self.delete_rule,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Collection":
        return cls(
            name=d["name"],
            type=CollectionType(d.get("type", "base")),
            fields=[build_field(f) for f in d.get("fields", [])],
            indexes=d.get("indexes", []),
            list_rule=d.get("list_rule"),
            view_rule=d.get("view_rule"),
            create_rule=d.get("create_rule"),
            update_rule=d.get("update_rule"),
            delete_rule=d.get("delete_rule"),
        )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True

    c = Collection(
        name="notes",
        fields=[
            {"name": "title", "type": "text", "required": True, "unique": True},
            {"name": "body", "type": "editor"},
            {"name": "pinned", "type": "bool"},
        ],
        indexes=[["title", "pinned"]],
        list_rule="",  # public list
    )
    assert c.table == "col_notes"
    assert c.field_names() == ["title", "body", "pinned"]
    assert 'CREATE TABLE IF NOT EXISTS "col_notes"' in c.create_table_sql()
    idx = c.index_sql()
    assert any("ux_notes_title" in s for s in idx)   # unique index
    assert any("ix_notes_0" in s for s in idx)        # composite index

    # round-trip serialization
    c2 = Collection.from_dict(c.to_dict())
    assert c2.field_names() == c.field_names()

    # auth collection auto-adds email/password/verified
    au = Collection(name="users", type="auth", fields=[{"name": "displayName", "type": "text"}])
    assert "email" in au.field_names() and "password" in au.field_names()

    # reserved + bad names rejected
    for bad in ("episodic_memory", "_migrations", "1bad", "bad-name"):
        try:
            Collection(name=bad)
            ok = False
        except ValidationError:
            pass

    # system column clash rejected
    try:
        Collection(name="x", fields=[{"name": "id", "type": "text"}])
        ok = False
    except ValidationError:
        pass

    print("✅ schema.py OK" if ok else "❌ FAILED")
