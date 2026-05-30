import sys
import asyncio
import datetime
import hashlib
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
    # RULE 8 — past reasoning injected before scoring
    reasoning_steps: list[str] = field(default_factory=list)


@dataclass
class Decision:
    winner: Candidate
    all_candidates: list[Candidate]
    reasoning: str
    timestamp: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())
    evaluated: int = 0


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
        self._reasoning_bank = None
        logger.info("[VECTOR][decision_engine] initialized")

    def _get_reasoning_bank(self):
        """ReasoningBank: inject past reasoning chains before scoring (RULE 8)."""
        if self._reasoning_bank is None:
            try:
                try:
                    from vectorcode.src.reasoning_bank import ReasoningBank
                except ImportError:
                    # importlib fallback: load by absolute file path so sys.path gaps never disable RULE 8
                    import importlib.util as _ilu
                    _rb_path = Path(__file__).parent.parent.parent / "vectorcode" / "src" / "reasoning_bank.py"
                    _spec = _ilu.spec_from_file_location("vectorcode.src.reasoning_bank", _rb_path)
                    _mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
                    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
                    ReasoningBank = _mod.ReasoningBank
                self._reasoning_bank = ReasoningBank()
                self._reasoning_bank.load()
                _entry_count = len(self._reasoning_bank._entries)
                logger.info(
                    "[VECTOR][decision_engine] ReasoningBank online — RULE 8 active ({} entries)",
                    _entry_count,
                )
            except Exception as e:
                logger.warning(
                    "[VECTOR][decision_engine] ReasoningBank unavailable — RULE 8 disabled: {}", e
                )
                self._reasoning_bank = False  # sentinel: do not retry
        return self._reasoning_bank if self._reasoning_bank is not False else None

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
        key = f"{candidate.action_type}:{sorted(candidate.params.items())}"
        return hashlib.md5(key.encode()).hexdigest()[:12]

    def _score_candidate(self, candidate: Candidate) -> float:
        """Apply the 5-factor formula. Mutates candidate with computed scores."""
        situation_hash = self._make_situation_hash(candidate)

        # RULE 7 — get_score() BEFORE every decision
        policy_score = self._get_policy().get_score(candidate.action_type, situation_hash)
        candidate.policy_score = policy_score

        goal_score = self._score_goal_alignment(candidate)
        candidate.goal_alignment = goal_score

        cost_penalty = min(1.0, candidate.estimated_cost_inr / 10.0)

        total = (
            self.W_GOAL * goal_score
            + self.W_CONF * candidate.confidence
            + self.W_POLICY * policy_score
            + self.W_URGENCY * candidate.urgency
            + self.W_TIMING * candidate.timing_score
            - self.W_COST * cost_penalty
        )
        candidate.total_score = round(max(0.0, min(1.0, total)), 4)
        return candidate.total_score

    async def evaluate(self, candidates: list[Candidate]) -> Decision:
        """Score all candidates. Return winner. Log ALL including rejected."""
        if not candidates:
            logger.warning("[VECTOR][decision_engine] no candidates provided")
            noop = Candidate("noop", {}, source="fallback")
            return Decision(winner=noop, all_candidates=[], reasoning="No candidates", evaluated=0)

        # RULE 8 — inject past reasoning before scoring
        bank = self._get_reasoning_bank()
        if bank is not None:
            try:
                for c in candidates:
                    query = f"{c.action_type} {' '.join(str(v) for v in c.params.values())}"
                    past_snippet = bank.inject_past_reasoning(query, top_k=3)
                    if past_snippet:
                        c.reasoning_steps = [past_snippet]
            except Exception as _rb_err:
                logger.warning("[VECTOR][decision_engine] RULE 8 inject failed: {}", _rb_err)

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
