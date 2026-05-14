"""
CommunicationsAdapter — canonical comms adapter.
Re-exports MessagingHub from VectorCode (vectorcode/src/).
"""
import sys
from pathlib import Path

_CODEBASE_ROOT = Path(__file__).parent.parent.parent.parent   # agents/../../../ = codebase root
_VC_SRC = _CODEBASE_ROOT / "vectorcode" / "src"

# Add codebase root so `from core.config import CONFIG` works
sys.path.insert(0, str(_CODEBASE_ROOT))
# Add vectorcode/src so `from comms.messenger import MessagingHub` works
if _VC_SRC.exists():
    sys.path.insert(0, str(_VC_SRC))

from loguru import logger

try:
    from comms.messenger import MessagingHub
    CommunicationsAdapter = MessagingHub
    logger.debug("[VECTOR][comms_adapter] Using VectorCode MessagingHub")
except ImportError as e:
    logger.error(f"[VECTOR][comms_adapter] MessagingHub unavailable: {e}")
    CommunicationsAdapter = None

if __name__ == "__main__":
    import asyncio
    adapter = CommunicationsAdapter()
    status = adapter.get_comms_status()
    assert "urgent" in status
    print("communications_adapter.py OK")
