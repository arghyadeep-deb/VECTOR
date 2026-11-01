"""Field type system for the VECTOR collections engine.

Ported in Python from PocketBase's Go field types (core/field_*.go). Defines the
field kinds a dynamic collection can have, their per-type validators, and how each
maps to a SQLite column type. No Go code is copied — this is a clean reimplementation
of the *concept* (dynamic, validated, polymorphic fields) for VECTOR's SQLite layer.
"""

import sys

__all__ = [
    "FieldType",
    "Field",
    "ValidationError",
    "build_field",
]


import json
import re
import math
from dataclasses import dataclass, field as dc_field
from datetime import datetime, date
from enum import Enum

from core.config import CONFIG  # noqa: F401  (kept per VECTOR file convention)


class ValidationError(ValueError):
    """Raised when a value fails a field's validation rules."""


class FieldType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    BOOL = "bool"
    EMAIL = "email"
    URL = "url"
    DATE = "date"
    AUTODATE = "autodate"   # auto-set on create/update — never user-supplied
    SELECT = "select"
    JSON = "json"
    RELATION = "relation"
    FILE = "file"
    PASSWORD = "password"   # stored as a hash; write-only in API responses
    EDITOR = "editor"       # rich text / markdown / html blob
    GEOPOINT = "geopoint"   # {"lon": float, "lat": float}


# Field types whose stored representation is a JSON blob (multi-value or structured).
_JSON_STORED = {FieldType.JSON, FieldType.GEOPOINT}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


@dataclass
class Field:
    """One field within a collection's schema.

    options carries per-type config:
      number:   {"min": float, "max": float, "only_int": bool}
      text/editor: {"min": int, "max": int, "pattern": str}
      select:   {"values": [...], "max_select": int}   (max_select>1 ⇒ multi)
      relation: {"collection": str, "max_select": int}  (max_select>1 ⇒ multi)
      file:     {"max_select": int, "mime_types": [...], "max_size": int}
      password: {"min": int}
    """
    name: str
    type: FieldType
    required: bool = False
    unique: bool = False
    options: dict = dc_field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.type, str):
            self.type = FieldType(self.type)
        if not _IDENT_RE.match(self.name):
            raise ValidationError(
                f"field name {self.name!r} is not a safe identifier (letters/digits/_, no leading digit)"
            )

    # ── DDL ────────────────────────────────────────────────────────────────
    def sql_type(self) -> str:
        if self.type == FieldType.NUMBER:
            return "INTEGER" if self.options.get("only_int") else "REAL"
        if self.type == FieldType.BOOL:
            return "INTEGER"
        return "TEXT"

    def is_multi(self) -> bool:
        return int(self.options.get("max_select", 1)) > 1

    def stored_as_json(self) -> bool:
        return self.type in _JSON_STORED or (
            self.type in {FieldType.SELECT, FieldType.RELATION, FieldType.FILE} and self.is_multi()
        )

    # ── Validation ───────────────────────────────────────────────────────────
    def validate(self, value):
        """Validate + normalize a value for storage. Returns the storable value.

        Raises ValidationError on bad input. None is allowed unless required.
        """
        if value is None or value == "":
            if self.required and self.type != FieldType.AUTODATE:
                raise ValidationError(f"{self.name} is required")
            return None

        handler = getattr(self, f"_v_{self.type.value}", None)
        if handler is None:
            raise ValidationError(f"unknown field type {self.type}")
        return handler(value)

    def _v_text(self, v):
        s = str(v)
        opts = self.options
        if "min" in opts and len(s) < int(opts["min"]):
            raise ValidationError(f"{self.name} shorter than min {opts['min']}")
        if "max" in opts and len(s) > int(opts["max"]):
            raise ValidationError(f"{self.name} longer than max {opts['max']}")
        if opts.get("pattern") and not re.match(opts["pattern"], s):
            raise ValidationError(f"{self.name} does not match required pattern")
        return s

    _v_editor = _v_text

    def _v_number(self, v):
        try:
            num = float(v)
        except (TypeError, ValueError):
            raise ValidationError(f"{self.name} must be a number")
        if math.isnan(num) or math.isinf(num):
            raise ValidationError(f"{self.name} must be finite")
        if self.options.get("only_int"):
            if num != int(num):
                raise ValidationError(f"{self.name} must be an integer")
            num = int(num)
        if "min" in self.options and num < float(self.options["min"]):
            raise ValidationError(f"{self.name} below min {self.options['min']}")
        if "max" in self.options and num > float(self.options["max"]):
            raise ValidationError(f"{self.name} above max {self.options['max']}")
        return num

    def _v_bool(self, v):
        if isinstance(v, bool):
            return 1 if v else 0
        if isinstance(v, (int, float)):
            return 1 if v else 0
        if isinstance(v, str):
            return 1 if v.strip().lower() in {"1", "true", "yes", "on"} else 0
        return 1 if v else 0

    def _v_email(self, v):
        s = str(v).strip()
        if not _EMAIL_RE.match(s):
            raise ValidationError(f"{self.name} is not a valid email")
        return s

    def _v_url(self, v):
        s = str(v).strip()
        if not _URL_RE.match(s):
            raise ValidationError(f"{self.name} is not a valid http(s) URL")
        return s

    def _v_date(self, v):
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        s = str(v)
        try:
            datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            raise ValidationError(f"{self.name} is not a valid ISO date")
        return s

    def _v_autodate(self, v):
        # autodate is system-managed; accept whatever the store sets.
        return self._v_date(v)

    def _v_select(self, v):
        allowed = self.options.get("values", [])
        if self.is_multi():
            items = v if isinstance(v, list) else [v]
            for item in items:
                if allowed and item not in allowed:
                    raise ValidationError(f"{self.name}: {item!r} not in allowed values")
            max_sel = int(self.options.get("max_select", len(items)))
            if len(items) > max_sel:
                raise ValidationError(f"{self.name}: too many selections (max {max_sel})")
            return json.dumps(items)
        if allowed and v not in allowed:
            raise ValidationError(f"{self.name}: {v!r} not in allowed values")
        return str(v)

    def _v_json(self, v):
        try:
            json.dumps(v)
        except (TypeError, ValueError):
            raise ValidationError(f"{self.name} is not JSON-serializable")
        return json.dumps(v)

    def _v_relation(self, v):
        if self.is_multi():
            ids = v if isinstance(v, list) else [v]
            ids = [str(x) for x in ids]
            max_sel = int(self.options.get("max_select", len(ids)))
            if len(ids) > max_sel:
                raise ValidationError(f"{self.name}: too many relations (max {max_sel})")
            return json.dumps(ids)
        return str(v)

    def _v_file(self, v):
        # Stores filename(s); the storage layer owns the bytes. Reject path traversal.
        def _clean(name: str) -> str:
            name = str(name)
            if "/" in name or "\\" in name or ".." in name:
                raise ValidationError(f"{self.name}: unsafe file name {name!r}")
            return name
        if self.is_multi():
            names = v if isinstance(v, list) else [v]
            return json.dumps([_clean(n) for n in names])
        return _clean(v)

    def _v_password(self, v):
        s = str(v)
        min_len = int(self.options.get("min", 8))
        if len(s) < min_len:
            raise ValidationError(f"{self.name} must be at least {min_len} chars")
        # The auth layer hashes this; we never store plaintext.
        return s

    def _v_geopoint(self, v):
        if not isinstance(v, dict) or "lon" not in v or "lat" not in v:
            raise ValidationError(f"{self.name} must be {{'lon':..,'lat':..}}")
        try:
            lon, lat = float(v["lon"]), float(v["lat"])
        except (TypeError, ValueError):
            raise ValidationError(f"{self.name} lon/lat must be numbers")
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValidationError(f"{self.name} lon/lat out of range")
        return json.dumps({"lon": lon, "lat": lat})

    # ── Serialization ─────────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type.value,
            "required": self.required,
            "unique": self.unique,
            "options": self.options,
        }


def build_field(spec: dict) -> Field:
    """Construct a Field from a plain dict (e.g. API/JSON input)."""
    return Field(
        name=spec["name"],
        type=FieldType(spec["type"]),
        required=bool(spec.get("required", False)),
        unique=bool(spec.get("unique", False)),
        options=dict(spec.get("options", {})),
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ok = True

    # text min/max
    t = Field("title", FieldType.TEXT, required=True, options={"min": 2, "max": 10})
    assert t.validate("hello") == "hello"
    try:
        t.validate("x"); ok = False
    except ValidationError:
        pass

    # number int + range
    n = Field("age", FieldType.NUMBER, options={"only_int": True, "min": 0, "max": 120})
    assert n.validate("30") == 30
    try:
        n.validate(3.5); ok = False
    except ValidationError:
        pass

    # email / url
    assert Field("e", FieldType.EMAIL).validate("a@b.com") == "a@b.com"
    try:
        Field("e", FieldType.EMAIL).validate("nope"); ok = False
    except ValidationError:
        pass

    # bool coercion
    assert Field("b", FieldType.BOOL).validate("true") == 1
    assert Field("b", FieldType.BOOL).validate(0) == 0

    # select multi + json storage
    s = Field("tags", FieldType.SELECT, options={"values": ["a", "b", "c"], "max_select": 2})
    assert json.loads(s.validate(["a", "b"])) == ["a", "b"]
    assert s.stored_as_json()
    try:
        s.validate(["a", "b", "c"]); ok = False
    except ValidationError:
        pass

    # relation single
    r = Field("owner", FieldType.RELATION, options={"collection": "users"})
    assert r.validate("rec123") == "rec123"

    # file path traversal rejected
    f = Field("doc", FieldType.FILE)
    try:
        f.validate("../etc/passwd"); ok = False
    except ValidationError:
        pass

    # geopoint
    g = Field("loc", FieldType.GEOPOINT)
    assert json.loads(g.validate({"lon": 88.4, "lat": 22.5}))["lat"] == 22.5

    # password min length
    p = Field("pw", FieldType.PASSWORD, options={"min": 8})
    assert p.validate("longenough") == "longenough"
    try:
        p.validate("short"); ok = False
    except ValidationError:
        pass

    # bad field name rejected
    try:
        Field("1bad", FieldType.TEXT); ok = False
    except ValidationError:
        pass

    print("✅ fields.py OK" if ok else "❌ FAILED")
