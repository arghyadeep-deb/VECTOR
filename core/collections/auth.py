"""Authentication + access rules for the VECTOR collections engine.

Python reimplementation of PocketBase's auth layer (apis/record_auth*.go, tools/auth/):
  - PasswordHasher: bcrypt (fallback PBKDF2-HMAC-SHA256) — never stores plaintext.
  - JWTManager: HS256 access + refresh tokens, secret from CONFIG/env.
  - RuleEngine: SAFE evaluator for PocketBase-style access rules
        ("@request.auth.id != ''", "owner = @request.auth.id", ...).
        Implemented as a tiny recursive-descent interpreter over a fixed grammar —
        it NEVER uses python eval()/exec().
  - AuthService: register / authenticate / refresh / oauth_login + authorize() against
        a collection's per-action rules. OAuth2 provider login delegates identity
        resolution to the existing core.engine.oauth flow (no web-flow duplication).
"""

from __future__ import annotations

import sys

__all__ = [
    "AuthError",
    "PasswordHasher",
    "JWTManager",
    "RuleEngine",
    "AuthService",
]


import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from loguru import logger
from core.config import CONFIG

from core.collections.schema import Collection, CollectionType


class AuthError(Exception):
    pass


# ── password hashing ─────────────────────────────────────────────────────────
class PasswordHasher:
    """bcrypt when available, else PBKDF2-HMAC-SHA256. Scheme is encoded in the hash."""

    _PBKDF2_ROUNDS = 240_000

    @classmethod
    def hash(cls, password: str) -> str:
        pw = password.encode("utf-8")
        try:
            import bcrypt
            return "bcrypt$" + bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")
        except ImportError:
            salt = secrets.token_bytes(16)
            dk = hashlib.pbkdf2_hmac("sha256", pw, salt, cls._PBKDF2_ROUNDS)
            return f"pbkdf2${cls._PBKDF2_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"

    @classmethod
    def verify(cls, password: str, hashed: str) -> bool:
        if not hashed:
            return False
        pw = password.encode("utf-8")
        if hashed.startswith("bcrypt$"):
            try:
                import bcrypt
                return bcrypt.checkpw(pw, hashed[len("bcrypt$"):].encode("utf-8"))
            except ImportError:
                logger.error("[VECTOR][collections] bcrypt hash present but bcrypt not installed")
                return False
        if hashed.startswith("pbkdf2$"):
            try:
                _, rounds, salt_b64, dk_b64 = hashed.split("$", 3)
                dk = hashlib.pbkdf2_hmac("sha256", pw, base64.b64decode(salt_b64), int(rounds))
                return hmac.compare_digest(dk, base64.b64decode(dk_b64))
            except Exception:
                return False
        return False


# ── JWT ────────────────────────────────────────────────────────────────────
class JWTManager:
    def __init__(self, secret: str | None = None,
                 access_ttl: int = 900, refresh_ttl: int = 1_209_600):
        self.secret = secret or self._resolve_secret()
        self.access_ttl = access_ttl
        self.refresh_ttl = refresh_ttl

    @staticmethod
    def _resolve_secret() -> str:
        cfg = (CONFIG.get("collections", {}) or {}).get("jwt", {}) or {}
        secret = cfg.get("secret") or os.environ.get("VECTOR_JWT_SECRET", "")
        if not secret:
            vector_home = CONFIG.get("vector_home") or os.environ.get("VECTOR_HOME") or ".vector"
            secret_path = os.path.join(str(vector_home), "collections_jwt_secret")
            try:
                os.makedirs(os.path.dirname(secret_path), exist_ok=True)
                if os.path.exists(secret_path):
                    with open(secret_path, "r", encoding="utf-8") as f:
                        secret = f.read().strip()
                if not secret:
                    secret = secrets.token_urlsafe(48)
                    with open(secret_path, "w", encoding="utf-8") as f:
                        f.write(secret)
                logger.warning(
                    "[VECTOR][collections] VECTOR_JWT_SECRET not set - using persistent local secret at {}",
                    secret_path,
                )
            except Exception as exc:
                logger.warning("[VECTOR][collections] local JWT secret file unavailable: {}", exc)
                secret = secrets.token_urlsafe(48)
        return secret

    def issue(self, claims: dict, ttl: int, token_type: str) -> str:
        import jwt
        now = datetime.now(timezone.utc)
        payload = {
            **claims,
            "type": token_type,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        }
        return jwt.encode(payload, self.secret, algorithm="HS256")

    def issue_pair(self, sub: str, collection: str, extra: dict | None = None) -> dict:
        base = {"sub": sub, "collection": collection, **(extra or {})}
        return {
            "token": self.issue(base, self.access_ttl, "access"),
            "refresh_token": self.issue({"sub": sub, "collection": collection},
                                        self.refresh_ttl, "refresh"),
        }

    def verify(self, token: str, expected_type: str | None = None) -> dict:
        import jwt
        try:
            claims = jwt.decode(token, self.secret, algorithms=["HS256"])
        except jwt.ExpiredSignatureError as e:
            raise AuthError("token expired") from e
        except jwt.InvalidTokenError as e:
            raise AuthError(f"invalid token: {e}") from e
        if expected_type and claims.get("type") != expected_type:
            raise AuthError(f"expected {expected_type} token, got {claims.get('type')}")
        return claims

    def refresh(self, refresh_token: str) -> dict:
        claims = self.verify(refresh_token, expected_type="refresh")
        return self.issue_pair(claims["sub"], claims["collection"])


# ── access-rule DSL (safe interpreter) ───────────────────────────────────────
_RULE_TOKEN_RE = re.compile(
    r"""\s*(
        \(|\)|&&|\|\||
        >=|<=|!=|!~|=|>|<|~|
        "(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|
        @request\.[A-Za-z0-9_.]+|
        [A-Za-z_][A-Za-z0-9_.]*|
        -?\d+(?:\.\d+)?
    )""",
    re.VERBOSE,
)
_RULE_OPS = {"=", "!=", ">", ">=", "<", "<=", "~", "!~"}


class RuleEngine:
    """Evaluates PocketBase-style access rules to a bool over a request context.

    Context:
      record — the record being accessed (dict) or None
      auth   — the authenticated identity (dict) or None
      data   — incoming request payload (dict) or None
    """

    def evaluate(self, rule: str | None, *, record=None, auth=None, data=None) -> bool:
        if rule is None:
            return False            # admin-only
        if rule.strip() == "":
            return True             # public
        tokens = self._tokenize(rule)
        ctx = {"record": record or {}, "auth": auth, "data": data or {}}
        parser = _RuleParser(tokens, ctx)
        result = parser.parse()
        return bool(result)

    @staticmethod
    def _tokenize(expr: str) -> list[str]:
        tokens, pos = [], 0
        while pos < len(expr):
            if expr[pos].isspace():
                pos += 1
                continue
            m = _RULE_TOKEN_RE.match(expr, pos)
            if not m or m.start(1) == -1:
                raise AuthError(f"bad rule near: {expr[pos:pos + 20]!r}")
            tokens.append(m.group(1))
            pos = m.end(1)
        return tokens


class _RuleParser:
    def __init__(self, tokens, ctx):
        self.toks = tokens
        self.i = 0
        self.ctx = ctx

    def _peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else None

    def _next(self):
        t = self._peek()
        self.i += 1
        return t

    def parse(self) -> bool:
        v = self._or()
        if self.i != len(self.toks):
            raise AuthError(f"trailing tokens in rule: {self.toks[self.i:]}")
        return v

    def _or(self) -> bool:
        left = self._and()
        while self._peek() == "||":
            self._next()
            right = self._and()
            left = left or right
        return left

    def _and(self) -> bool:
        left = self._cmp()
        while self._peek() == "&&":
            self._next()
            right = self._cmp()
            left = left and right
        return left

    def _cmp(self) -> bool:
        if self._peek() == "(":
            self._next()
            inner = self._or()
            if self._next() != ")":
                raise AuthError("missing ) in rule")
            return inner
        left = self._resolve(self._next())
        op = self._next()
        if op not in _RULE_OPS:
            raise AuthError(f"expected operator in rule, got {op!r}")
        right = self._resolve(self._next())
        return self._apply(op, left, right)

    def _resolve(self, tok):
        if tok is None:
            raise AuthError("unexpected end of rule")
        if (tok.startswith('"') and tok.endswith('"')) or (tok.startswith("'") and tok.endswith("'")):
            return tok[1:-1]
        if tok == "true":
            return True
        if tok == "false":
            return False
        if tok == "null":
            return None
        if re.fullmatch(r"-?\d+", tok):
            return int(tok)
        if re.fullmatch(r"-?\d+\.\d+", tok):
            return float(tok)
        if tok.startswith("@request.auth."):
            key = tok[len("@request.auth."):]
            if self.ctx["auth"] is None:
                return "" if key == "id" else None
            return self.ctx["auth"].get(key)
        if tok.startswith("@request.data."):
            return self.ctx["data"].get(tok[len("@request.data."):])
        if tok.startswith("@request."):
            return None
        # bare identifier → field on the record
        return self.ctx["record"].get(tok)

    @staticmethod
    def _apply(op, left, right):
        if op == "=":
            return left == right
        if op == "!=":
            return left != right
        if op == "~":
            return right is not None and str(right) in str(left or "")
        if op == "!~":
            return right is None or str(right) not in str(left or "")
        # ordering — None-safe
        if left is None or right is None:
            return False
        try:
            if op == ">":
                return left > right
            if op == ">=":
                return left >= right
            if op == "<":
                return left < right
            if op == "<=":
                return left <= right
        except TypeError:
            return False
        return False


# ── auth service (ties tokens + rules + password to collections) ─────────────
class AuthService:
    def __init__(self, engine, jwt: JWTManager | None = None):
        self.engine = engine
        self.jwt = jwt or JWTManager()
        self.rules = RuleEngine()

    def _auth_collection(self, name: str) -> Collection:
        coll = self.engine.get_collection(name)
        if coll is None:
            raise AuthError(f"collection {name!r} does not exist")
        if coll.type != CollectionType.AUTH:
            raise AuthError(f"collection {name!r} is not an auth collection")
        return coll

    def register(self, collection_name: str, data: dict) -> dict:
        coll = self._auth_collection(collection_name)
        payload = dict(data)
        if "password" not in payload:
            raise AuthError("password required")
        # validate plaintext length via the field, then store only the hash
        coll.field("password").validate(payload["password"])
        payload["password"] = PasswordHasher.hash(payload["password"])
        try:
            return self.engine.store.create(coll, payload)
        except Exception as e:
            # A duplicate email/username used to escape as the raw DB IntegrityError and surface as HTTP 500
            # (found by the live JWT smoke test, 2026-09-26). It is a client error, so report it as one.
            if "UNIQUE constraint" in str(e):
                raise AuthError("a record with that email or username already exists") from e
            raise

    def _find_auth(self, coll: Collection, email: str):
        """Return (record_without_password, password_hash) or (None, None)."""
        conn = self.engine.store.conn
        row = conn.execute(
            f'SELECT id, password FROM "{coll.table}" WHERE email = ?', (email,)
        ).fetchone()
        if not row:
            return None, None
        return self.engine.store.get(coll, row[0]), row[1]

    def authenticate(self, collection_name: str, email: str, password: str) -> dict:
        coll = self._auth_collection(collection_name)
        record, pw_hash = self._find_auth(coll, email)
        if record is None or not PasswordHasher.verify(password, pw_hash or ""):
            raise AuthError("invalid credentials")
        tokens = self.jwt.issue_pair(record["id"], collection_name,
                                     extra={"email": record.get("email")})
        return {**tokens, "record": record}

    def refresh(self, refresh_token: str) -> dict:
        return self.jwt.refresh(refresh_token)

    def identity(self, access_token: str) -> dict:
        """Verify an access token and return the auth identity claims."""
        claims = self.jwt.verify(access_token, expected_type="access")
        return {"id": claims["sub"], "collection": claims.get("collection"),
                "email": claims.get("email")}

    def oauth_login(self, collection_name: str, identity: dict) -> dict:
        """Find-or-create an auth record from an external OAuth identity, then issue
        tokens. `identity` is already resolved (email/name/provider/provider_id) by the
        existing core.engine.oauth flow — this does NOT re-run the web flow."""
        coll = self._auth_collection(collection_name)
        email = identity.get("email")
        if not email:
            raise AuthError("oauth identity has no email")
        record, _ = self._find_auth(coll, email)
        if record is None:
            payload = {"email": email, "verified": True,
                       "password": PasswordHasher.hash(secrets.token_urlsafe(24))}
            if coll.field("name") and identity.get("name"):
                payload["name"] = identity["name"]
            record = self.engine.store.create(coll, payload)
        tokens = self.jwt.issue_pair(record["id"], collection_name,
                                     extra={"email": email})
        return {**tokens, "record": record}

    def authorize(self, collection_name: str, action: str, *,
                  record=None, auth=None, data=None) -> bool:
        coll = self.engine.get_collection(collection_name)
        if coll is None:
            return False
        return self.rules.evaluate(coll.rule_for(action), record=record, auth=auth, data=data)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import sqlite3
    from core.collections.store import CollectionEngine
    ok = True

    # password hashing round-trip
    h = PasswordHasher.hash("hunter2pass")
    assert PasswordHasher.verify("hunter2pass", h)
    assert not PasswordHasher.verify("wrong", h)

    # JWT issue / verify / refresh / expiry
    jm = JWTManager(secret="x"*40, access_ttl=3600)
    pair = jm.issue_pair("rec1", "users", extra={"email": "a@b.com"})
    claims = jm.verify(pair["token"], expected_type="access")
    assert claims["sub"] == "rec1" and claims["email"] == "a@b.com"
    refreshed = jm.refresh(pair["refresh_token"])
    assert jm.verify(refreshed["token"], expected_type="access")["sub"] == "rec1"
    expired = JWTManager(secret="x"*40, access_ttl=-10).issue_pair("r", "users")
    try:
        jm.verify(expired["token"]); ok = False
    except AuthError:
        pass
    # wrong token type rejected
    try:
        jm.verify(pair["refresh_token"], expected_type="access"); ok = False
    except AuthError:
        pass

    # rule engine
    re_ = RuleEngine()
    assert re_.evaluate("") is True                       # public
    assert re_.evaluate(None) is False                    # admin-only
    assert re_.evaluate("@request.auth.id != ''", auth={"id": "u1"}) is True
    assert re_.evaluate("@request.auth.id != ''", auth=None) is False
    assert re_.evaluate("owner = @request.auth.id",
                        record={"owner": "u1"}, auth={"id": "u1"}) is True
    assert re_.evaluate("owner = @request.auth.id",
                        record={"owner": "u2"}, auth={"id": "u1"}) is False
    assert re_.evaluate('status = "public" || @request.auth.role = "admin"',
                        record={"status": "private"}, auth={"role": "admin"}) is True
    assert re_.evaluate("views >= 10", record={"views": 12}) is True
    assert re_.evaluate('title ~ "ell"', record={"title": "hello"}) is True
    # malformed rule rejected (no eval of arbitrary code)
    try:
        re_.evaluate("__import__('os').system('x')"); ok = False
    except AuthError:
        pass

    # AuthService end-to-end on a temp DB
    conn = sqlite3.connect(":memory:")
    eng = CollectionEngine(conn)
    eng.create_collection(Collection(name="users", type="auth",
                                     fields=[{"name": "name", "type": "text"}]))
    svc = AuthService(eng, jwt=JWTManager(secret="y"*40))
    user = svc.register("users", {"email": "a@b.com", "password": "longpass123", "name": "A"})
    assert "password" not in user
    res = svc.authenticate("users", "a@b.com", "longpass123")
    assert res["record"]["email"] == "a@b.com" and res["token"]
    try:
        svc.authenticate("users", "a@b.com", "nope"); ok = False
    except AuthError:
        pass
    # authorize against a per-collection rule
    eng2 = CollectionEngine(sqlite3.connect(":memory:"))
    eng2.create_collection(Collection(name="docs",
                                      fields=[{"name": "owner", "type": "text"}],
                                      update_rule="owner = @request.auth.id"))
    svc2 = AuthService(eng2)
    assert svc2.authorize("docs", "update", record={"owner": "u1"}, auth={"id": "u1"}) is True
    assert svc2.authorize("docs", "update", record={"owner": "u1"}, auth={"id": "u2"}) is False

    conn.close()
    print("✅ auth.py OK" if ok else "❌ FAILED")
