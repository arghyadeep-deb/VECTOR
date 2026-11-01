"""
VECTOR OFP — Open Federation Protocol for multi-device agent networking.

Lets VECTOR instances on different machines (Legion Pro 5, cloud VM, phone)
talk to each other and delegate tasks across the network.

Protocol:
  - TCP/IP with asyncio (port 7790 default)
  - HMAC-SHA256 message authentication
  - Nonce-based replay protection
  - JSON messages framed with 4-byte length prefix

Message types:
  PING / PONG        — health check
  REGISTER           — announce this node to the network
  TASK               — send a task to a remote VECTOR node
  RESULT             — return task result
  STATUS             — request node status
  BROADCAST          — send to all known peers
  SUBSCRIBE          — subscribe to events from a peer

Ported from the agent OS agent OS P2P protocol.
"""
from __future__ import annotations

__all__ = [
    "DEFAULT_PORT",
    "MAX_MESSAGE_BYTES",
    "NONCE_TTL_SECS",
    "OFPMessage",
    "OFPMessageType",
    "OFPNode",
    "PeerInfo",
    "PROTOCOL_VERSION",
    "TaskHandler",
]


import asyncio
import hashlib
import hmac
import json
import math
import os
import secrets
import ssl
import struct
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Callable, Awaitable

from loguru import logger

DEFAULT_PORT = 7790
NONCE_TTL_SECS = 300        # replay window
MAX_MESSAGE_BYTES = 10 * 1024 * 1024   # 10MB max message
PROTOCOL_VERSION = "1.0"


class OFPMessageType(str, Enum):
    PING       = "ping"
    PONG       = "pong"
    REGISTER   = "register"
    DEREGISTER = "deregister"
    TASK       = "task"
    RESULT     = "result"
    STATUS     = "status"
    STATUS_RSP = "status_rsp"
    BROADCAST  = "broadcast"
    SUBSCRIBE  = "subscribe"
    EVENT      = "event"
    ERROR      = "error"


@dataclass
class PeerInfo:
    node_id: str
    host: str
    port: int
    capabilities: list[str] = field(default_factory=list)   # districts available
    version: str = PROTOCOL_VERSION
    last_seen: float = field(default_factory=time.time)
    hp: int = 500    # node health score

    def address(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass
class OFPMessage:
    """
    A single OFP protocol message.

    Fields:
        msg_id   : unique UUID per message
        type     : OFPMessageType
        sender   : node_id of sender
        payload  : message-specific data dict
        nonce    : random bytes (hex) for replay protection
        timestamp: unix timestamp
        hmac     : HMAC-SHA256 of canonical content (set by sign())
    """
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: OFPMessageType = OFPMessageType.PING
    sender: str = ""
    payload: dict = field(default_factory=dict)
    nonce: str = field(default_factory=lambda: secrets.token_hex(16))
    timestamp: float = field(default_factory=time.time)
    hmac_sig: str = ""

    def canonical(self) -> bytes:
        """Deterministic bytes for HMAC computation (excludes hmac_sig)."""
        d = {
            "msg_id": self.msg_id,
            "type": self.type.value,
            "sender": self.sender,
            "payload": self.payload,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
        }
        return json.dumps(d, sort_keys=True, separators=(",", ":")).encode()

    def sign(self, secret: bytes) -> "OFPMessage":
        self.hmac_sig = hmac.new(secret, self.canonical(), hashlib.sha256).hexdigest()
        return self

    def verify(self, secret: bytes) -> bool:
        expected = hmac.new(secret, self.canonical(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, self.hmac_sig)

    def is_expired(self, ttl: float = NONCE_TTL_SECS) -> bool:
        # Reject both stale messages and timestamps too far in the future.
        # The previous one-sided check accepted an arbitrarily future-dated
        # signed message indefinitely once the in-memory nonce cache was lost.
        if isinstance(self.timestamp, bool) or not isinstance(self.timestamp, (int, float)):
            return True
        return not math.isfinite(self.timestamp) or abs(time.time() - self.timestamp) > ttl

    def to_json(self) -> bytes:
        d = asdict(self)
        d["type"] = self.type.value
        return json.dumps(d, separators=(",", ":")).encode()

    @classmethod
    def from_json(cls, data: bytes) -> "OFPMessage":
        d = json.loads(data)
        d["type"] = OFPMessageType(d["type"])
        return cls(**d)


# â”€â”€ Frame encoding (4-byte length prefix + JSON body) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _encode_frame(msg: OFPMessage) -> bytes:
    body = msg.to_json()
    if len(body) > MAX_MESSAGE_BYTES:
        raise ValueError(f"Message too large: {len(body)} bytes")
    return struct.pack(">I", len(body)) + body


async def _read_frame(reader: asyncio.StreamReader) -> bytes:
    header = await asyncio.wait_for(reader.readexactly(4), timeout=10.0)
    length = struct.unpack(">I", header)[0]
    if length > MAX_MESSAGE_BYTES:
        raise ValueError(f"Frame too large: {length} bytes")
    return await asyncio.wait_for(reader.readexactly(length), timeout=30.0)


# â”€â”€ OFPNode â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

TaskHandler = Callable[[OFPMessage], Awaitable[dict]]


class OFPNode:
    """
    A VECTOR OFP network node.

    Each VECTOR instance runs one OFPNode. Nodes can:
      - Register with peers to announce themselves
      - Send tasks to remote VECTOR nodes (e.g. delegate research to cloud VM)
      - Receive tasks and execute them locally
      - Broadcast events to all peers (e.g. HP updates, memory sync)

    Usage:
        node = OFPNode(
            node_id="vector-legion",
            host="0.0.0.0",
            port=7790,
            secret=b"shared-secret",
            capabilities=["coding","research","governance"],
        )
        node.on_task(my_task_handler)
        await node.start()

        # Send task to remote node
        result = await node.send_task(
            peer_host="192.168.1.100",
            peer_port=7790,
            task_type="research",
            payload={"query": "latest LLM papers"},
        )
    """

    def __init__(
        self,
        node_id: str | None = None,
        host: str = "127.0.0.1",
        port: int = DEFAULT_PORT,
        secret: bytes | None = None,
        capabilities: list[str] | None = None,
    ) -> None:
        self.node_id = node_id or f"vector-{secrets.token_hex(4)}"
        self.host = host
        self.port = port
        from core.config import CONFIG as _C
        _secret_env = _C.get("ofp_secret", "")
        if secret:
            self._secret = secret
        elif _secret_env:
            self._secret = _secret_env.encode()
        else:
            if os.environ.get("VECTOR_ENV", "").strip().lower() in {"prod", "production", "vector"}:
                raise RuntimeError("VECTOR_OFP_SECRET is required in production")
            logger.warning(
                "[VECTOR][ofp] Using generated local-only secret — "
                "set VECTOR_OFP_SECRET env var for multi-node operation"
            )
            self._secret = secrets.token_bytes(32)
        self.capabilities = capabilities or []
        self._peers: dict[str, PeerInfo] = {}
        self._seen_nonces: set[str] = set()
        self._task_handler: TaskHandler | None = None
        self._tls_context: ssl.SSLContext | None = self._init_tls()
        self._server: asyncio.AbstractServer | None = None
        self._running = False

    # ── TLS ───────────────────────────────────────────────────────────────────

    def _init_tls(self) -> ssl.SSLContext | None:
        from core.config import CONFIG as _C
        cert_path = _C.get("ofp_cert", "")
        key_path = _C.get("ofp_key", "")
        if cert_path and key_path:
            ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ctx.load_cert_chain(cert_path, key_path)
            logger.info("[VECTOR][ofp] TLS enabled (cert={})", cert_path)
            return ctx
        logger.warning("[VECTOR][ofp] TLS not configured \u2014 traffic is PLAINTEXT")
        return None

    # ── Server ────────────────────────────────────────────────────────────────

    def on_task(self, handler: TaskHandler) -> None:
        """Register a handler for incoming task messages."""
        self._task_handler = handler

    async def start(self) -> None:
        """Start the OFP server listening for incoming connections."""
        self._server = await asyncio.start_server(
            self._handle_connection, self.host, self.port,
            ssl=self._tls_context,
        )
        self._running = True
        logger.info(
            "[VECTOR][ofp] node {} listening on {}:{}",
            self.node_id, self.host, self.port,
        )

    async def stop(self) -> None:
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        logger.info("[VECTOR][ofp] node {} stopped", self.node_id)

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer_addr = writer.get_extra_info("peername")
        try:
            raw = await _read_frame(reader)
            msg = OFPMessage.from_json(raw)

            if not self._verify_message(msg):
                await self._send_error(writer, msg.msg_id, "Authentication failed")
                return

            response = await self._dispatch(msg)
            if response:
                await self._write_frame(writer, response)
        except Exception as e:
            logger.warning("[VECTOR][ofp] connection error from {}: {}", peer_addr, e)
        finally:
            writer.close()

    async def _dispatch(self, msg: OFPMessage) -> OFPMessage | None:
        match msg.type:
            case OFPMessageType.PING:
                return self._make_message(OFPMessageType.PONG, {"ts": time.time()})

            case OFPMessageType.REGISTER:
                peer = PeerInfo(
                    node_id=msg.sender,
                    host=msg.payload.get("host", ""),
                    port=msg.payload.get("port", DEFAULT_PORT),
                    capabilities=msg.payload.get("capabilities", []),
                    version=msg.payload.get("version", PROTOCOL_VERSION),
                )
                self._peers[msg.sender] = peer
                logger.info("[VECTOR][ofp] peer registered: {} @ {}",
                            msg.sender, peer.address())
                return self._make_message(OFPMessageType.PONG, {"registered": True})

            case OFPMessageType.STATUS:
                return self._make_message(OFPMessageType.STATUS_RSP, {
                    "node_id": self.node_id,
                    "capabilities": self.capabilities,
                    "peer_count": len(self._peers),
                    "uptime": time.time(),
                    "version": PROTOCOL_VERSION,
                })

            case OFPMessageType.TASK:
                if self._task_handler:
                    try:
                        result = await self._task_handler(msg)
                        return self._make_message(OFPMessageType.RESULT, {
                            "task_id": msg.payload.get("task_id"),
                            "result": result,
                            "status": "ok",
                        })
                    except Exception as e:
                        return self._make_message(OFPMessageType.ERROR, {
                            "task_id": msg.payload.get("task_id"),
                            "error": str(e),
                        })
                return self._make_message(OFPMessageType.ERROR, {"error": "No task handler"})

            case OFPMessageType.DEREGISTER:
                self._peers.pop(msg.sender, None)
                logger.info("[VECTOR][ofp] peer deregistered: {}", msg.sender)
                return None

            case _:
                logger.debug("[VECTOR][ofp] unhandled message type: {}", msg.type)
                return None

    # â”€â”€ Client methods â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def send_task(
        self,
        peer_host: str,
        peer_port: int,
        task_type: str,
        payload: dict,
        timeout: float = 120.0,
    ) -> dict:
        """
        Send a task to a remote VECTOR node and await the result.

        Args:
            peer_host: IP/hostname of remote VECTOR node
            peer_port: OFP port (default 7790)
            task_type: Task type string (e.g. "research", "code")
            payload:   Task data
            timeout:   Max wait seconds

        Returns:
            Result dict from remote node
        """
        task_id = str(uuid.uuid4())
        msg = self._make_message(OFPMessageType.TASK, {
            "task_id": task_id,
            "task_type": task_type,
            **payload,
        })

        response = await self._send_and_receive(peer_host, peer_port, msg, timeout)

        if response.type == OFPMessageType.ERROR:
            raise RuntimeError(f"Remote task failed: {response.payload.get('error')}")

        return response.payload.get("result", {})

    async def register_with(self, peer_host: str, peer_port: int) -> bool:
        """Announce this node to a peer."""
        msg = self._make_message(OFPMessageType.REGISTER, {
            "host": self.host if self.host != "0.0.0.0" else _local_ip(),
            "port": self.port,
            "capabilities": self.capabilities,
            "version": PROTOCOL_VERSION,
        })
        try:
            response = await self._send_and_receive(peer_host, peer_port, msg, timeout=10.0)
            ok = response.type == OFPMessageType.PONG
            if ok:
                logger.info("[VECTOR][ofp] registered with {}:{}", peer_host, peer_port)
            return ok
        except Exception as e:
            logger.warning("[VECTOR][ofp] registration failed {}:{} — {}", peer_host, peer_port, e)
            return False

    async def ping(self, peer_host: str, peer_port: int) -> float | None:
        """Ping a peer. Returns RTT in ms or None if unreachable."""
        msg = self._make_message(OFPMessageType.PING, {})
        t0 = time.monotonic()
        try:
            await self._send_and_receive(peer_host, peer_port, msg, timeout=5.0)
            return (time.monotonic() - t0) * 1000
        except Exception:
            return None

    async def broadcast(self, event_type: str, data: dict) -> int:
        """Broadcast an event to all known peers. Returns success count."""
        msg = self._make_message(OFPMessageType.BROADCAST, {
            "event_type": event_type,
            "data": data,
        })
        success = 0
        for peer in list(self._peers.values()):
            try:
                await self._send_only(peer.host, peer.port, msg)
                success += 1
            except Exception:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        return success

    # â”€â”€ Internal helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _make_message(self, msg_type: OFPMessageType, payload: dict) -> OFPMessage:
        msg = OFPMessage(type=msg_type, sender=self.node_id, payload=payload)
        return msg.sign(self._secret)

    def _verify_message(self, msg: OFPMessage) -> bool:
        if msg.is_expired():
            logger.warning("[VECTOR][ofp] expired message from {}", msg.sender)
            return False
        if msg.nonce in self._seen_nonces:
            logger.warning("[VECTOR][ofp] replay attack detected from {}", msg.sender)
            return False
        if not msg.verify(self._secret):
            logger.warning("[VECTOR][ofp] HMAC verification failed from {}", msg.sender)
            return False
        self._seen_nonces.add(msg.nonce)
        # Prune old nonces
        if len(self._seen_nonces) > 10_000:
            self._seen_nonces = set(list(self._seen_nonces)[-5_000:])
        return True

    async def _send_and_receive(
        self,
        host: str, port: int,
        msg: OFPMessage,
        timeout: float,
    ) -> OFPMessage:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=self._tls_context), timeout=timeout
        )
        try:
            await self._write_frame(writer, msg)
            raw = await asyncio.wait_for(_read_frame(reader), timeout=timeout)
            response = OFPMessage.from_json(raw)
            if not self._verify_message(response):
                raise RuntimeError("Response authentication failed")
            return response
        finally:
            writer.close()

    async def _send_only(self, host: str, port: int, msg: OFPMessage) -> None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=self._tls_context), timeout=5.0
        )
        try:
            await self._write_frame(writer, msg)
        finally:
            writer.close()

    async def _write_frame(
        self, writer: asyncio.StreamWriter, msg: OFPMessage
    ) -> None:
        writer.write(_encode_frame(msg))
        await writer.drain()

    async def _send_error(
        self, writer: asyncio.StreamWriter, msg_id: str, reason: str
    ) -> None:
        err = self._make_message(OFPMessageType.ERROR, {"msg_id": msg_id, "reason": reason})
        await self._write_frame(writer, err)

    @property
    def peers(self) -> dict[str, PeerInfo]:
        return dict(self._peers)

    @property
    def peer_count(self) -> int:
        return len(self._peers)


def _local_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    import asyncio

    async def _test():
        # Test message signing and verification
        secret = b"test-secret-key"
        msg = OFPMessage(type=OFPMessageType.PING, sender="node-a")
        msg.sign(secret)
        assert msg.verify(secret), "HMAC verification failed"
        assert not msg.verify(b"wrong-secret"), "Should fail with wrong secret"

        # Test replay protection
        msg2 = OFPMessage(type=OFPMessageType.PING, sender="node-a",
                          timestamp=time.time() - NONCE_TTL_SECS - 1)
        msg2.sign(secret)
        assert msg2.is_expired(), "Old message should be expired"

        # Test frame encoding
        encoded = _encode_frame(msg)
        assert len(encoded) > 4

        # Test node creation
        node = OFPNode(node_id="test-node", port=17790, secret=secret,
                       capabilities=["coding","research"])
        assert node.node_id == "test-node"
        assert node.peer_count == 0

        # Test two-node local communication
        results = []
        async def handler(m: OFPMessage) -> dict:
            results.append(m.payload.get("task_type"))
            return {"status": "done", "from": "node-b"}

        node_a = OFPNode("node-a", port=17791, secret=secret)
        node_b = OFPNode("node-b", port=17792, secret=secret)
        node_b.on_task(handler)

        await node_a.start()
        await node_b.start()

        rtt = await node_a.ping("127.0.0.1", 17792)
        assert rtt is not None and rtt > 0

        ok = await node_a.register_with("127.0.0.1", 17792)
        assert ok

        result = await node_a.send_task("127.0.0.1", 17792, "research",
                                        {"query": "test"}, timeout=10.0)
        assert result.get("status") == "done"
        assert results == ["research"]

        await node_a.stop()
        await node_b.stop()

        print("OK ofp_protocol.py — HMAC auth, replay protection, task delegation verified")

    asyncio.run(_test())
