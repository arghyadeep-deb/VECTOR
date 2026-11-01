"""VectorCode router — /vectorcode/launch."""


__all__ = [
    "launch_vectorcode",
    "LaunchRequest",
    "router",
    "vectorcode_status",
]

import subprocess
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel
from loguru import logger

router = APIRouter(prefix="/vectorcode", tags=["vectorcode"])

_VC_ROOT = Path(__file__).parent.parent.parent.parent / "vectorcode"
_VC_ENTRY = _VC_ROOT / "vector.py"


class LaunchRequest(BaseModel):
    mode: str = "run"


@router.post("/launch")
async def launch_vectorcode(body: LaunchRequest):
    """Open VectorCode in a new terminal window."""
    if not _VC_ENTRY.exists():
        logger.warning(f"[VECTOR][vectorcode] Entry not found: {_VC_ENTRY}")
        return {"status": "error", "detail": f"VectorCode entry not found at {_VC_ENTRY}"}

    mode = body.mode if body.mode in ("run", "auto", "hybrid") else "run"
    cmd_str = f'python "{_VC_ENTRY}" {mode}'

    try:
        # Windows: open a new cmd/wt window
        import platform
        if platform.system() == "Windows":
            # Try Windows Terminal first, fall back to cmd
            try:
                subprocess.Popen(
                    ["wt.exe", "--title", "VectorCode", "--", "cmd", "/k", cmd_str],
                    shell=False, cwd=str(_VC_ENTRY.parent.parent),
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            except FileNotFoundError:
                # wt.exe not found — use cmd.exe with explicit args (no shell=True)
                subprocess.Popen(
                    ["cmd.exe", "/c", "start", "VectorCode", "cmd", "/k", cmd_str],
                    shell=False, cwd=str(_VC_ENTRY.parent.parent),
                )
        else:
            # Linux/macOS
            subprocess.Popen(
                ["bash", "-c", f'python "{_VC_ENTRY}" {mode}'],
                cwd=str(_VC_ENTRY.parent.parent),
            )

        logger.info(f"[VECTOR][vectorcode] Launched in terminal — mode={mode}")
        return {"status": "ok", "mode": mode, "entry": str(_VC_ENTRY)}

    except Exception as e:
        logger.error(f"[VECTOR][vectorcode] Launch failed: {e}")
        return {"status": "error", "detail": str(e)}


@router.get("/status")
async def vectorcode_status():
    """Check if VectorCode entry point exists."""
    return {
        "available": _VC_ENTRY.exists(),
        "entry": str(_VC_ENTRY),
        "root": str(_VC_ROOT),
    }
