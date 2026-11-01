"""Read-only status report over the laya_log decisions.jsonl.

Run directly: `python laya_status.py` prints a report on the real default
log (or whatever VECTOR_LAYA_LOG_PATH points at). Pass --log-path to point
at a different file. This module never writes to the log; it only reads.

Deliberate deviation from this package's usual "bare invocation runs the
self-test" convention: this file's whole purpose is to be run bare and
print a real report, so bare invocation does that instead. Use
--self-test to run the self-test.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from laya_log import read_decisions


def _routing_override_stats(rows: list[dict[str, Any]]) -> dict[str, int]:
    """How many routing_override rows show a real human override vs. a
    plain confirmation of what the deterministic classifier already
    picked. Override rows are the highest-signal training examples.
    """

    category_overridden = 0
    difficulty_overridden = 0
    either_overridden = 0

    for row in rows:
        choice = row.get("choice") or {}
        meta = row.get("meta") or {}

        category_changed = (
            bool(meta.get("task_category_was_explicit"))
            and choice.get("task_category") != meta.get("auto_task_category")
        )
        difficulty_changed = (
            choice.get("difficulty") != meta.get("auto_difficulty")
        )

        if category_changed:
            category_overridden += 1
        if difficulty_changed:
            difficulty_overridden += 1
        if category_changed or difficulty_changed:
            either_overridden += 1

    return {
        "total": len(rows),
        "category_overridden": category_overridden,
        "difficulty_overridden": difficulty_overridden,
        "either_overridden": either_overridden,
        "confirmed_only": len(rows) - either_overridden,
    }


def _bool_choice_stats(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(rows),
        "true": sum(1 for row in rows if row.get("choice") is True),
        "false": sum(1 for row in rows if row.get("choice") is False),
    }


def _urgency_stats(rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    values = [
        row["choice"] for row in rows
        if isinstance(row.get("choice"), (int, float))
    ]

    if not values:
        return {"total": 0, "min": None, "max": None, "avg": None}

    return {
        "total": len(values),
        "min": min(values),
        "max": max(values),
        "avg": sum(values) / len(values),
    }


def build_report(rows: list[dict[str, Any]]) -> str:
    by_schema: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        by_schema.setdefault(row.get("schema", "unknown"), []).append(row)

    lines: list[str] = []
    lines.append(f"Total logged decisions: {len(rows)}")
    lines.append("")
    lines.append("By schema:")

    for schema in sorted(by_schema):
        lines.append(f"  {schema}: {len(by_schema[schema])}")

    lines.append("")

    if "routing_override" in by_schema:
        stats = _routing_override_stats(by_schema["routing_override"])
        lines.append("routing_override detail:")
        lines.append(f"  total: {stats['total']}")
        lines.append(
            "  category overridden (explicit + differs from auto): "
            f"{stats['category_overridden']}"
        )
        lines.append(
            "  difficulty overridden (final differs from auto default): "
            f"{stats['difficulty_overridden']}"
        )
        lines.append(
            "  either overridden (highest-signal for training): "
            f"{stats['either_overridden']}"
        )
        lines.append(
            f"  confirmed only (matched auto-classifier): {stats['confirmed_only']}"
        )
        lines.append("")

    if "guard_screen" in by_schema:
        stats = _bool_choice_stats(by_schema["guard_screen"])
        lines.append("guard_screen detail:")
        lines.append(f"  flagged: {stats['true']}   clean: {stats['false']}")
        lines.append("")

    if "task_urgency" in by_schema:
        stats = _urgency_stats(by_schema["task_urgency"])
        lines.append("task_urgency detail:")
        lines.append(
            f"  n={stats['total']}  min={stats['min']}  "
            f"max={stats['max']}  avg={stats['avg']}"
        )
        lines.append("")

    if "approval_resolution" in by_schema:
        stats = _bool_choice_stats(by_schema["approval_resolution"])
        lines.append("approval_resolution detail:")
        lines.append(
            f"  approved (True): {stats['true']}   "
            f"needs_human (False): {stats['false']}"
        )
        lines.append("")

    if "completion_review_required" in by_schema:
        stats = _bool_choice_stats(by_schema["completion_review_required"])
        lines.append("completion_review_required detail:")
        lines.append(
            f"  required review (True): {stats['true']}   "
            f"clean (False): {stats['false']}"
        )
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="laya_status.py",
        description="Report on logged Laya decision-training examples.",
    )
    parser.add_argument(
        "--log-path", type=Path, default=None,
        help="Path to decisions.jsonl (defaults to VECTOR_LAYA_LOG_PATH env "
        "var, or this package's .state/laya/decisions.jsonl).",
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run this module's self-test instead of printing a report.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        _self_test()
        return 0

    rows = read_decisions(log_path=args.log_path)
    print(build_report(rows))
    return 0


def _self_test() -> None:
    import os
    import shutil
    import tempfile

    from laya_log import log_decision

    temp_dir = Path(tempfile.mkdtemp(prefix="vector_laya_status_test_"))
    temp_path = temp_dir / "decisions.jsonl"

    try:
        assert build_report([]) == "Total logged decisions: 0\n\nBy schema:\n"

        log_decision(
            schema="routing_override", state="a", question="q",
            choice={"task_category": "debugging", "difficulty": "serious"},
            meta={
                "auto_task_category": "implementation",
                "auto_difficulty": "routine",
                "task_category_was_explicit": True,
            },
            log_path=temp_path,
        )
        log_decision(
            schema="routing_override", state="b", question="q",
            choice={"task_category": "implementation", "difficulty": "routine"},
            meta={
                "auto_task_category": "implementation",
                "auto_difficulty": "routine",
                "task_category_was_explicit": False,
            },
            log_path=temp_path,
        )
        log_decision(
            schema="guard_screen", state="c", question="q", choice=True,
            meta={"reasons": ["ignore previous instructions"]},
            log_path=temp_path,
        )
        log_decision(
            schema="task_urgency", state="d", question="q", choice=0.8,
            log_path=temp_path,
        )
        log_decision(
            schema="approval_resolution", state="e", question="q", choice=True,
            meta={"trigger": "approve_task"}, log_path=temp_path,
        )
        log_decision(
            schema="completion_review_required", state="f", question="q",
            choice=False, meta={"risk": "low"}, log_path=temp_path,
        )

        rows = read_decisions(log_path=temp_path)
        assert len(rows) == 6

        report = build_report(rows)
        assert "Total logged decisions: 6" in report
        assert "  routing_override: 2" in report
        assert "either overridden (highest-signal for training): 1" in report
        assert "confirmed only (matched auto-classifier): 1" in report
        assert "flagged: 1   clean: 0" in report
        assert "n=1  min=0.8  max=0.8  avg=0.8" in report
        assert "approved (True): 1   needs_human (False): 0" in report
        assert "required review (True): 0   clean (False): 1" in report

        os.environ["VECTOR_LAYA_LOG_PATH"] = str(temp_path)
        try:
            assert main([]) == 0
        finally:
            del os.environ["VECTOR_LAYA_LOG_PATH"]

        assert main(["--log-path", str(temp_path)]) == 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
