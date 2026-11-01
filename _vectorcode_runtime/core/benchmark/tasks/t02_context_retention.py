"""T02 — Context Retention: multi-turn conversation context preserved.

Store 3 turns of escalating context, then query for information from turn 1.
Passes if earlier context is retrievable after later turns are added.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.benchmark.benchmark_task import BenchmarkTask, TaskResult


_TURNS = [
    {"content": "User asks about setting up a FastAPI project with Docker", "turn": 1},
    {"content": "User decides to use PostgreSQL instead of SQLite for the database", "turn": 2},
    {"content": "User wants Docker Compose with health checks and volume mounts", "turn": 3},
]


class ContextRetentionTask(BenchmarkTask):
    task_id = "T02"
    category = "context_retention"
    required_capability = "Multi-turn conversation context retention across episodes"
    expected_behavior = "Information from turn 1 (FastAPI) retrievable after turns 2-3 stored"

    def run(self, state) -> TaskResult:
        from core.memory.episodic import EpisodicMemory

        mem = EpisodicMemory()
        stored = 0

        # Store each turn as an episode
        for turn_data in _TURNS:
            try:
                mem.store(
                    event_type="conversation",
                    content=turn_data["content"],
                    tags=["conversation", f"turn_{turn_data['turn']}"],
                    context={"turn": turn_data["turn"], "session": "bench_t02"},
                )
                stored += 1
            except Exception as e:
                return self._failure(
                    actual=f"Failed storing turn {turn_data['turn']}: {e}",
                    outcome=f"Context broken at turn {turn_data['turn']}",
                )

        # Now query for turn 1 information — should still be accessible
        turn1_results = mem.recall("FastAPI Docker", limit=10, event_type="conversation")
        turn1_found = any("FastAPI" in r.get("content", "") for r in turn1_results)

        # Query for turn 2 — should also work
        turn2_results = mem.recall("PostgreSQL database", limit=10, event_type="conversation")
        turn2_found = any("PostgreSQL" in r.get("content", "") for r in turn2_results)

        if stored == 3 and turn1_found and turn2_found:
            return self._success(
                actual=f"All 3 turns stored. Turn 1 query: {'found' if turn1_found else 'missed'}. Turn 2 query: {'found' if turn2_found else 'missed'}.",
                outcome="Context retained across all turns",
                details={"stored": stored, "turn1_found": turn1_found, "turn2_found": turn2_found},
            )
        else:
            return self._failure(
                actual=f"Stored {stored}/3. Turn 1: {'found' if turn1_found else 'MISSED'}. Turn 2: {'found' if turn2_found else 'MISSED'}.",
                outcome="Context not fully retained",
                details={"stored": stored, "turn1_found": turn1_found, "turn2_found": turn2_found},
            )


TASK_CLASS = ContextRetentionTask
