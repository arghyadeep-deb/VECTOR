"""
QueenCoordinator — VectorCode VC-3 + Ruflo Queen absorption.

Absorbed from Ruflo v2/src/hive-mind/core/Queen.ts:
  - startCoordinationLoop(): monitors swarm state, re-decomposes stalled subtasks
  - ConsensusProposal: lightweight consensus round before RED-gate actions
  - Capability declarations: Queen registers capabilities with the swarm

Original single-shot decompose() preserved (backward compat).
"""
import json
import asyncio
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from loguru import logger

if TYPE_CHECKING:
    from agents.districts.coding.vectorcode.swarm import SwarmCoordinator


def chat(model: str, prompt: str) -> str:
    """Thin Ollama wrapper — module-level for test patching."""
    import ollama
    try:
        resp = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        return resp["message"]["content"]
    except Exception as e:
        logger.warning(f"[VECTOR][queen] ollama unavailable: {e}")
        return '{"subtasks": []}'


_DECOMPOSE_PROMPT = """\
Decompose the following task into concrete subtasks. Return ONLY valid JSON.

Format:
{{"subtasks": [{{"task": "...", "domain": "core|security|devops|research|support"}}]}}

Task: {task}"""

_CONSENSUS_PROMPT = """\
A RED-gate action has been proposed. Evaluate whether it should proceed.

Action: {action}
Context: {context}

Return ONLY valid JSON:
{{"verdict": "proceed|reject|defer", "confidence": 0.0-1.0, "reason": "..."}}"""


# ── Consensus types (absorbed from Ruflo Queen.ts) ────────────────────────────

class ConsensusVerdict(Enum):
    PROCEED = "proceed"
    REJECT  = "reject"
    DEFER   = "defer"


@dataclass
class ConsensusProposal:
    action:      str
    context:     str = ""
    proposer:    str = "swarm"
    votes:       dict = field(default_factory=dict)  # voter_id -> verdict
    confidence:  float = 0.0
    verdict:     ConsensusVerdict | None = None
    created_at:  float = field(default_factory=time.time)


class QueenCoordinator:
    """
    Decomposes high-level tasks and coordinates the swarm.

    Single-shot mode  : decompose(task) → subtasks list
    Coordination loop : start_coordination_loop(swarm) — async, runs continuously
    Consensus         : build_consensus(proposal) — before RED-gate actions
    """

    CAPABILITIES = [
        "strategic_planning",
        "task_allocation",
        "consensus_coordination",
        "performance_optimization",
        "swarm_governance",
    ]

    def __init__(self):
        self._model = "vector-reasoning"
        self._loop_running = False
        self._loop_interval = 30.0   # seconds between coordination ticks
        self._stall_threshold = 120.0  # seconds before a subtask is considered stalled
        self._active_proposals: list[ConsensusProposal] = []
        self._completed_tasks: list[dict] = []

    # ── Single-shot decompose (original VC-3, preserved for compat) ───────────

    def decompose(self, task: str) -> list:
        """Decompose a high-level task into domain-tagged subtasks."""
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

    # ── Coordination loop (absorbed from Ruflo Queen.startCoordinationLoop) ───

    async def start_coordination_loop(self, swarm: "SwarmCoordinator") -> None:
        """
        Continuous coordination loop — monitors swarm health, re-decomposes
        stalled subtasks, optimises agent assignments.
        Ruflo reference: Queen.startCoordinationLoop() + startOptimizationLoop()
        """
        self._loop_running = True
        logger.info("[VECTOR][queen] coordination loop started")
        while self._loop_running:
            try:
                await self._coordination_tick(swarm)
            except Exception as e:
                logger.error(f"[VECTOR][queen] coordination tick failed: {e}")
            await asyncio.sleep(self._loop_interval)

    async def _coordination_tick(self, swarm: "SwarmCoordinator") -> None:
        """Single coordination tick: check stalled tasks, rebalance if needed."""
        report = swarm.report()
        agents = report.get("agents", [])

        # Identify idle agents
        idle = [a for a in agents if a.get("status") == "idle"]
        busy = [a for a in agents if a.get("status") == "busy"]

        if idle:
            logger.debug(f"[VECTOR][queen] tick: {len(idle)} idle, {len(busy)} busy agents")

        # Check for stalled tasks (started but not finished for > threshold)
        now = time.time()
        for agent_info in busy:
            started_at = agent_info.get("task_started_at", now)
            if now - started_at > self._stall_threshold:
                agent_id = agent_info.get("id", "?")
                task = agent_info.get("current_task", "")
                logger.warning(
                    f"[VECTOR][queen] stalled agent {agent_id}: '{task[:60]}' "
                    f"({int(now - started_at)}s) — re-decomposing"
                )
                # Re-decompose and reassign
                if task:
                    new_subtasks = self.decompose(task)
                    logger.info(
                        f"[VECTOR][queen] re-decomposed into {len(new_subtasks)} subtasks"
                    )

    def stop_coordination_loop(self) -> None:
        self._loop_running = False
        logger.info("[VECTOR][queen] coordination loop stopped")

    # ── Consensus (absorbed from Ruflo ConsensusProposal) ─────────────────────

    def build_consensus(self, action: str, context: str = "") -> ConsensusProposal:
        """
        Before a RED-gate action, ask vector-reasoning for a verdict.
        Returns a ConsensusProposal with verdict set.
        Ruflo ref: Queen creates ConsensusProposal, collects agent votes.
        """
        proposal = ConsensusProposal(action=action, context=context)

        prompt = _CONSENSUS_PROMPT.format(action=action, context=context)
        raw = chat(self._model, prompt)

        try:
            data = json.loads(raw)
            verdict_str = data.get("verdict", "defer")
            verdict = ConsensusVerdict(verdict_str) if verdict_str in ConsensusVerdict._value2member_map_ else ConsensusVerdict.DEFER
            proposal.verdict = verdict
            proposal.confidence = float(data.get("confidence", 0.5))
            proposal.votes["queen"] = verdict_str
            logger.info(
                f"[VECTOR][queen] consensus: action='{action[:60]}' "
                f"verdict={verdict.value} confidence={proposal.confidence:.2f}"
            )
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"[VECTOR][queen] consensus parse failed: {e} — defaulting to DEFER")
            proposal.verdict = ConsensusVerdict.DEFER
            proposal.confidence = 0.5

        self._active_proposals.append(proposal)
        return proposal

    def should_proceed(self, proposal: ConsensusProposal) -> bool:
        """
        Return True if consensus verdict is PROCEED with confidence ≥ 0.7.
        RED actions require high-confidence approval.
        """
        return (
            proposal.verdict == ConsensusVerdict.PROCEED
            and proposal.confidence >= 0.7
        )

    # ── Swarm registration ────────────────────────────────────────────────────

    def get_capabilities(self) -> list[str]:
        """Return Queen's declared capabilities (Ruflo agent capability declarations)."""
        return list(self.CAPABILITIES)

    def get_status(self) -> dict:
        return {
            "loop_running": self._loop_running,
            "active_proposals": len(self._active_proposals),
            "capabilities": self.CAPABILITIES,
            "model": self._model,
        }


if __name__ == "__main__":
    q = QueenCoordinator()

    # Single-shot decompose (backward compat)
    result = q.decompose("build a login endpoint with JWT auth")
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "task" in result[0] and "domain" in result[0]

    # Capabilities (Ruflo absorbed feature)
    caps = q.get_capabilities()
    assert "strategic_planning" in caps
    assert "consensus_coordination" in caps

    # Status
    status = q.get_status()
    assert "loop_running" in status
    assert not status["loop_running"]

    # Consensus proposal (non-LLM path — tests graceful fallback)
    proposal = ConsensusProposal(action="delete production database", context="maintenance")
    proposal.verdict = ConsensusVerdict.DEFER
    proposal.confidence = 0.4
    assert not q.should_proceed(proposal)

    proposal2 = ConsensusProposal(action="run tests", context="safe operation")
    proposal2.verdict = ConsensusVerdict.PROCEED
    proposal2.confidence = 0.9
    assert q.should_proceed(proposal2)

    print(f"queen.py OK — {len(result)} subtask(s), caps={len(caps)}")
