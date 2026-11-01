"""Collections router — PocketBase-compatible /api/collections + /api/files endpoints.

Exposes the VECTOR collections engine (core/collections) over HTTP: dynamic collection
management, generic rule-gated record CRUD, auth-with-password / token refresh, and file
upload/download with optional thumbnails. Record actions are gated by each collection's
access rules (RuleEngine); admin operations rely on the API-key middleware already in front
of the whole API.
"""

import sys

__all__ = ["router"]

from pathlib import Path

# Running this file directly puts its own directory (which contains email.py) on
# sys.path[0], shadowing the stdlib `email` module that FastAPI imports. Drop it so
# the stdlib resolves correctly; harmless when imported normally as a package module.
_HERE = Path(__file__).resolve().parent
sys.path = [p for p in sys.path if p and Path(p).resolve() != _HERE]

from fastapi import APIRouter, Query, HTTPException, Request, Body, UploadFile, File, Form
from fastapi.responses import Response, JSONResponse
from loguru import logger

from core.config import CONFIG
from core.collections import (
    Collection, CollectionEngine, AuthService, JWTManager,
    FileStorage, get_hooks, ValidationError, FilterError, AuthError, HookCancelled,
    safe_key,
)
from core.collections.storage import StorageError

router = APIRouter(prefix="/api", tags=["collections"])

# ── lazily-built singletons (share VECTOR's encrypted DB connection) ──────────
_engine: CollectionEngine | None = None
_auth: AuthService | None = None
_storage: FileStorage | None = None


def engine() -> CollectionEngine:
    global _engine
    if _engine is None:
        _engine = CollectionEngine(hooks=get_hooks())
    return _engine


def auth() -> AuthService:
    global _auth
    if _auth is None:
        jwtcfg = (CONFIG.get("collections", {}) or {}).get("jwt", {}) or {}
        _auth = AuthService(engine(), jwt=JWTManager(
            secret=jwtcfg.get("secret") or None,
            access_ttl=int(jwtcfg.get("access_ttl_sec", 900)),
            refresh_ttl=int(jwtcfg.get("refresh_ttl_sec", 1_209_600)),
        ))
    return _auth


def storage() -> FileStorage:
    global _storage
    if _storage is None:
        _storage = FileStorage()
    return _storage


def _identity(request: Request) -> dict | None:
    """Resolve a collections-JWT identity from the Authorization header, if present.
    Returns None when there is no valid collections token (anonymous request)."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    token = header[7:].strip()
    try:
        return auth().identity(token)
    except AuthError:
        return None


def _require_access(name: str, action: str, request: Request,
                    record: dict | None = None, data: dict | None = None):
    """Enforce a collection's access rule. rule None ⇒ admin-only (API-key middleware
    already gates the API, so allow); rule '' ⇒ public; expr ⇒ evaluate vs identity."""
    coll = engine().get_collection(name)
    if coll is None:
        raise HTTPException(status_code=404, detail=f"collection {name!r} not found")
    rule = coll.rule_for(action)
    if rule is None:
        return                       # admin-only — protected by API-key middleware
    identity = _identity(request)
    if not auth().rules.evaluate(rule, record=record, auth=identity, data=data):
        raise HTTPException(status_code=403, detail=f"not allowed to {action} {name}")


# ── collection management ─────────────────────────────────────────────────────
@router.get("/collections")
async def list_collections():
    try:
        return {"collections": [c.to_dict() for c in engine().list_collections()]}
    except Exception as e:
        logger.error(f"[VECTOR][api][collections] list defs failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collections")
async def create_collection(body: dict = Body(...)):
    try:
        coll = engine().create_collection(Collection.from_dict(body))
        return coll.to_dict()
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[VECTOR][api][collections] create def failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{name}")
async def get_collection(name: str):
    coll = engine().get_collection(name)
    if coll is None:
        raise HTTPException(status_code=404, detail=f"collection {name!r} not found")
    return coll.to_dict()


@router.delete("/collections/{name}")
async def delete_collection(name: str):
    if not engine().delete_collection(name):
        raise HTTPException(status_code=404, detail=f"collection {name!r} not found")
    return {"deleted": name}


# ── record CRUD ────────────────────────────────────────────────────────────────
@router.get("/collections/{name}/records")
async def list_records(name: str, request: Request,
                       filter: str | None = Query(None),
                       sort: str | None = Query(None),
                       page: int = Query(1, ge=1),
                       perPage: int = Query(30, ge=1, le=500),
                       expand: str | None = Query(None)):
    _require_access(name, "list", request)
    try:
        return engine().list_records(
            name, filter=filter, sort=sort, page=page, per_page=perPage,
            expand=[e.strip() for e in expand.split(",")] if expand else None,
        )
    except FilterError as e:
        raise HTTPException(status_code=400, detail=f"bad filter/sort: {e}")
    except ValidationError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/collections/{name}/records/{record_id}")
async def view_record(name: str, record_id: str, request: Request):
    rec = engine().get_record(name, record_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="record not found")
    _require_access(name, "view", request, record=rec)
    return rec


@router.post("/collections/{name}/records")
async def create_record(name: str, request: Request, body: dict = Body(...)):
    _require_access(name, "create", request, data=body)
    try:
        return engine().create_record(name, body)
    except HookCancelled as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/collections/{name}/records/{record_id}")
async def update_record(name: str, record_id: str, request: Request, body: dict = Body(...)):
    existing = engine().get_record(name, record_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="record not found")
    _require_access(name, "update", request, record=existing, data=body)
    try:
        return engine().update_record(name, record_id, body)
    except HookCancelled as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/collections/{name}/records/{record_id}")
async def delete_record(name: str, record_id: str, request: Request):
    existing = engine().get_record(name, record_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="record not found")
    _require_access(name, "delete", request, record=existing)
    try:
        engine().delete_record(name, record_id)
        return {"deleted": record_id}
    except HookCancelled as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── auth ──────────────────────────────────────────────────────────────────────
@router.post("/collections/{name}/auth-with-password")
async def auth_with_password(name: str, body: dict = Body(...)):
    try:
        return auth().authenticate(name, body.get("email", ""), body.get("password", ""))
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/collections/{name}/auth-refresh")
async def auth_refresh(name: str, body: dict = Body(...)):
    try:
        return auth().refresh(body.get("refresh_token", ""))
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/collections/{name}/auth-with-oauth2")
async def auth_with_oauth2(name: str, body: dict = Body(...)):
    # body: {"identity": {"email": ..., "name": ...}} — identity already resolved by the
    # existing core.engine.oauth flow (see AuthService.oauth_login docstring).
    try:
        return auth().oauth_login(name, body.get("identity", {}))
    except (AuthError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/collections/{name}/records-auth")
async def register_auth_record(name: str, body: dict = Body(...)):
    try:
        return auth().register(name, body)
    except (AuthError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── files ──────────────────────────────────────────────────────────────────────
@router.post("/files/{name}/{record_id}/{field}")
async def upload_file(name: str, record_id: str, field: str, request: Request,
                      file: UploadFile = File(...)):
    _require_access(name, "update", request)
    coll = engine().get_collection(name)
    if coll is None or coll.field(field) is None:
        raise HTTPException(status_code=404, detail="collection/field not found")
    data = await file.read()
    key = f"{name}/{record_id}/{field}/{safe_key(file.filename)}"
    try:
        meta = storage().put(key, data, content_type=file.content_type)
        engine().update_record(name, record_id, {field: file.filename})
        return {"key": meta["key"], "size": meta["size"], "url": storage().url(key)}
    except (StorageError, ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/files/{name}/{record_id}/{field}/{filename}")
async def download_file(name: str, record_id: str, field: str, filename: str,
                        thumb: str | None = Query(None)):
    key = f"{name}/{record_id}/{field}/{safe_key(filename)}"
    try:
        if thumb:
            w, _, h = thumb.partition("x")
            data = storage().thumbnail(key, int(w or 100), int(h or 100))
        else:
            data = storage().get(key)
        return Response(content=data, media_type="application/octet-stream")
    except StorageError as e:
        raise HTTPException(status_code=404, detail=str(e))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    # Smoke test: the router mounts and exposes the expected paths.
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    paths = {r.path for r in app.routes}
    expected = {
        "/api/collections",
        "/api/collections/{name}",
        "/api/collections/{name}/records",
        "/api/collections/{name}/records/{record_id}",
        "/api/collections/{name}/auth-with-password",
        "/api/collections/{name}/auth-with-oauth2",
        "/api/files/{name}/{record_id}/{field}",
    }
    ok = expected.issubset(paths)
    print("✅ collections router OK" if ok else f"❌ FAILED missing {expected - paths}")
