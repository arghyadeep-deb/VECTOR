"""
QueenCoordinator — complete Queen coordinator absorption + multi-model consensus.

Absorbed from reference v2/src/hive-mind/core/Queen.ts:
  - startCoordinationLoop()  — continuous swarm monitoring + stall detection
  - startOptimizationLoop()  — latency + reward optimization
  - ConsensusProposal        — formal multi-model voting before RED-gate actions
  - QueenDecision            — typed decision with voter breakdown
  - CoordinationStrategy     — pluggable per-topology strategy
  - capability declarations  — Queen registers capabilities with swarm

Multi-model consensus: 3 voters (vector-reasoning + vector-coder + vector-reasoning).
Quorum: 2/3 majority needed for RED-gate actions.
"""
import json
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Callable

from loguru import logger

if TYPE_CHECKING:
    from swarm import SwarmCoordinator


# ── Module-level chat (patchable in tests) ────────────────────────────────────

def chat(model: str, prompt: str, timeout: float = 30.0) -> str:
    import ollama
    try:
        # Use a client with an explicit timeout so a slow/hung Ollama fails
        # fast into the graceful fallback instead of blocking forever.
        resp = ollama.Client(timeout=timeout).chat(
            model=model, messages=[{"role": "user", "content": prompt}]
        )
        return resp["message"]["content"]
    except Exception as e:
        logger.warning(f"[VECTOR][queen] ollama {model} unavailable: {e}")
        return '{"subtasks": []}'


# ── Prompts ───────────────────────────────────────────────────────────────────

_DECOMPOSE_PROMPT = """\
Decompose the following task into concrete subtasks. Return ONLY valid JSON.
Format: {{"subtasks": [{{"task": "...", "domain": "core|security|devops|research|support"}}]}}
Task: {task}"""

_CONSENSUS_PROMPT = """\
A {gate_level}-gate action has been proposed. Evaluate whether it should proceed.
Action: {action}
Context: {context}
You are voter: {voter_role}

Return ONLY valid JSON:
{{"verdict": "proceed|reject|defer", "confidence": 0.0-1.0, "reason": "one sentence"}}"""

_OPTIMIZATION_PROMPT = """\
Analyze this swarm performance data and suggest 3 concrete optimizations.
Data: {data}
Return ONLY valid JSON: {{"optimizations": ["...", "...", "..."]}}"""


# ── Data types ────────────────────────────────────────────────────────────────

class ConsensusVerdict(Enum):
    PROCEED = "proceed"
    REJECT  = "reject"
    DEFER   = "defer"


@dataclass
class VoterResult:
    voter:      str
    model:      str
    verdict:    ConsensusVerdict
    confidence: float
    reason:     str


@dataclass
class ConsensusProposal:
    action:      str
    context:     str                = ""
    gate_level:  str                = "RED"
    proposer:    str                = "swarm"
    voter_results: list             = field(default_factory=list)  # [VoterResult]
    verdict:     ConsensusVerdict | None = None
    confidence:  float              = 0.0
    decision_reason: str            = ""
    created_at:  float              = field(default_factory=time.time)

    @property
    def votes(self) -> dict:
        return {vr.voter: vr.verdict.value for vr in self.voter_results}


@dataclass
class QueenDecision:
    """reference QueenDecision — typed output from coordination loop."""
    task:        str
    subtasks:    list
    assigned_to: dict   # {agent_id: subtask}
    strategy:    str
    created_at:  float  = field(default_factory=time.time)


# ── Coordination strategies (pluggable, reference CoordinationStrategy concept) ───

class CoordinationStrategy:
    name: str = "base"

    def select_agents(self, agents: list, task: str) -> list:
        return agents

    def assign(self, agents: list, subtasks: list) -> dict:
        assignment = {}
        for i, subtask in enumerate(subtasks):
            if agents:
                agent = agents[i % len(agents)]
                assignment[getattr(agent, "id", str(i))] = subtask
        return assignment


class HierarchicalStrategy(CoordinationStrategy):
    name = "hierarchical"

    def select_agents(self, agents: list, task: str) -> list:
        return sorted(agents, key=lambda a: getattr(a, "hp", 500), reverse=True)


class MeshStrategy(CoordinationStrategy):
    name = "mesh"

    def select_agents(self, agents: list, task: str) -> list:
        return agents  # all agents participate equally


class AdaptiveStrategy(CoordinationStrategy):
    name = "adaptive"

    def select_agents(self, agents: list, task: str) -> list:
        # Pick agents whose domain matches task keywords
        task_lower = task.lower()
        domain_agents = [
            a for a in agents
            if any(kw in task_lower for kw in [
                getattr(a, "domain", ""), getattr(a, "name", "").lower()
            ])
        ]
        return domain_agents or agents


_STRATEGIES = {
    "hierarchical": HierarchicalStrategy(),
    "mesh":         MeshStrategy(),
    "adaptive":     AdaptiveStrategy(),
}


class QueenCoordinator:
    """
    Queen coordinator with continuous loops and multi-model consensus.
    Complete absorption of Queen coordinator.
    """

    CAPABILITIES = [
        "strategic_planning",
        "task_allocation",
        "consensus_coordination",
        "performance_optimization",
        "swarm_governance",
    ]

    # Consensus voters: (voter_role, model, weight)
    _VOTERS = [
        ("strategist",  "vector-reasoning",  0.4),
        ("auditor",     "vector-coder",         0.35),
        ("chairman",    "vector-reasoning",    0.25),
    ]

    _QUORUM_THRESHOLD    = 0.67   # 2/3 of weighted votes must be PROCEED
    _CONFIDENCE_MIN      = 0.65   # minimum average confidence for PROCEED
    _STALL_THRESHOLD     = 120.0  # seconds before a task is stalled
    _LOOP_INTERVAL       = 30.0   # coordination loop tick
    _OPTIM_INTERVAL      = 300.0  # optimization loop tick (5 min)

    def __init__(self):
        self._model             = "vector-reasoning"
        self._loop_running      = False
        self._optim_running     = False
        self._active_proposals: list[ConsensusProposal]  = []
        self._decisions:        list[QueenDecision]       = []
        self._strategy:         CoordinationStrategy      = HierarchicalStrategy()
        self._performance_log:  list[dict]                = []

    # ── Decompose (original VC-3, preserved) ─────────────────────────────────

    def decompose(self, task: str) -> list:
        prompt = _DECOMPOSE_PROMPT.format(task=task)
        raw = chat(self._model, prompt)
        try:
            data = json.loads(raw)
            subtasks = data.get("subtasks", [])
            if subtasks and all("task" in s and "domain" in s for s in subtasks):
                logger.info(f"[VECTOR][queen] decomposed '{task[:60]}' → {len(subtasks)} subtasks")
                return subtasks
        except (json.JSONDecodeError, AttributeError, TypeError):
            logger.warning("[VECTOR][queen] bad JSON from LLM, using fallback")
        return [{"task": task, "domain": "core"}]

    def plan(self, task: str, swarm: "SwarmCoordinator") -> QueenDecision:
        """
        Full plan: decompose → select agents → assign subtasks.
        Returns a QueenDecision (reference typed decision output).
        """
        subtasks  = self.decompose(task)
        agents    = self._strategy.select_agents(swarm.list_agents(), task)
        assignment = self._strategy.assign(agents, subtasks)

        decision = QueenDecision(
            task=task, subtasks=subtasks,
            assigned_to=assignment, strategy=self._strategy.name,
        )
        self._decisions.append(decision)
        return decision

    def set_strategy(self, strategy_name: str) -> None:
        self._strategy = _STRATEGIES.get(strategy_name, HierarchicalStrategy())
        logger.info(f"[VECTOR][queen] strategy → {self._strategy.name}")

    # ── Coordination loop (reference startCoordinationLoop) ──────────────────────

    async def start_coordination_loop(self, swarm: "SwarmCoordinator") -> None:
        self._loop_running = True
        logger.info("[VECTOR][queen] coordination loop started")
        while self._loop_running:
            try:
                await self._coordination_tick(swarm)
            except Exception as e:
                logger.error(f"[VECTOR][queen] tick failed: {e}")
            await asyncio.sleep(self._LOOP_INTERVAL)

    async def _coordination_tick(self, swarm: "SwarmCoordinator") -> None:
        report = swarm.report()
        agents = report.get("agents", [])
        now = time.time()

        # Detect stalled agents (busy > threshold seconds)
        for agent_info in agents if isinstance(agents[0], dict) else []:
            started = agent_info.get("task_started_at", now)
            if now - started > self._STALL_THRESHOLD:
                task = agent_info.get("current_task", "")
                if task:
                    logger.warning(
                        f"[VECTOR][queen] stalled: {agent_info.get('id', '?')} — '{task[:60]}' "
                        f"({int(now - started)}s) — redecomposing"
                    )
                    self.decompose(task)

        # Log snapshot
        self._performance_log.append({
            "ts": now,
            "active": report.get("active", 0),
        })
        self._performance_log = self._performance_log[-100:]

    # ── Optimization loop (reference startOptimizationLoop) ──────────────────────

    async def start_optimization_loop(self, swarm: "SwarmCoordinator") -> None:
        self._optim_running = True
        logger.info("[VECTOR][queen] optimization loop started")
        while self._optim_running:
            try:
                await self._optimization_tick(swarm)
            except Exception as e:
                logger.error(f"[VECTOR][queen] optim tick failed: {e}")
            await asyncio.sleep(self._OPTIM_INTERVAL)

    async def _optimization_tick(self, swarm: "SwarmCoordinator") -> dict:
        if not self._performance_log:
            return {}
        recent = self._performance_log[-10:]
        avg_active = sum(s["active"] for s in recent) / len(recent)
        data_str = json.dumps({"avg_active_agents": avg_active, "samples": len(recent)})
        raw = chat(self._model, _OPTIMIZATION_PROMPT.format(data=data_str))
        try:
            opts = json.loads(raw).get("optimizations", [])
            logger.info(f"[VECTOR][queen] optimizations: {opts}")
            return {"optimizations": opts}
        except Exception:
            return {}

    def stop_coordination_loop(self) -> None:
        self._loop_running  = False
        self._optim_running = False
        logger.info("[VECTOR][queen] loops stopped")

    # ── Multi-model consensus (reference ConsensusProposal + QueenDecision) ───────

    def build_consensus(self, action: str, context: str = "", gate_level: str = "RED") -> ConsensusProposal:
        """
        Poll 3 model voters and aggregate by weighted majority.
        reference: Queen collects ConsensusProposal votes from all council agents.
        VectorCode: 3 local Ollama models act as voters (RULE 11 compliant).
        """
        proposal = ConsensusProposal(action=action, context=context, gate_level=gate_level)
        proceed_weight = 0.0
        total_weight   = 0.0
        confidence_sum = 0.0

        for voter_role, model, weight in self._VOTERS:
            prompt = _CONSENSUS_PROMPT.format(
                gate_level=gate_level, action=action,
                context=context, voter_role=voter_role,
            )
            raw = chat(model, prompt)
            try:
                data     = json.loads(raw)
                v_str    = data.get("verdict", "defer")
                v        = ConsensusVerdict(v_str) if v_str in ConsensusVerdict._value2member_map_ else ConsensusVerdict.DEFER
                conf     = float(data.get("confidence", 0.5))
                reason   = data.get("reason", "")
            except Exception:
                v, conf, reason = ConsensusVerdict.DEFER, 0.5, "parse error"

            proposal.voter_results.append(VoterResult(
                voter=voter_role, model=model, verdict=v, confidence=conf, reason=reason
            ))

            if v == ConsensusVerdict.PROCEED:
                proceed_weight += weight
            total_weight   += weight
            confidence_sum += conf * weight

        proceed_ratio   = proceed_weight / total_weight if total_weight > 0 else 0.0
        avg_confidence  = confidence_sum / total_weight if total_weight > 0 else 0.5

        if proceed_ratio >= self._QUORUM_THRESHOLD and avg_confidence >= self._CONFIDENCE_MIN:
            proposal.verdict         = ConsensusVerdict.PROCEED
            proposal.decision_reason = f"Quorum: {proceed_ratio:.0%} voted PROCEED"
        elif proceed_ratio < 0.33:
            proposal.verdict         = ConsensusVerdict.REJECT
            proposal.decision_reason = f"Quorum: {proceed_ratio:.0%} voted PROCEED — rejected"
        else:
            proposal.verdict         = ConsensusVerdict.DEFER
            proposal.decision_reason = f"No quorum: {proceed_ratio:.0%} — deferred"

        proposal.confidence = round(avg_confidence, 3)
        self._active_proposals.append(proposal)

        logger.info(
            f"[VECTOR][queen] consensus: action='{action[:60]}' "
            f"verdict={proposal.verdict.value} ({proceed_ratio:.0%} weighted PROCEED)"
        )
        return proposal

    def should_proceed(self, proposal: ConsensusProposal) -> bool:
        return (
            proposal.verdict == ConsensusVerdict.PROCEED
            and proposal.confidence >= self._CONFIDENCE_MIN
        )

    # ── Capability declarations (reference agent capability declarations) ─────────

    def get_capabilities(self) -> list[str]:
        return list(self.CAPABILITIES)

    def get_voters(self) -> list[dict]:
        return [{"voter": v, "model": m, "weight": w} for v, m, w in self._VOTERS]

    def get_status(self) -> dict:
        return {
            "loop_running":      self._loop_running,
            "optim_running":     self._optim_running,
            "active_proposals":  len(self._active_proposals),
            "decisions":         len(self._decisions),
            "capabilities":      self.CAPABILITIES,
            "strategy":          self._strategy.name,
            "voters":            self.get_voters(),
            "model":             self._model,
        }


if __name__ == "__main__":
    q = QueenCoordinator()

    result = q.decompose("build a login endpoint with JWT auth")
    assert isinstance(result, list) and len(result) >= 1
    assert "task" in result[0] and "domain" in result[0]

    caps = q.get_capabilities()
    assert "strategic_planning" in caps and "consensus_coordination" in caps

    voters = q.get_voters()
    assert len(voters) == 3

    status = q.get_status()
    assert "loop_running" in status and "voters" in status

    p = ConsensusProposal(action="run tests")
    p.verdict = ConsensusVerdict.PROCEED
    p.confidence = 0.9
    assert q.should_proceed(p)

    p2 = ConsensusProposal(action="delete production")
    p2.verdict = ConsensusVerdict.DEFER
    p2.confidence = 0.95
    assert not q.should_proceed(p2)

    q.set_strategy("mesh")
    assert q._strategy.name == "mesh"

    print(f"queen.py OK — {len(result)} subtasks, {len(voters)} voters, strategy={q._strategy.name}")


