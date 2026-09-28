"""An agent that dies from failures must leave those failures in its ghost memory.

Found 2026-09-25: of 1,246 `agent_history` rows only 13 were real HP-0 deaths, and every
one had `lessons_learned: []` and `best_decisions: []`. The ghost->successor pipeline
is real (`agent_registry.deregister`), but it only carries `agent.lessons`, and nothing
put anything in there when HP was lost -- the exact moment that kills an agent. So the
next generation inherited nothing about what went wrong.
"""
import uuid

from core.city.agent_base import AgentBase


def _agent(hp=500):
    a = AgentBase(str(uuid.uuid4()), "GhostTester", "qa")
    a.health_points = hp
    return a


def test_a_failure_is_remembered_as_a_lesson():
    a = _agent()
    a.deduct_points(30, "task_failed_parse_error")
    assert any("task_failed_parse_error" in str(lesson) for lesson in a.lessons)


def test_a_repeated_failure_is_stored_once_not_twenty_times():
    a = _agent()
    for _ in range(10):
        a.deduct_points(5, "task_failed_parse_error")
    assert sum("task_failed_parse_error" in str(lesson) for lesson in a.lessons) == 1


def test_distinct_failures_are_all_kept_within_the_cap():
    a = _agent()
    for i in range(30):
        a.deduct_points(1, f"failure_{i}")
    assert len(a.lessons) == 20
    assert "failure_29" in str(a.lessons[-1])


def test_death_leaves_a_ghost_that_says_what_killed_the_agent():
    a = _agent(hp=40)
    result = a.deduct_points(30, "output_ignored_3x")
    assert not result["died"]
    result = a.deduct_points(50, "critical_error_in_task")
    assert result["died"]
    lessons = " ".join(str(x) for x in result["ghost"]["lessons_learned"])
    assert "output_ignored_3x" in lessons
    assert "critical_error_in_task" in lessons


def test_successor_inherits_the_failure_lessons():
    dead = _agent(hp=10)
    ghost = dead.deduct_points(50, "critical_error_in_task")["ghost"]
    heir = _agent()
    heir.inherit_ghost(ghost)
    assert any("critical_error_in_task" in str(x) for x in heir.lessons)
