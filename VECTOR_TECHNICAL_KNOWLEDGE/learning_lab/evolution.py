"""
VECTOR Digital Twin Lab — multi-experience evolution (Task 78 Phase 11).

Applies experience 1, 2, 3, ... sequentially against ONE shared isolated
env and records the decision after each — then explicitly separates
STATE ACCUMULATION (row count / sample_count growing — always true once any
update is applied) from BEHAVIORAL ADAPTATION (the winner actually
changing as a *consequence*, not merely a coincident row-count increase).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from isolation import IsolatedVectorEnv
from scenario import Scenario
from twin import build_isolated_engine, make_situation_hash


@dataclass
class EvolutionStep:
    step: int
    reward_applied: float | None
    sample_count_after: int
    avg_reward_after: float
    winner: str
    winner_score: float
    all_scores: dict


@dataclass
class EvolutionResult:
    label: str
    steps: list[EvolutionStep] = field(default_factory=list)

    def state_accumulated(self) -> bool:
        """True iff sample_count strictly grew across the run — this is
        cheap and ALWAYS true once >=1 reward is applied; it is NOT, by
        itself, evidence of adaptation. See `behavioral_adaptation_events`."""
        counts = [s.sample_count_after for s in self.steps]
        return len(counts) >= 2 and counts[-1] > counts[0]

    def behavioral_adaptation_events(self) -> list[tuple[int, str, str]]:
        """Steps where the WINNER actually differs from the immediately
        preceding step — the honest signal, separate from state growth."""
        events = []
        for prev, cur in zip(self.steps, self.steps[1:]):
            if prev.winner != cur.winner:
                events.append((cur.step, prev.winner, cur.winner))
        return events

    def summary(self) -> str:
        lines = [f"EVOLUTION: {self.label}"]
        for s in self.steps:
            lines.append(
                f"  step {s.step}: reward={s.reward_applied}  "
                f"sample_count={s.sample_count_after}  avg_reward={s.avg_reward_after:.3f}  "
                f"winner={s.winner} (score={s.winner_score:.4f})"
            )
        lines.append(f"  state accumulated (sample_count grew): {self.state_accumulated()}")
        events = self.behavioral_adaptation_events()
        if events:
            for step, old, new in events:
                lines.append(f"  BEHAVIORAL ADAPTATION at step {step}: winner {old} -> {new}")
        else:
            lines.append("  NO behavioral adaptation event — state grew but the winner never changed.")
        return "\n".join(lines)


def run_evolution(label: str, action_type: str, params: dict, rival_action_type: str,
                    rival_params: dict, rewards: list[float]) -> EvolutionResult:
    """`rewards[i]` is applied to `action_type` AFTER observing step i's
    decision, then step i+1 re-decides the same two-candidate race. The
    rival never receives any reward — a static reference point."""
    from core.loop.decision_engine import Candidate

    result = EvolutionResult(label=label)
    sit_hash = make_situation_hash(action_type, params)

    with IsolatedVectorEnv() as env:
        engine = build_isolated_engine(env)

        def decide_once(step_idx: int, reward_just_applied: float | None) -> EvolutionStep:
            candidates = [
                Candidate(action_type, dict(params), confidence=0.6, urgency=0.5),
                Candidate(rival_action_type, dict(rival_params), confidence=0.6, urgency=0.5),
            ]
            decision = asyncio.run(engine.evaluate(candidates))
            row = engine._policy.get_stats()
            score_val = engine._policy.get_score(action_type, sit_hash)
            all_scores = {c.action_type: c.total_score for c in decision.all_candidates}
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cur:
                r = cur.execute(
                    "SELECT avg_reward, sample_count FROM policy_memory WHERE action_type=? AND situation_hash=?",
                    (action_type, sit_hash),
                ).fetchone()
            avg_reward, sample_count = (r[0], r[1]) if r else (0.5, 0)
            return EvolutionStep(
                step=step_idx, reward_applied=reward_just_applied,
                sample_count_after=sample_count, avg_reward_after=avg_reward,
                winner=decision.winner.action_type, winner_score=decision.winner.total_score,
                all_scores=all_scores,
            )

        result.steps.append(decide_once(0, None))
        for i, reward in enumerate(rewards, start=1):
            engine._policy.update_from_outcome(action_type, sit_hash, reward)
            result.steps.append(decide_once(i, reward))

    return result


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    result = run_evolution(
        "search_web_slowly_earns_trust", "search_web", {"q": "evolve"},
        "check_calendar", {},
        rewards=[0.6, 0.7, 0.8, 0.9, 0.95],
    )
    print(result.summary())
