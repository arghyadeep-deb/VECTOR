"""Governed agent-to-agent (A2A) bus for the REAL city registry.

Why this exists (2026-09-26): the only internal agent-to-agent call in VECTOR was AgentBase.request_agent_help(), used in two places,
and it called `target.run(task)` directly -- around the Governor and the PermissionGateway. The external /a2a/* HTTP surface reads a
different registry (wrapper agents with no behaviour). Neither is a communication layer for the 39 districts. This module is.

Rules (the point of the design):
  * Nothing here calls `agent.run()`. Every delivery goes through `Governor.dispatch()`, which already enforces the tier gate
    (YELLOW/RED need a real PermissionGateway approval), the unknown-task-type gate, timeouts, HP accounting and event logging.
  * Authority is never inherited from another agent. The gateway classifies the ACTION, not the agent, so asking a peer to do
    something cannot make an action easier than asking directly. Phase 1 carries information/analysis requests only: a YELLOW/RED
    task type is answered `requires_approval` (or, when the caller opts in with `escalate=True`, is handed to
    PermissionGateway.execute() exactly like any other proposed action, from the untrusted proposer id "a2a_agent").
  * Bounded by construction: depth limit, cycle detection (an agent already in the chain cannot be asked again), a message budget per
    conversation, a per-sender rate limit, a cap on requests in flight, a timeout on every delivery, and a size cap on payloads. Nested
    requests made from inside an agent's own run() pick up the current chain automatically (a ContextVar), so agents cannot forget to
    propagate depth.
  * Every message is audited (in-memory ring + episodic memory) so the HUD can show conversations and later phases can attribute credit.
  * `ping`/`describe` are answered by the bus itself from the registry, so every one of the 230 agents is reachable for discovery
    without any per-agent code.
"""
from __future__ import annotations

__all__ = ["A2ABus", "A2AReply", "A2AMessage", "get_bus", "describe_agent"]

import asyncio
import contextvars
import json
import math
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

from loguru import logger

# Defaults; overridable through CONFIG["a2a"] without code changes.
_DEFAULTS = {
    "max_depth": 3,               # requests nested inside requests
    "max_messages_per_conversation": 12,
    "rate_per_minute": 20,        # per sender
    "max_inflight": 8,
    "default_timeout_sec": 30.0,
    "max_timeout_sec": 60.0,
    "max_payload_chars": 20_000,
    "conversation_ttl_sec": 600,
}


def _cfg(key: str):
    try:
        from core.config import CONFIG
        return (CONFIG.get("a2a", {}) or {}).get(key, _DEFAULTS[key])
    except Exception:
        return _DEFAULTS[key]


@dataclass
class A2AMessage:
    id: str
    correlation_id: str
    sender_id: str
    sender_name: str
    sender_district: str
    task_type: str
    params: dict
    mode: str = "ask"                       # ask | tell | delegate | ping
    recipient: str | None = None            # agent name/id, or "district:<name>"
    depth: int = 0
    path: tuple = ()                        # agent ids already in this conversation chain
    origin: str = "agent"                   # who started the root request: agent | owner_api | loop | external
    created_at: float = field(default_factory=time.time)


@dataclass
class A2AReply:
    """Result of a request. `delivered` means an agent actually ran it; `ok` additionally means it did not report failure."""
    message_id: str
    correlation_id: str
    status: str                             # the agent's own status when delivered; otherwise a bus status (refused, timeout, ...)
    delivered: bool = False
    result: dict = field(default_factory=dict)
    responder: str = ""
    responder_district: str = ""
    refused: str = ""                       # why the bus did not deliver (empty when delivered)
    error: str = ""
    elapsed_ms: int = 0

    @property
    def ok(self) -> bool:
        if not self.delivered:
            return False
        try:
            from core.runtime.executor import TERMINAL_STATUSES, assess_payload_failure
            if str(self.status).lower() in TERMINAL_STATUSES:
                return False
            return assess_payload_failure(self.result) is None
        except Exception:
            return str(self.status).lower() == "ok"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ok"] = self.ok
        return d


# The conversation chain the currently running request belongs to. Set while a delivery runs so that any request the receiving
# agent makes from inside its own run() inherits depth / path / correlation without the agent doing anything.
_CHAIN: contextvars.ContextVar[dict | None] = contextvars.ContextVar("a2a_chain", default=None)


def _hp_status(hp: Any) -> str | None:
    """The HP tier label (same bands as AgentBase.get_status), computed from the number so no agent code runs."""
    try:
        hp = float(hp)
    except (TypeError, ValueError):
        return None
    for floor, label in ((800, "elite"), (600, "strong"), (400, "healthy"), (200, "weakened"), (1, "critical")):
        if hp >= floor:
            return label
    return "dead"


def describe_agent(agent: Any) -> dict:
    """What an agent tells a peer about itself. Built from the registry, so every agent can answer a ping."""
    return {
        "id": getattr(agent, "id", ""),
        "name": getattr(agent, "name", ""),
        "district": getattr(agent, "district", ""),
        "capabilities": sorted({str(c) for c in (getattr(agent, "capabilities", None) or [])}),
        "generation": getattr(agent, "generation", None),
        "health_points": getattr(agent, "health_points", None),
        # NOT agent.get_status(): many agents override that name for their own purposes (GitBot's returns the repository status and
        # runs git, an HP award and all), so a directory listing would trigger real work. Use the base HP-tier implementation.
        "status": _hp_status(getattr(agent, "health_points", None)),
        "alive": bool(getattr(agent, "is_alive", True)),
    }


class A2ABus:
    def __init__(self, registry: Any | None = None) -> None:
        self._registry = registry
        self._log: deque[dict] = deque(maxlen=500)
        self._inbox: dict[str, deque] = {}
        self._rate: dict[str, deque] = {}
        self._conversations: dict[str, list] = {}     # correlation_id -> [count, first_ts]
        self._inflight = 0
        self._tasks: set[asyncio.Task] = set()
        self.stats = {"sent": 0, "delivered": 0, "refused": 0, "failed": 0}

    # ── registry helpers ────────────────────────────────────────────────────────────────────────────────────────────────
    def _reg(self):
        if self._registry is not None:
            return self._registry
        from core.city.agent_registry import get_registry
        return get_registry()

    def agents(self) -> list:
        try:
            return [a for a in self._reg().get_all_agents() if getattr(a, "is_alive", True)]
        except Exception:
            return []

    def resolve(self, ref: Any) -> Any | None:
        """An agent object, id or (case-insensitive) name -> the live agent, else None."""
        if ref is None:
            return None
        if not isinstance(ref, str):
            return ref if hasattr(ref, "id") else None
        want = ref.strip().lower()
        for a in self.agents():
            if str(getattr(a, "id", "")).lower() == want or str(getattr(a, "name", "")).lower() == want:
                return a
        return None

    def find(self, capability: str, district: str | None = None) -> list:
        """Live agents that declare `capability` (case-insensitive), best first."""
        cap = (capability or "").strip().lower()
        out = []
        for a in self.agents():
            caps = {str(c).lower() for c in (getattr(a, "capabilities", None) or [])}
            if cap in caps and (district is None or getattr(a, "district", "") == district):
                out.append(a)
        return sorted(out, key=lambda a: getattr(a, "health_points", 0), reverse=True)

    def directory(self) -> dict[str, list[dict]]:
        """district -> [describe(agent)], for discovery (the HUD atlas and agents choosing whom to ask)."""
        out: dict[str, list[dict]] = {}
        for a in self.agents():
            out.setdefault(getattr(a, "district", "unknown"), []).append(describe_agent(a))
        return out

    async def ping_all(self, sender: Any = "conformance") -> dict:
        """Ping every live agent over the bus (the same path a peer would use) and report who answered. This is the conformance
        check behind "A2A is available in every district": each answer must name the agent that was asked."""
        answered, failed = 0, []
        per_district: dict[str, dict] = {}
        for a in self.agents():
            r = await self.request(sender, "ping", {}, to=getattr(a, "id", None))
            d = getattr(a, "district", "unknown")
            slot = per_district.setdefault(d, {"agents": 0, "answered": 0, "with_capabilities": 0})
            slot["agents"] += 1
            if r.ok and r.result.get("id") == getattr(a, "id", None):
                answered += 1
                slot["answered"] += 1
                slot["with_capabilities"] += 1 if r.result.get("capabilities") else 0
            else:
                failed.append({"agent": getattr(a, "name", "?"), "district": d, "why": r.refused or r.error or r.status})
        return {
            "agents": answered + len(failed), "answered": answered, "failed": failed, "districts": per_district,
            "districts_unreachable": sorted(d for d, v in per_district.items() if v["answered"] == 0),
            "districts_without_capabilities": sorted(d for d, v in per_district.items() if v["with_capabilities"] == 0),
        }

    # ── audit ───────────────────────────────────────────────────────────────────────────────────────────────────────────
    def _audit(self, msg: A2AMessage, reply: A2AReply, persist: bool = True) -> None:
        entry = {
            "ts": time.time(), "message_id": msg.id, "correlation_id": msg.correlation_id, "mode": msg.mode,
            "from": msg.sender_name, "from_district": msg.sender_district, "to": reply.responder or msg.recipient or "",
            "to_district": reply.responder_district, "task_type": msg.task_type, "depth": msg.depth, "origin": msg.origin,
            "status": reply.status, "delivered": reply.delivered, "refused": reply.refused, "elapsed_ms": reply.elapsed_ms,
        }
        self._log.append(entry)
        if not persist:
            return
        try:
            from core.memory.episodic import EpisodicMemory
            EpisodicMemory().store(
                event_type="a2a_message",
                content=(f"{msg.sender_name} -> {entry['to'] or '?'} [{msg.task_type}] {reply.status}"
                         + (f" ({reply.refused})" if reply.refused else "")),
                tags=["a2a", msg.sender_district or "external", reply.responder_district or "none"],
                source="a2a_bus",
            )
        except Exception as e:  # audit storage must never break delivery
            logger.debug("[VECTOR][a2a] episodic audit skipped: {}", e)

    def recent(self, limit: int = 50) -> list[dict]:
        return list(self._log)[-limit:][::-1]

    def conversation(self, correlation_id: str) -> list[dict]:
        return [e for e in self._log if e["correlation_id"] == correlation_id]

    def inbox(self, agent_id: str, limit: int = 20) -> list[dict]:
        """Replies to fire-and-forget `tell`s, for the agent that sent them."""
        return list(self._inbox.get(agent_id, []))[-limit:]

    # ── guards ──────────────────────────────────────────────────────────────────────────────────────────────────────────
    def _rate_limited(self, sender_id: str) -> bool:
        now = time.time()
        q = self._rate.setdefault(sender_id, deque())
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= int(_cfg("rate_per_minute")):
            return True
        q.append(now)
        return False

    def _over_budget(self, correlation_id: str) -> bool:
        now = time.time()
        ttl = float(_cfg("conversation_ttl_sec"))
        for cid in [c for c, (_, ts) in self._conversations.items() if now - ts > ttl]:
            self._conversations.pop(cid, None)
        rec = self._conversations.setdefault(correlation_id, [0, now])
        rec[0] += 1
        return rec[0] > int(_cfg("max_messages_per_conversation"))

    @staticmethod
    def _payload_text(params: dict) -> str:
        parts: list[str] = []

        def walk(v: Any, depth: int = 0) -> None:
            if depth > 4:
                return
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, dict):
                for x in v.values():
                    walk(x, depth + 1)
            elif isinstance(v, (list, tuple)):
                for x in v:
                    walk(x, depth + 1)

        walk(params)
        return "\n".join(parts)

    @staticmethod
    def _payload_size(params: dict, limit: int) -> int:
        """Serialized payload size, including keys, numbers and containers; returns over-limit on malformed/cyclic input."""
        try:
            rendered = json.dumps(params, ensure_ascii=False, separators=(",", ":"), default=str)
            return len(rendered)
        except (TypeError, ValueError, RecursionError):
            return limit + 1

    # ── the request path ────────────────────────────────────────────────────────────────────────────────────────────────
    def _sender_identity(self, sender: Any) -> tuple[str, str, str]:
        agent = self.resolve(sender) if not isinstance(sender, str) else self.resolve(sender)
        if agent is not None:
            return str(getattr(agent, "id", "")), str(getattr(agent, "name", "")), str(getattr(agent, "district", ""))
        label = str(sender or "unknown")[:60]
        return label, label, "external"

    def _refuse(self, msg: A2AMessage, why: str, status: str = "refused", started: float | None = None) -> A2AReply:
        self.stats["refused"] += 1
        reply = A2AReply(message_id=msg.id, correlation_id=msg.correlation_id, status=status, delivered=False, refused=why,
                         elapsed_ms=int((time.time() - (started or time.time())) * 1000))
        self._audit(msg, reply)
        logger.info("[VECTOR][a2a] {} -> {} [{}] refused: {}", msg.sender_name, msg.recipient or "?", msg.task_type, why)
        return reply

    async def request(
        self,
        sender: Any,
        task_type: str,
        params: dict | None = None,
        *,
        to: Any = None,
        capability: str | None = None,
        mode: str = "ask",
        timeout: float | None = None,
        origin: str | None = None,
        escalate: bool = False,
        verify: Any = None,
        no_reward: bool = False,
    ) -> A2AReply:
        """Send one request and wait for the answer. Never raises: every failure is a reply with a status and a reason.

        `verify` is an optional callable the ASKER supplies to check the answer independently (result dict -> bool). Only a reply that
        passes it earns the helper collaboration XP (reduced weight, capped per pair per day): the exchange itself earns nothing, so
        two agents cannot farm each other by trading requests. `no_reward` runs the request without moving HP or writing a ledger row
        (used for practice drills, which the work board records itself)."""
        started = time.time()
        sid, sname, sdistrict = self._sender_identity(sender)
        chain = _CHAIN.get()
        correlation = (chain or {}).get("correlation_id") or f"conv_{uuid.uuid4().hex[:12]}"
        depth = ((chain or {}).get("depth", -1) + 1) if chain else 0
        path = tuple((chain or {}).get("path", ())) + ((sid,) if sid not in (chain or {}).get("path", ()) else ())
        msg = A2AMessage(
            id=f"a2a_{uuid.uuid4().hex[:12]}", correlation_id=correlation, sender_id=sid, sender_name=sname,
            sender_district=sdistrict, task_type=str(task_type or "").strip(), params=params if isinstance(params, dict) else {},
            mode=mode, recipient=(to if isinstance(to, str) else getattr(to, "name", None)), depth=depth, path=path,
            origin=origin or (chain or {}).get("origin") or ("agent" if self.resolve(sender) is not None else "external"),
        )
        self.stats["sent"] += 1

        # --- validation ---
        if not msg.task_type or len(msg.task_type) > 80:
            return self._refuse(msg, "task_type missing or too long", started=started)
        payload_limit = int(_cfg("max_payload_chars"))
        if self._payload_size(msg.params, payload_limit) > payload_limit:
            return self._refuse(msg, f"payload larger than {payload_limit} characters", started=started)
        # --- ping/describe: answered from the registry, no agent code runs; not rate-limited (a registry read, not work) ---
        if msg.task_type in ("ping", "describe"):
            target = self.resolve(to) if to is not None and not str(to).startswith("district:") else None
            if target is None:
                return self._refuse(msg, f"no live agent named {to!r}", "unavailable", started)
            msg.mode = "ping"
            reply = A2AReply(message_id=msg.id, correlation_id=correlation, status="ok", delivered=True,
                             result=describe_agent(target), responder=describe_agent(target)["name"],
                             responder_district=describe_agent(target)["district"], elapsed_ms=int((time.time() - started) * 1000))
            self.stats["delivered"] += 1
            self._audit(msg, reply, persist=False)   # discovery is cheap and frequent: ring buffer only
            return reply

        if depth > int(_cfg("max_depth")):
            return self._refuse(msg, f"conversation is nested {depth} deep (limit {_cfg('max_depth')})", "depth_exceeded", started)
        if self._rate_limited(sid):
            return self._refuse(msg, f"{sname} is sending more than {_cfg('rate_per_minute')} requests a minute", "rate_limited", started)
        if self._over_budget(correlation):
            return self._refuse(msg, f"conversation used its {_cfg('max_messages_per_conversation')}-message budget", "budget_exhausted", started)
        if self._inflight >= int(_cfg("max_inflight")):
            return self._refuse(msg, "too many requests in flight", "busy", started)

        # --- prompt-injection screen on the payload (agents relay content that came from the outside world) ---
        try:
            from core.security.prompt_injection import scan_text
            scan = scan_text(self._payload_text(msg.params)[:20000], context="a2a")
            if scan.has_high:
                return self._refuse(msg, "payload looks like a prompt-injection attempt: " + "; ".join(w.description for w in scan.warnings[:2]),
                                    "blocked", started)
        except Exception as e:
            logger.debug("[VECTOR][a2a] injection screen unavailable: {}", e)

        # --- resolve the target ---
        target = None
        district_route = None
        if isinstance(to, str) and to.startswith("district:"):
            district_route = to.split(":", 1)[1].strip()
            eligible = [a for a in self.agents()
                        if getattr(a, "district", "") == district_route
                        and getattr(a, "id", "") not in path
                        and getattr(a, "id", "") != sid]
            preferred = [a for a in self.find(capability or msg.task_type, district_route)
                         if getattr(a, "id", "") not in path and getattr(a, "id", "") != sid]
            candidates = preferred or sorted(eligible, key=lambda a: getattr(a, "health_points", 0), reverse=True)
            if not candidates:
                return self._refuse(msg, f"no eligible live agent in district {district_route!r}", "unavailable", started)
            target = candidates[0]
        elif to is not None:
            target = self.resolve(to)
            if target is None:
                return self._refuse(msg, f"no live agent named {to!r}", "unavailable", started)
        else:
            cands = self.find(capability or msg.task_type)
            cands = [a for a in cands if getattr(a, "id", "") not in path]
            if not cands:
                return self._refuse(msg, f"no live agent declares {capability or msg.task_type!r}", "unavailable", started)
            target = cands[0]
        if target is not None:
            msg.recipient = getattr(target, "name", msg.recipient)
            if getattr(target, "id", None) == sid:
                return self._refuse(msg, "an agent cannot send a request to itself", "refused", started)
            if getattr(target, "id", None) in path:
                return self._refuse(msg, f"{msg.recipient} is already part of this conversation (cycle)", "cycle", started)

        # --- authorization: the gateway classifies the ACTION, never the agent ---
        try:
            from core.loop.permission_gateway import PermissionGateway
            gateway = PermissionGateway()
            tier = gateway._classify(msg.task_type)
        except Exception as e:
            return self._refuse(msg, f"authorization check failed ({e}); failing closed", "blocked", started)
        if tier == "FORBIDDEN":
            return self._refuse(msg, f"'{msg.task_type}' is FORBIDDEN and can never be requested", "blocked", started)
        if tier in ("YELLOW", "RED"):
            if not escalate:
                return self._refuse(
                    msg, f"'{msg.task_type}' is {tier}-tier: the A2A bus carries information requests only; propose it through "
                         f"the PermissionGateway (or pass escalate=True)", "requires_approval", started)
            return await self._escalate(msg, gateway, started)

        # --- deliver through the Governor (tier gate, unknown-type gate, timeout, HP accounting, events) ---
        self._inflight += 1
        # A no-reward request (practice drill) must leave HP exactly as it found it. The Governor skips its own award for it, but agents
        # also award THEMSELVES HP inside their handlers (GitBot: +2.5 per status call), so snapshot and restore. Only the addressed
        # agent is touched, and drills only run for idle agents, so there is no concurrent real work to erase.
        snapshot = None
        if no_reward and target is not None:
            snapshot = (getattr(target, "health_points", None), dict(getattr(target, "_reason_award_counts", {}) or {}))
        token = _CHAIN.set({"correlation_id": correlation, "depth": depth, "path": path + ((getattr(target, "id", ""),) if target else ()),
                            "origin": msg.origin})
        try:
            from core.city.governor import Governor
            task: dict = {"type": msg.task_type, "params": dict(msg.params), "_a2a": {"message_id": msg.id, "from": sname,
                          "from_district": sdistrict, "correlation_id": correlation, "depth": depth}}
            if no_reward:
                task["_no_reward"] = True
            if target is not None:
                task["district"] = getattr(target, "district", None)
                task["_a2a_target"] = getattr(target, "id", None)
            elif district_route:
                task["district"] = district_route
            try:
                requested_budget = float(timeout if timeout is not None else _cfg("default_timeout_sec"))
            except (TypeError, ValueError):
                requested_budget = float(_cfg("default_timeout_sec"))
            if not math.isfinite(requested_budget) or requested_budget <= 0:
                requested_budget = float(_cfg("default_timeout_sec"))
            budget = min(requested_budget, float(_cfg("max_timeout_sec")))
            raw = await asyncio.wait_for(Governor().dispatch(task), timeout=budget)
            result = raw if isinstance(raw, dict) else {"status": "ok", "value": raw}
            status = str(result.get("status", "ok"))
            not_delivered = status in ("blocked", "no_agents", "no_capable_agent")
            reply = A2AReply(
                message_id=msg.id, correlation_id=correlation, status=status, delivered=not not_delivered, result=result,
                responder=str(result.get("agent") or getattr(target, "name", "") or ""),
                responder_district=str(result.get("district") or getattr(target, "district", "") or district_route or ""),
                refused=str(result.get("reason", status)) if not_delivered else "",
                elapsed_ms=int((time.time() - started) * 1000),
            )
            self.stats["refused" if not_delivered else "delivered"] += 1
        except asyncio.TimeoutError:
            reply = A2AReply(message_id=msg.id, correlation_id=correlation, status="timeout", delivered=False,
                             refused=f"no answer within {budget:.0f}s", elapsed_ms=int((time.time() - started) * 1000))
            self.stats["failed"] += 1
        except Exception as e:
            logger.warning("[VECTOR][a2a] delivery failed: {}", e)
            reply = A2AReply(message_id=msg.id, correlation_id=correlation, status="error", delivered=False, error=str(e),
                             elapsed_ms=int((time.time() - started) * 1000))
            self.stats["failed"] += 1
        finally:
            _CHAIN.reset(token)
            self._inflight -= 1
            if snapshot is not None and snapshot[0] is not None:
                try:
                    target.health_points = snapshot[0]
                    target._reason_award_counts = snapshot[1]
                    target.model = target._calculate_model()
                except Exception:
                    pass
        if not reply.responder and target is not None:
            reply.responder, reply.responder_district = getattr(target, "name", ""), getattr(target, "district", "")
        if reply.ok and callable(verify) and target is not None and not no_reward and mode in ("ask", "delegate"):
            self._credit_collaboration(msg, target, reply, verify)
        self._audit(msg, reply)
        return reply

    _COLLAB_DAILY_CAP = 3
    _COLLAB_WEIGHT = 0.5

    def _credit_collaboration(self, msg: A2AMessage, target: Any, reply: A2AReply, verify: Any) -> None:
        """Credit the helper only when the asker's own check of the answer passes, and never more than a few times a day for the same
        (asker, helper, task) -- so a verified, useful answer is rewarded and trading requests back and forth is not."""
        try:
            if not verify(reply.result):
                return
            day = time.strftime("%Y-%m-%d")
            key = (day, msg.sender_id, getattr(target, "id", ""), msg.task_type)
            counts = self.__dict__.setdefault("_collab_counts", {})
            if counts.get(key, 0) >= self._COLLAB_DAILY_CAP:
                return
            counts[key] = counts.get(key, 0) + 1
            for k in [k for k in counts if k[0] != day]:
                counts.pop(k, None)
            from core.city import experience
            xp = experience.record(target, f"collab:{msg.task_type}", "success", verified=True, difficulty=0.5,
                                   note=f"helped {msg.sender_name}", weight=self._COLLAB_WEIGHT)
            reply.result.setdefault("_collab_xp", round(xp, 2)) if isinstance(reply.result, dict) else None
        except Exception as e:
            logger.debug("[VECTOR][a2a] collaboration credit skipped: {}", e)

    async def _escalate(self, msg: A2AMessage, gateway: Any, started: float) -> A2AReply:
        """YELLOW/RED request the caller explicitly opted to raise: it becomes an ordinary proposed action. The proposer id is the
        untrusted "a2a_agent", so it gets none of the owner-initiated shortcuts (api_command / voice)."""
        try:
            from core.loop.permission_gateway import Action
            res = await gateway.execute(Action(action_type=msg.task_type, params=dict(msg.params), proposed_by="a2a_agent"))
            payload = res.result if isinstance(res.result, dict) else {}
            reply = A2AReply(
                message_id=msg.id, correlation_id=msg.correlation_id,
                status=str(payload.get("status") or ("ok" if res.executed else ("blocked" if not res.approved else "failed"))),
                delivered=bool(res.approved and res.executed), result=payload, responder="PermissionGateway",
                refused="" if (res.approved and res.executed) else str(res.reason or "not approved"),
                elapsed_ms=int((time.time() - started) * 1000),
            )
        except Exception as e:
            reply = A2AReply(message_id=msg.id, correlation_id=msg.correlation_id, status="error", error=str(e),
                             elapsed_ms=int((time.time() - started) * 1000))
        self.stats["delivered" if reply.delivered else "refused"] += 1
        self._audit(msg, reply)
        return reply

    # ── the three verbs ─────────────────────────────────────────────────────────────────────────────────────────────────
    async def ask(self, sender: Any, task_type: str, params: dict | None = None, **kw) -> A2AReply:
        """Request and wait for the answer."""
        return await self.request(sender, task_type, params, mode="ask", **kw)

    async def delegate(self, sender: Any, task_type: str, params: dict | None = None, **kw) -> A2AReply:
        """Like ask, but the sender hands the work over (recorded as such for credit attribution in a later phase)."""
        return await self.request(sender, task_type, params, mode="delegate", **kw)

    def tell(self, sender: Any, task_type: str, params: dict | None = None, **kw) -> str:
        """Fire and forget: returns immediately with the message id; the reply lands in the sender's inbox."""
        sid, _, _ = self._sender_identity(sender)
        marker = f"tell_{uuid.uuid4().hex[:10]}"
        chain = _CHAIN.get()

        async def _run() -> None:
            # the background task must carry the sender's chain so depth/cycle guards still apply
            token = _CHAIN.set(chain) if chain else None
            try:
                reply = await self.request(sender, task_type, params, mode="tell", **kw)
                self._inbox.setdefault(sid, deque(maxlen=50)).append({"marker": marker, **reply.to_dict()})
            finally:
                if token is not None:
                    _CHAIN.reset(token)

        try:
            t = asyncio.get_running_loop().create_task(_run())
        except RuntimeError:
            return ""
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return marker


_BUS: A2ABus | None = None


def get_bus() -> A2ABus:
    global _BUS
    if _BUS is None:
        _BUS = A2ABus()
    return _BUS


if __name__ == "__main__":
    import sys

    async def _smoke() -> bool:
        bus = A2ABus(registry=type("R", (), {"get_all_agents": staticmethod(lambda: [])})())
        r = await bus.ask("owner_api", "ping", to="nobody")
        return r.status == "unavailable" and not r.delivered

    print("a2a_bus OK" if asyncio.run(_smoke()) else "a2a_bus FAILED")
    sys.exit(0)
