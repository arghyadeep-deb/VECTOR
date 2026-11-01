"""Network router — /network/peers."""

import sys

__all__ = [
    "network_peers",
    "router",
]


from fastapi import APIRouter
from loguru import logger

from core.api.schemas import NetworkPeersResponse

router = APIRouter(prefix="/network", tags=["network"])

@router.get("/peers", response_model=NetworkPeersResponse)
async def network_peers():
    try:
        from core.network.peer_discovery import PeerRegistry
        reg = PeerRegistry()
        peers = reg.all()
        peer_list = [
            {
                "node_id": p.node_id,
                "host": p.host,
                "port": p.port,
                "last_seen": p.last_seen,
            }
            for p in peers
        ]
        return NetworkPeersResponse(total_peers=len(peer_list), peers=peer_list)
    except Exception as e:
        logger.warning(f"[VECTOR][api][network] peers failed: {e}")
        return NetworkPeersResponse(total_peers=0, peers=[])

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ network.py OK")
