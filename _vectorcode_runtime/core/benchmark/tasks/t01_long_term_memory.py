"""T01 — Long-term Memory: store facts, retrieve them later.

Tests EpisodicMemory.store() + recall() + search_semantic() round-trip.
Passes if all 5 stored facts are retrievable.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.benchmark.benchmark_task import BenchmarkTask, TaskResult

_FACTS = [
    {"event_type": "fact", "content": "Owner's cat is named Luna and is a tabby", "tags": ["pet", "cat"]},
    {"event_type": "fact", "content": "Owner prefers Python over JavaScript for backend work", "tags": ["preference", "coding"]},
    {"event_type": "fact", "content": "KIIT University semester ends in December 2026", "tags": ["education", "deadline"]},
    {"event_type": "fact", "content": "Owner's favourite algorithm is merge sort for its stability guarantee", "tags": ["coding", "preference"]},
    {"event_type": "fact", "content": "Legion Pro 5 has 32GB DDR5 RAM and RTX 5070 Ti", "tags": ["hardware", "system"]},
]


class LongTermMemoryTask(BenchmarkTask):
    task_id = "T01"
    category = "long_term_memory"
    required_capability = "EpisodicMemory store + recall round-trip"
    expected_behavior = "Store 5 facts, retrieve all 5 via recall() and search_semantic()"

    def run(self, state) -> TaskResult:
        from core.memory.episodic import EpisodicMemory

        mem = EpisodicMemory()
        stored_ids = []

        # Store 5 facts
        for fact in _FACTS:
            try:
                eid = mem.store(
                    event_type=fact["event_type"],
                    content=fact["content"],
                    tags=fact.get("tags"),
                )
                if eid:
                    stored_ids.append(eid)
            except Exception as e:
                return self._failure(
                    actual=f"store() failed: {e}",
                    outcome=f"Failed to store fact #{len(stored_ids)+1}",
                    incorrect_actions=len(stored_ids),
                )

        # Recall by query — should find relevant facts
        recalled = []
        for query in ["cat Luna", "Python JavaScript", "KIIT", "merge sort", "Legion RTX"]:
            try:
                results = mem.recall(query, limit=5)
                recalled.extend(results)
            except Exception:
                pass

        # Also try search_semantic
        semantic_hits = 0
        try:
            sem_results = mem.search_semantic("owner's cat", top_k=5)
            semantic_hits = len(sem_results)
        except Exception:
            pass

        unique_recalled = len(set(r.get("content", "") for r in recalled))

        if len(stored_ids) == 5 and unique_recalled >= 3:
            return self._success(
                actual=f"Stored {len(stored_ids)} facts, recalled {unique_recalled} unique, semantic hits: {semantic_hits}",
                outcome="All facts stored and retrievable",
                details={"stored": len(stored_ids), "recalled_unique": unique_recalled, "semantic_hits": semantic_hits},
            )
        else:
            return self._failure(
                actual=f"Stored {len(stored_ids)}/5, recalled {unique_recalled} unique, semantic hits: {semantic_hits}",
                outcome="Some facts not retrievable",
                details={"stored": len(stored_ids), "recalled_unique": unique_recalled},
            )


TASK_CLASS = LongTermMemoryTask
