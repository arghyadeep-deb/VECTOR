"""
VECTOR Peer Discovery — finds other VECTOR nodes on the network.

Discovery methods:
  1. Static config  — hosts listed in VECTOR_PEERS env var or config file
  2. LAN broadcast  — UDP multicast on local network (auto-discover)
  3. Cloud registry — register with a central VECTOR cloud node (Phase 3)

Usage:
    discovery = PeerDiscovery(node_id="vector-legion", port=7790)
    await discovery.announce()                     # tell LAN we exist
    peers = await discovery.discover_lan()         # find peers on LAN
    for peer in peers:
        await node.register_with(peer.host, peer.port)
"""
from __future__ import annotations

__all__ = [
    "ANNOUNCE_TTL",
    "MULTICAST_GROUP",
    "MULTICAST_PORT",
    "PeerDiscovery",
    "PeerRegistry",
]


import asyncio
import json
import os
import secrets
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger
from core.network.ofp_protocol import PeerInfo, DEFAULT_PORT, PROTOCOL_VERSION

MULTICAST_GROUP = "239.255.42.99"
MULTICAST_PORT  = 7791
ANNOUNCE_TTL    = 60.0   # announce every 60s
_PEERS_FILE = Path.home() / ".vector_ca" / "network" / "peers.json"


class PeerRegistry:
    """Persistent registry of known VECTOR peers."""

    def __init__(self, peers_file: Path | None = None) -> None:
        self._file = peers_file or _PEERS_FILE
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._peers: dict[str, PeerInfo] = {}
        self._load()

    def add(self, peer: PeerInfo) -> None:
        peer.last_seen = time.time()
        self._peers[peer.node_id] = peer
        self._save()
        logger.info("[VECTOR][peer_registry] added peer: {} @ {}", peer.node_id, peer.address())

    def remove(self, node_id: str) -> None:
        self._peers.pop(node_id, None)
        self._save()

    def update_seen(self, node_id: str) -> None:
        if node_id in self._peers:
            self._peers[node_id].last_seen = time.time()
            self._save()

    def all(self) -> list[PeerInfo]:
        return list(self._peers.values())

    def live(self, max_age_secs: float = 300.0) -> list[PeerInfo]:
        cutoff = time.time() - max_age_secs
        return [p for p in self._peers.values() if p.last_seen >= cutoff]

    def get(self, node_id: str) -> PeerInfo | None:
        return self._peers.get(node_id)

    def count(self) -> int:
        return len(self._peers)

    def _save(self) -> None:
        data = {
            nid: {
                "node_id": p.node_id, "host": p.host, "port": p.port,
                "capabilities": p.capabilities, "version": p.version,
                "last_seen": p.last_seen, "hp": p.hp,
            }
            for nid, p in self._peers.items()
        }
        self._file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            for nid, d in data.items():
                self._peers[nid] = PeerInfo(**d)
        except Exception as e:
            logger.warning("[VECTOR][peer_registry] load failed: {}", e)


class PeerDiscovery:
    """
    Discovers other VECTOR nodes via multiple methods.

    Usage:
        disc = PeerDiscovery("vector-legion", host="192.168.1.10", port=7790)
        await disc.announce()                  # broadcast presence on LAN
        peers = await disc.discover_lan(5.0)   # listen for 5 seconds
        static = disc.discover_static()        # from env var
    """

    def __init__(
        self,
        node_id: str,
        host: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
        capabilities: list[str] | None = None,
    ) -> None:
        self.node_id = node_id
        self.host = host
        self.port = port
        self.capabilities = capabilities or []
        self.registry = PeerRegistry()

    # â”€â”€ Static discovery (from VECTOR_PEERS env var) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def discover_static(self) -> list[PeerInfo]:
        """
        Discover peers from VECTOR_PEERS environment variable.

        Format: VECTOR_PEERS=node1@192.168.1.2:7790,node2@10.0.0.5:7790
        """
        from core.config import CONFIG as _C
        peers_env = _C.get("peers", "")
        if not peers_env.strip():
            return []

        peers = []
        for entry in peers_env.split(","):
            entry = entry.strip()
            if not entry:
                continue
            try:
                if "@" in entry:
                    node_id, addr = entry.split("@", 1)
                else:
                    node_id = f"static-{secrets.token_hex(4)}"
                    addr = entry

                if ":" in addr:
                    host, port_str = addr.rsplit(":", 1)
                    port = int(port_str)
                else:
                    host, port = addr, DEFAULT_PORT

                peer = PeerInfo(node_id=node_id, host=host, port=port)
                self.registry.add(peer)
                peers.append(peer)
                logger.info("[VECTOR][discovery] static peer: {} @ {}:{}", node_id, host, port)
            except Exception as e:
                logger.warning("[VECTOR][discovery] bad peer entry '{}': {}", entry, e)

        return peers

    # â”€â”€ LAN multicast discovery â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def announce(self) -> None:
        """Broadcast this node's presence on the local network via UDP multicast."""
        announcement = json.dumps({
            "type": "vector_announce",
            "node_id": self.node_id,
            "host": self._public_ip(),
            "port": self.port,
            "capabilities": self.capabilities,
            "version": PROTOCOL_VERSION,
            "ts": time.time(),
        }).encode()

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
            sock.sendto(announcement, (MULTICAST_GROUP, MULTICAST_PORT))
            sock.close()
            logger.info(
                "[VECTOR][discovery] announced on LAN multicast {}:{}",
                MULTICAST_GROUP, MULTICAST_PORT,
            )
        except Exception as e:
            logger.warning("[VECTOR][discovery] announce failed: {}", e)

    async def discover_lan(self, listen_secs: float = 5.0) -> list[PeerInfo]:
        """
        Listen for peer announcements on LAN for `listen_secs` seconds.

        Returns list of discovered peers (also added to registry).
        """
        discovered: list[PeerInfo] = []

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", MULTICAST_PORT))

            # Join multicast group
            import struct
            group = socket.inet_aton(MULTICAST_GROUP)
            mreq = struct.pack("4sL", group, socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.setblocking(False)

            loop = asyncio.get_event_loop()
            deadline = loop.time() + listen_secs

            while loop.time() < deadline:
                remaining = deadline - loop.time()
                try:
                    data = await asyncio.wait_for(
                        loop.run_in_executor(None, lambda: sock.recv(4096)),
                        timeout=min(remaining, 1.0),
                    )
                    announcement = json.loads(data)
                    if (announcement.get("type") == "vector_announce" and
                            announcement.get("node_id") != self.node_id):
                        peer = PeerInfo(
                            node_id=announcement["node_id"],
                            host=announcement["host"],
                            port=announcement["port"],
                            capabilities=announcement.get("capabilities", []),
                            version=announcement.get("version", PROTOCOL_VERSION),
                        )
                        if peer.node_id not in {p.node_id for p in discovered}:
                            discovered.append(peer)
                            self.registry.add(peer)
                            logger.info(
                                "[VECTOR][discovery] found peer: {} @ {}",
                                peer.node_id, peer.address(),
                            )
                except (asyncio.TimeoutError, json.JSONDecodeError):
                    logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

            sock.close()
        except Exception as e:
            logger.warning("[VECTOR][discovery] LAN discovery failed: {}", e)

        return discovered

    async def announce_loop(self, interval: float = ANNOUNCE_TTL) -> None:
        """Continuously announce presence every `interval` seconds."""
        while True:
            await self.announce()
            await asyncio.sleep(interval)

    def _public_ip(self) -> str:
        if self.host not in ("0.0.0.0", ""):
            return self.host
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"


if __name__ == "__main__":
    import tempfile

    async def _test():
        with tempfile.TemporaryDirectory() as d:
            reg = PeerRegistry(peers_file=Path(d) / "peers.json")
            peer = PeerInfo(node_id="node-b", host="192.168.1.100", port=7790,
                            capabilities=["research"])
            reg.add(peer)
            assert reg.count() == 1
            assert reg.get("node-b") is not None

            # Reload from disk
            reg2 = PeerRegistry(peers_file=Path(d) / "peers.json")
            assert reg2.count() == 1

        # Static discovery from env
        import os
        os.environ["VECTOR_PEERS"] = "node-x@192.168.1.50:7790,node-y@10.0.0.5:7792"
        disc = PeerDiscovery("test-node", port=7790)
        peers = disc.discover_static()
        assert len(peers) == 2
        del os.environ["VECTOR_PEERS"]

        print("OK peer_discovery.py — registry persistence + static discovery verified")

    asyncio.run(_test())
