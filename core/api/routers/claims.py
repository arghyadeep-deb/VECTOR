"""Claims router — /claims."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/claims", tags=["claims"])


@router.get("")
async def list_claims():
    """List all active claims (stealable, active, blocked, in_review, etc.)."""
    try:
        from vectorcode.src.claims import _get_repo
        repo = _get_repo()
        claims = repo.find_all_active()
        return {
            "claims": [
                {
                    "id": c.id,
                    "issue_id": c.issue_id,
                    "title": c.issue.title if c.issue else c.issue_id,
                    "status": c.status.value,
                    "progress": c.progress,
                    "agent": c.claimant.name,
                    "priority": c.issue.priority.value if c.issue else "medium",
                }
                for c in claims
            ],
            "total": len(claims),
        }
    except ImportError as e:
        logger.warning(f"[VECTOR][api][claims] claims system unavailable: {e}")
        return {"claims": [], "total": 0}
    except Exception as e:
        logger.error(f"[VECTOR][api][claims] list failed: {e}")
        return {"claims": [], "total": 0, "error": str(e)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("OK")
