"""T14 — Cross-session Continuity: data survives connection restart.

Store data in isolated DB, close connection, reopen, verify data persists.
Simulates VECTOR restart / session boundary.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.benchmark.benchmark_task import BenchmarkTask, TaskResult


class CrossSessionContinuityTask(BenchmarkTask):
    task_id = "T14"
    category = "cross_session_continuity"
    required_capability = "EpisodicMemory data persists across connection restarts (session boundaries)"
    expected_behavior = "Data stored before restart is retrievable after restart"

    def run(self, state) -> TaskResult:
        import core.memory.episodic as ep
        from core.memory.episodic import EpisodicMemory

        mem = EpisodicMemory()

        # Store data
        test_data = [
            {"event_type": "persistent_fact", "content": "Cross-session test: project deadline is Aug 20", "tags": ["benchmark"]},
            {"event_type": "persistent_fact", "content": "Cross-session test: owner meeting at 3pm Thursday", "tags": ["benchmark"]},
            {"event_type": "persistent_fact", "content": "Cross-session test: API key expires next Monday", "tags": ["benchmark"]},
        ]

        stored_ids = []
        for item in test_data:
            try:
                eid = mem.store(
                    event_type=item["event_type"],
                    content=item["content"],
                    tags=item.get("tags"),
                )
                if eid:
                    stored_ids.append(eid)
            except Exception as e:
                return self._failure(
                    actual=f"Store failed before restart: {e}",
                    outcome="Could not store initial data",
                )

        if len(stored_ids) != 3:
            return self._failure(
                actual=f"Stored {len(stored_ids)}/3 items before restart",
                outcome="Partial store before restart",
            )

        # Simulate "restart" — close the DB connection, reopen
        try:
            ep.close_db_connection()
            # Force singleton reset (like a fresh process)
            ep._db_connection = None
            ep._DB_KEY = None
            # Reopen — should connect to the same DB file
            conn = ep.get_db_connection()
        except Exception as e:
            return self._failure(
                actual=f"Restart simulation failed: {e}",
                outcome="Could not simulate session restart",
            )

        # Verify data survived restart
        mem2 = EpisodicMemory()
        recalled = mem2.recall("Cross-session test", limit=10, event_type="persistent_fact")
        recalled_contents = [r.get("content", "") for r in recalled]

        found_deadline = any("deadline" in c for c in recalled_contents)
        found_meeting = any("meeting" in c for c in recalled_contents)
        found_api = any("API key" in c for c in recalled_contents)

        all_found = found_deadline and found_meeting and found_api
        total_found = sum([found_deadline, found_meeting, found_api])

        if all_found:
            return self._success(
                actual=(
                    f"Stored 3 facts → restart (close+reopen) → retrieved {total_found}/3. "
                    f"Data survived session boundary."
                ),
                outcome="Cross-session continuity verified",
                details={
                    "stored": len(stored_ids),
                    "retrieved": total_found,
                    "deadline_found": found_deadline,
                    "meeting_found": found_meeting,
                    "api_found": found_api,
                },
            )
        else:
            return self._failure(
                actual=(
                    f"Stored 3 → restart → retrieved {total_found}/3. "
                    f"deadline={found_deadline}, meeting={found_meeting}, api={found_api}"
                ),
                outcome="Data lost across session boundary",
                details={
                    "stored": len(stored_ids),
                    "retrieved": total_found,
                },
            )


TASK_CLASS = CrossSessionContinuityTask
