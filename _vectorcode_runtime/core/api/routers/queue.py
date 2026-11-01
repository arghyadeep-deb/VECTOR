"""Retry queue observability endpoints (Phase 1F)."""

__all__ = [
    "dlq_items",
    "replay_item",
    "retry_items",
    "retry_stats",
    "router",
]


from fastapi import APIRouter, HTTPException, Query
from loguru import logger

router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("/retry/stats")
async def retry_stats():
    """Pending + dead-letter queue sizes."""
    try:
        from core.queue.retry_queue import RetryQueue
        rq = RetryQueue.get()
        return {"pending": rq.size(), "dlq": rq.dlq_size()}
    except Exception as e:
        logger.warning(f"[VECTOR][api][queue] stats failed: {e}")
        return {"pending": 0, "dlq": 0, "error": str(e)}


@router.get("/retry/items")
async def retry_items(limit: int = Query(20, ge=1, le=100)):
    """List pending retry items."""
    try:
        from core.queue.retry_queue import RetryQueue
        rq = RetryQueue.get()
        conn, private = rq._conn()
        try:
            rows = conn.execute(
                "SELECT id, action_type, attempt, next_retry_at, error FROM retry_queue "
                "ORDER BY next_retry_at LIMIT ?", (limit,)
            ).fetchall()
        finally:
            if private:
                conn.close()
        return {"items": [dict(r) for r in rows], "count": len(rows)}
    except Exception as e:
        logger.warning(f"[VECTOR][api][queue] items failed: {e}")
        return {"items": [], "count": 0, "error": str(e)}


@router.get("/dlq/items")
async def dlq_items(limit: int = Query(20, ge=1, le=100)):
    """List dead-letter queue items."""
    try:
        from core.queue.retry_queue import RetryQueue
        rq = RetryQueue.get()
        conn, private = rq._conn()
        try:
            rows = conn.execute(
                "SELECT id, action_type, attempts, last_error, failed_at FROM dead_letter "
                "ORDER BY failed_at DESC LIMIT ?", (limit,)
            ).fetchall()
        finally:
            if private:
                conn.close()
        return {"items": [dict(r) for r in rows], "count": len(rows)}
    except Exception as e:
        logger.warning(f"[VECTOR][api][queue] dlq failed: {e}")
        return {"items": [], "count": 0, "error": str(e)}


@router.post("/retry/{item_id}/replay")
async def replay_item(item_id: int):
    """Force-replay a stuck retry item immediately."""
    try:
        from core.queue.retry_queue import RetryQueue, RetryItem
        from core.loop.permission_gateway import PermissionGateway, Action
        import json
        rq = RetryQueue.get()
        conn, private = rq._conn()
        try:
            row = conn.execute(
                "SELECT * FROM retry_queue WHERE id = ?", (item_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
            conn.execute("DELETE FROM retry_queue WHERE id = ?", (item_id,))
            conn.commit()
        finally:
            if private:
                conn.close()
        item = RetryItem(
            id=row["id"], action_type=row["action_type"],
            params=json.loads(row["params"]), proposed_by=row["proposed_by"],
            attempt=row["attempt"], next_retry_at=row["next_retry_at"],
            error=row["error"], created_at=row["created_at"],
        )
        gw = PermissionGateway()
        action = Action(action_type=item.action_type, params=item.params,
                        proposed_by=item.proposed_by)
        result = await gw.execute(action)
        return {"replayed": item_id, "status": result.level if hasattr(result, "level") else "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[VECTOR][api][queue] replay {item_id} failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
