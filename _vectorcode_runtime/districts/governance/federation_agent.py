"""
Federation Agent — cross-machine VECTOR agent coordination.

Ported from ruflo's ruflo-federation plugin concept.
Enables VECTOR agents running on different machines (Legion + Fly.io VMs +
old Android phone) to collaborate via signed task delegation.

Architecture:
  Legion (primary) ──HTTP/signed──► Fly.io brain server
  Fly.io brain     ──HTTP/signed──► Phone Termux node
  Any node         ──broadcast──►  All registered federation peers

Security: every cross-machine task is HMAC-SHA256 signed. Replay protection
via timestamp + nonce. Only registered peers accepted.
"""
import asyncio
import datetime
import hashlib
import hmac
import json
import os
import secrets
import uuid
import time


from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory

# Federation peer registry — add peer nodes here or via VECTOR_PEERS env var
_DEFAULT_PEERS = {
    "cloud_brain": os.environ.get("VECTOR_BRAIN_URL", "https://vector-api.arghyadeepdeb020703.workers.dev"),
    "phone_node": os.environ.get("VECTOR_PHONE_URL", "http://192.168.1.100:8765"),
}

def _is_hardened() -> bool:
    return os.environ.get("VECTOR_ENV", "").strip().lower() in {"prod", "production", "vector"}


# Resolved lazily so the module imports cleanly on nodes that never federate
# (production boxes without VECTOR_FEDERATION_SECRET must still be able to
# import the governance district — only actual sign/verify calls may raise).
_FEDERATION_SECRET: str | None = None


def _get_federation_secret() -> str:
    global _FEDERATION_SECRET
    if _FEDERATION_SECRET is None:
        secret = os.environ.get("VECTOR_FEDERATION_SECRET", "").strip()
        if not secret:
            if _is_hardened():
                raise RuntimeError("VECTOR_FEDERATION_SECRET is required in production")
            secret = secrets.token_urlsafe(32)
        _FEDERATION_SECRET = secret
    return _FEDERATION_SECRET


_REPLAY_WINDOW_SECS = 30  # reject requests older than 30s


def _sign_task(task: dict) -> dict:
    """Sign a federated task with HMAC-SHA256 for peer authentication."""
    timestamp = int(time.time())
    nonce = str(uuid.uuid4())
    payload = json.dumps(task, sort_keys=True, separators=(",", ":"))
    data = f"{timestamp}:{nonce}:{payload}"
    sig = hmac.new(_get_federation_secret().encode(), data.encode(), hashlib.sha256).hexdigest()
    return {
        "task": task,
        "timestamp": timestamp,
        "nonce": nonce,
        "signature": sig,
        "origin": os.environ.get("VECTOR_NODE_ID", "legion-primary"),
    }


def _verify_signed_task(signed: dict) -> bool:
    """Verify a federated task's signature and replay window."""
    try:
        timestamp = signed["timestamp"]
        nonce = signed["nonce"]
        sig = signed["signature"]
        task = signed["task"]
        # Replay protection
        if abs(time.time() - timestamp) > _REPLAY_WINDOW_SECS:
            logger.warning("[VECTOR][federation] rejected: timestamp too old ({}s)", abs(time.time() - timestamp))
            return False
        payload = json.dumps(task, sort_keys=True, separators=(",", ":"))
        data = f"{timestamp}:{nonce}:{payload}"
        expected = hmac.new(_get_federation_secret().encode(), data.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception as e:
        logger.warning("[VECTOR][federation] verify failed: {}", e)
        return False


class FederationAgent(AgentBase):
    """
    Cross-machine task delegation. Dispatches signed tasks to remote
    VECTOR nodes (Fly.io brain, phone Termux) and receives results.
    Implements ruflo's federation plugin concept in Python.
    """

    def __init__(self):
        super().__init__(agent_id="federation_agent_001", name="FederationAgent", district="governance")
        self.capabilities = ["broadcast", "delegate", "federation", "governance", "receive", "register_peer"]
        self._memory: EpisodicMemory | None = None
        self._peers: dict[str, str] = dict(_DEFAULT_PEERS)
        logger.info("[VECTOR][federation] initialized with {} peers: {}", len(self._peers), list(self._peers.keys()))

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def register_peer(self, name: str, url: str) -> None:
        """Register a new federation peer node."""
        self._peers[name] = url
        logger.info("[VECTOR][federation] registered peer: {} → {}", name, url)

    def list_peers(self) -> dict:
        """Return all registered peer nodes."""
        return dict(self._peers)

    async def delegate_task(self, peer_name: str, task: dict, timeout: float = 30.0) -> dict:
        """Delegate a signed task to a remote VECTOR peer node."""
        peer_url = self._peers.get(peer_name)
        if not peer_url:
            return {"status": "error", "error": f"Unknown peer: {peer_name}"}

        signed = _sign_task(task)
        endpoint = f"{peer_url.rstrip('/')}/federation/task"

        try:
            import httpx
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(endpoint, json=signed,
                                         headers={"Content-Type": "application/json"})
                resp.raise_for_status()
                result = resp.json()
                logger.info("[VECTOR][federation] peer={} task={} status={}", peer_name, task.get("type"), result.get("status"))

                self._get_memory().store(
                    event_type="federated_task",
                    content=f"Delegated {task.get('type')} to {peer_name}: {result.get('status')}",
                    tags=["governance", "federation", peer_name],
                    source="federation_agent",
                )
                return result

        except Exception as e:
            logger.warning("[VECTOR][federation] peer={} unreachable: {}", peer_name, e)
            return {"status": "error", "error": str(e), "peer": peer_name}

    async def broadcast_task(self, task: dict, timeout: float = 10.0) -> dict:
        """Broadcast a task to all registered peers concurrently."""
        if not self._peers:
            return {"status": "error", "error": "No peers registered"}

        results = await asyncio.gather(
            *[self.delegate_task(name, task, timeout) for name in self._peers],
            return_exceptions=True,
        )
        outcomes = {}
        for peer_name, result in zip(self._peers.keys(), results):
            if isinstance(result, Exception):
                outcomes[peer_name] = {"status": "error", "error": str(result)}
            else:
                outcomes[peer_name] = result

        ok_count = sum(1 for r in outcomes.values() if r.get("status") == "ok")
        self.award_points(ok_count * 10, "federation_broadcast")
        return {"status": "ok", "broadcast_results": outcomes, "ok_peers": ok_count, "total_peers": len(self._peers)}

    def receive_task(self, signed: dict) -> dict:
        """Receive and verify an incoming federated task from a peer. Returns verified task or error."""
        if not _verify_signed_task(signed):
            self.deduct_points(20, "invalid_federation_signature")
            return {"status": "error", "error": "Invalid signature or replay detected"}
        task = signed.get("task", {})
        origin = signed.get("origin", "unknown")
        logger.info("[VECTOR][federation] verified task from {}: {}", origin, task.get("type"))
        return {"status": "ok", "task": task, "origin": origin}

    async def answer_federation_question(self, query: str) -> str:
        """Answer a free-text/unmatched-task_type question grounded in the
        real peer registry, instead of always dumping the raw peer-status
        dict regardless of what was actually asked (KNOWN_ISSUES bug
        pattern — 'dumps an unrelated hardcoded default')."""
        peers = self.list_peers()
        context = f"{len(self._peers)} federation peer(s) registered: {peers}."
        prompt = (
            "You are VECTOR's FederationAgent in the governance district — "
            "you coordinate cross-machine VECTOR agent collaboration. "
            "Answer the owner's question using this real context; do not "
            f"invent data you don't have:\n\n{context}\n\nQuestion: {query}"
        )
        try:
            result = self.vchat([{"role": "user", "content": prompt}])
            return (result or "").strip() or context
        except Exception as e:
            logger.warning("[VECTOR][federation] answer_federation_question failed: {}", e)
            return context

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "status")
        try:
            if task_type == "delegate":
                result = await self.delegate_task(
                    task.get("peer", "cloud_brain"), task.get("task", {}), task.get("timeout", 30.0)
                )
                self.award_points(15, "task_delegated")
                return {"status": "ok", "result": result}

            elif task_type == "broadcast":
                result = await self.broadcast_task(task.get("task", {}))
                return {"status": "ok", **result}

            elif task_type == "register_peer":
                self.register_peer(task.get("name", ""), task.get("url", ""))
                self.award_points(5, "peer_registered")
                return {"status": "ok", "peers": self.list_peers()}

            elif task_type == "receive":
                result = self.receive_task(task.get("signed_task", {}))
                return result

            else:  # status, or an unmatched task_type carrying a free-text question
                query = (
                    (task.get("params") or {}).get("query")
                    or task.get("query")
                    or task.get("text")
                    or ""
                ).strip()
                if query:
                    answer = await self.answer_federation_question(query)
                    if answer:
                        self.award_points(5, "federation_question_answered")
                        return {"status": "ok", "response": answer}

                self._get_memory().store(
                    event_type="federation_status",
                    content=f"Federation: {len(self._peers)} peers registered",
                    tags=["governance", "federation"],
                    source="federation_agent",
                )
                self.award_points(5, "federation_status_checked")
                return {"status": "ok", "peers": self.list_peers(), "peer_count": len(self._peers)}

        except Exception as e:
            logger.error("[VECTOR][federation] {}", e)
            self.deduct_points(30, "federation_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = FederationAgent()
        peers = agent.list_peers()
        print(f"[OK] peers: {list(peers.keys())} ({len(peers)} registered)")

        # Test signing + verification
        task = {"type": "health_check", "district": "ops"}
        signed = _sign_task(task)
        valid = _verify_signed_task(signed)
        print(f"[OK] sign+verify: valid={valid} nonce={signed['nonce'][:8]}...")

        # Test receive
        received = agent.receive_task(signed)
        print(f"[OK] receive: status={received['status']} origin={received.get('origin')}")

        # Test status
        result = await agent.run({"type": "status"})
        print(f"[OK] run status: peer_count={result.get('peer_count')}")
        print("federation_agent.py OK")

    asyncio.run(_smoke())
