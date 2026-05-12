"""
HermesAdapter — DEPRECATED. Redirects to VectorCode MessagingHub.

Hermes dependency removed. VectorCode's MessagingHub is the replacement.
This file is kept only for backward-compat imports in any external callers.
All new code should import from:
  agents.districts.coding.vectorcode.comms.messenger import MessagingHub
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger
from agents.districts.coding.vectorcode.comms.messenger import MessagingHub

# Re-export MessagingHub as HermesAdapter for backward compat
HermesAdapter = MessagingHub

logger.debug("[VECTOR][hermes_adapter] Hermes dependency removed — using VectorCode MessagingHub")

if __name__ == "__main__":
    import asyncio
    adapter = HermesAdapter()
    status = adapter.get_comms_status()
    assert "urgent" in status
    print("hermes_adapter.py (redirected to MessagingHub) OK")
