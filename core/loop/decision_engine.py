import sys
import asyncio
import datetime
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


@dataclass
class Candidate:
    action_type: str
    params: dict
    goal_ids: list[str] = field(default_factory=list)
    confidence: float = 0.5
    urgency: float = 0.5
    timing_score: float = 1.0
    estimated_cost_inr: float = 0.0
    source: str = "system"
    # Computed during scoring
    goal_alignment: float = 0.0
    policy_score: float = 0.5
    total_score: float = 0.0
    # Reasoning chain populated by _act_on()
    reasoning_chain: list[dict] = field(default_factory=list)
    situation: dict = field(default_factory=dict)
    reasoning_steps: list[str] = field(default_factory=list)


@dataclass
class Decision:
    winner: Candidate
    all_candidates: list[Candidate]
    reasoning: str
    timestamp: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    evaluated: int = 0
    reasoning_chain: list[dict] = field(default_factory=list)
    situation: dict = field(default_factory=dict)


class DecisionEngine:
    """
    Scores 4 candidates per decision using the 5-factor weighted formula.
    RULE 7: policy.get_score() BEFORE. policy.update_from_outcome() AFTER.
    ALL candidates logged — including rejected. No silent drops.

    Scoring: goal_alignment(30%) + confidence(25%) + policy(20%) +
             urgency(15%) + timing(10%) - cost(5%)
    """

    W_GOAL = 0.30
    W_CONF = 0.25
    W_POLICY = 0.20
    W_URGENCY = 0.15
    W_TIMING = 0.10
    W_COST = 0.05

    def __init__(self):
        self._policy = None
        self._goals = None
        self._memory = None
        self._epistemic = None
        logger.info("[VECTOR][decision_engine] initialized")

    def _get_policy(self):
        if self._policy is None:
            from core.memory.policy import PolicyMemory
            self._policy = PolicyMemory()
        return self._policy

    def _get_goals(self):
        if self._goals is None:
            from core.brain.goal_system import GoalSystem
            self._goals = GoalSystem()
        return self._goals

    def _get_memory(self):
        if self._memory is None:
            from core.memory.episodic import EpisodicMemory
            self._memory = EpisodicMemory()
        return self._memory

    def _get_epistemic(self):
        if self._epistemic is None:
            try:
                from core.brain.epistemic_tracker import EpistemicTracker
                self._epistemic = EpistemicTracker()
            except Exception as e:
                logger.debug(f"[VECTOR][decision_engine] EpistemicTracker unavailable: {e}")
        return self._epistemic

    def _score_goal_alignment(self, candidate: Candidate) -> float:
        """How well does this action serve active goals? 0.0-1.0"""
        if not candidate.goal_ids:
            return 0.3

        goals = self._get_goals().get_active_goals()
        goal_map = {g["id"]: g for g in goals}
        score = 0.0
        for gid in candidate.goal_ids:
            if gid in goal_map:
                g = goal_map[gid]
                priority_weight = g.get("priority", 5) / 10.0
                progress_gap = 1.0 - g.get("progress", 0.0)
                score = max(score, priority_weight * progress_gap)
        return min(1.0, score)

    def _make_situation_hash(self, candidate: Candidate) -> str:
        key = f"{candidate.action_type}:{json.dumps(candidate.params, sort_keys=True, default=str)}"
        return hashlib.sha256(key.encode()).hexdigest()[:12]

    def _score_candidate(self, candidate: Candidate) -> float:
        """Apply the 5-factor formula. Mutates candidate with computed scores."""
        situation_hash = self._make_situation_hash(candidate)

        policy_score = self._get_policy().get_score(candidate.action_type, situation_hash)
        candidate.policy_score = policy_score

        goal_score = self._score_goal_alignment(candidate)
        candidate.goal_alignment = goal_score

        cost_penalty = min(1.0, candidate.estimated_cost_inr / 10.0)

        # EpistemicTracker: blend raw confidence with epistemic belief (70/30 split)
        raw_conf = candidate.confidence
        epistemic = self._get_epistemic()
        if epistemic is not None:
            try:
                belief = epistemic.get_belief(candidate.action_type)
                if belief is not None:
                    epistemic_conf = belief.get("confidence", raw_conf)
                    blended_conf = (raw_conf * 0.7) + (epistemic_conf * 0.3)
                    if abs(blended_conf - raw_conf) > 0.05:
                        logger.debug(
                            f"[VECTOR][decision_engine] Epistemic blend {candidate.action_type}: "
                            f"{raw_conf:.2f} → {blended_conf:.2f}"
                        )
                    candidate.confidence = round(blended_conf, 4)
            except Exception:
                pass  # epistemic tracker never blocks a decision

        total = (
            self.W_GOAL * goal_score
            + self.W_CONF * candidate.confidence
            + self.W_POLICY * policy_score
            + self.W_URGENCY * candidate.urgency
            + self.W_TIMING * candidate.timing_score
            - self.W_COST * cost_penalty
        )
        candidate.total_score = round(max(0.0, min(1.0, total)), 4)

        # Build reasoning chain for audit/replay
        candidate.reasoning_chain = [
            {"step": 1, "factor": "goal_alignment", "score": round(goal_score, 4), "weight": self.W_GOAL, "contribution": round(self.W_GOAL * goal_score, 4)},
            {"step": 2, "factor": "confidence", "score": candidate.confidence, "weight": self.W_CONF, "contribution": round(self.W_CONF * candidate.confidence, 4)},
            {"step": 3, "factor": "policy_score", "score": round(policy_score, 4), "weight": self.W_POLICY, "contribution": round(self.W_POLICY * policy_score, 4)},
            {"step": 4, "factor": "urgency", "score": candidate.urgency, "weight": self.W_URGENCY, "contribution": round(self.W_URGENCY * candidate.urgency, 4)},
            {"step": 5, "factor": "timing_score", "score": candidate.timing_score, "weight": self.W_TIMING, "contribution": round(self.W_TIMING * candidate.timing_score, 4)},
            {"step": 6, "factor": "cost_penalty", "score": round(cost_penalty, 4), "weight": self.W_COST, "contribution": round(-self.W_COST * cost_penalty, 4)},
        ]

        candidate.reasoning_steps = [
            f"1. goal_alignment={goal_score:.2f} (contrib={self.W_GOAL*goal_score:.2f})",
            f"2. confidence={candidate.confidence:.2f} (contrib={self.W_CONF*candidate.confidence:.2f})",
            f"3. policy_score={policy_score:.2f} (contrib={self.W_POLICY*policy_score:.2f})",
            f"4. urgency={candidate.urgency:.2f} (contrib={self.W_URGENCY*candidate.urgency:.2f})",
            f"5. timing_score={candidate.timing_score:.2f} (contrib={self.W_TIMING*candidate.timing_score:.2f})",
            f"6. cost_penalty={cost_penalty:.2f} (contrib={-self.W_COST*cost_penalty:.2f})",
            f"FINAL total_score={candidate.total_score:.4f}",
        ]

        # Capture situation for policy memory
        goals = self._get_goals().get_active_goals()
        candidate.situation = {
            "action_type": candidate.action_type,
            "situation_hash": situation_hash,
            "goal_ids": candidate.goal_ids,
            "goal_priorities": [g.get("priority", 5) for g in goals if g.get("id") in candidate.goal_ids],
            "active_goal_count": len(goals),
            "policy_score": round(policy_score, 4),
        }

        return candidate.total_score

    async def evaluate(self, candidates: list[Candidate]) -> Decision:
        """Score all candidates. Return winner. Log ALL including rejected."""
        if not candidates:
            logger.warning("[VECTOR][decision_engine] no candidates provided")
            noop = Candidate("noop", {}, source="fallback")
            return Decision(winner=noop, all_candidates=[], reasoning="No candidates", evaluated=0)

        for c in candidates:
            self._score_candidate(c)

        ranked = sorted(candidates, key=lambda c: c.total_score, reverse=True)
        winner = ranked[0]

        # Log ALL candidates including rejected — RULE 8
        mem = self._get_memory()
        for c in ranked:
            status = "winner" if c is winner else "rejected"
            mem.store(
                event_type="decision_candidate",
                content=f"{status}: {c.action_type} score={c.total_score}",
                tags=["decision", status, c.action_type],
                context={
                    "score": c.total_score,
                    "goal_alignment": c.goal_alignment,
                    "policy": c.policy_score,
                    "confidence": c.confidence,
                },
                source="decision_engine",
            )

        reasoning = (
            f"Winner: {winner.action_type} (score={winner.total_score}) "
            f"over {len(ranked)-1} alternatives. "
            f"goal_alignment={winner.goal_alignment:.2f} "
            f"policy={winner.policy_score:.2f} "
            f"confidence={winner.confidence:.2f}"
        )
        logger.info(f"[VECTOR][decision_engine] {reasoning}")

        return Decision(
            winner=winner,
            all_candidates=ranked,
            reasoning=reasoning,
            evaluated=len(candidates),
            reasoning_chain=[
                {
                    "rank": i + 1,
                    "action_type": c.action_type,
                    "goal_ids": c.goal_ids,
                    "total_score": c.total_score,
                    "goal_alignment": c.goal_alignment,
                    "policy_score": c.policy_score,
                    "confidence": c.confidence,
                    "urgency": c.urgency,
                    "timing_score": c.timing_score,
                    "reasoning_steps": c.reasoning_steps,
                    "winner": c is winner,
                }
                for i, c in enumerate(ranked)
            ],
            situation=winner.situation,
        )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    engine = DecisionEngine()
    candidates = [
        Candidate("search_web", {"query": "KIIT attendance"}, goal_ids=["g_kiit_attendance"], confidence=0.8, urgency=0.6),
        Candidate("check_calendar", {}, confidence=0.9, urgency=0.3),
        Candidate("commit_code", {"repo": "VECTOR"}, goal_ids=["g_vector_phase1"], confidence=0.7, urgency=0.5),
        Candidate("set_reminder", {"text": "Karpathy 30min"}, goal_ids=["g_karpathy_30"], confidence=0.6, urgency=0.4),
    ]
    decision = asyncio.run(engine.evaluate(candidates))
    ok = (
        decision.winner is not None
        and decision.evaluated == 4
        and 0.0 <= decision.winner.total_score <= 1.0
    )
    print(
        f"✅ decision_engine OK — winner={decision.winner.action_type} "
        f"score={decision.winner.total_score}, {decision.evaluated} evaluated"
        if ok else "❌ FAILED"
    )
