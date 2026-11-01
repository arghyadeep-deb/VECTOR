"""MCP collection tools."""

from loguru import logger

from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.security import mcp_secure_call as _mcp_secure_call


def add_collections_tools(mcp) -> None:
    """Expose the VECTOR collections engine (PocketBase absorption) to MCP clients so
    VECTOR's own agents can store/query structured data. Reads + a gated create."""
    import json as _json
    try:
        from core.collections import CollectionEngine, FilterError, ValidationError
    except Exception as e:
        logger.warning(f"[VECTOR][mcp] collections tools unavailable: {e}")
        return

    _holder: dict = {}

    def _engine():
        if "eng" not in _holder:
            _holder["eng"] = CollectionEngine()   # shares the encrypted DB connection
        return _holder["eng"]

    @mcp.tool
    def collection_list() -> str:
        """List all VECTOR collections with their field summaries."""
        if not _mcp_secure_call("collection_list", "collections", {}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            out = [{"name": c.name, "type": c.type.value,
                    "fields": [{"name": f.name, "type": f.type.value} for f in c.fields]}
                   for c in _engine().list_collections()]
            return _safe_json({"collections": out})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def collection_query(name: str, filter: str = "", sort: str = "",
                         page: int = 1, per_page: int = 30) -> str:
        """Query records in a VECTOR collection. filter/sort use the PocketBase-style
        syntax, e.g. filter='views > 10 && title ~ "foo"', sort='-created'. The filter
        parser is parameterized — bad/unknown fields return an error, never raw SQL."""
        if not _mcp_secure_call("collection_query", "collections",
                                {"name": name, "filter": filter[:200]}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            return _safe_json(_engine().list_records(
                name, filter=filter or None, sort=sort or None,
                page=int(page), per_page=int(per_page)))
        except (FilterError, ValidationError) as e:
            return _safe_json({"error": str(e)})
        except Exception as e:
            return _safe_json({"error": str(e)})

    @mcp.tool
    def collection_record_create(name: str, data_json: str = "{}") -> str:
        """Create a record in a VECTOR collection. data_json is a JSON object string of
        the record fields. Returns the created record (passwords are never returned)."""
        if not _mcp_secure_call("collection_record_create", "collections", {"name": name}):
            return _safe_json({"error": "blocked by MCP security rate limit"})
        try:
            data = _json.loads(data_json) if data_json else {}
            if not isinstance(data, dict):
                return _safe_json({"error": "data_json must be a JSON object"})
            return _safe_json(_engine().create_record(name, data))
        except (FilterError, ValidationError) as e:
            return _safe_json({"error": str(e)})
        except Exception as e:
            return _safe_json({"error": str(e)})
