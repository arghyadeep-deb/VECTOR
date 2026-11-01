"""SlackArchaeologist — deterministic Slack-history reconstruction, chief_of_staff district.

Relocated from districts/security/security_specialists.py (2026-09-29): SELF_DEV_AGENT_SPEC.md's
own district map places `slack-archaeologist` under `chief_of_staff/` (alongside
orchestrator/planner/context-loader/cross-linker/brag-spotter/people-profiler/product-*/review-*),
not security -- a placement error found and corrected on re-reading the spec's own map, not a new
decision. Moving it now (built the same night, no accumulated external dependents) is low-risk
compared to moving a long-established agent.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from core.city.agent_base import AgentBase


@dataclass(frozen=True)
class SlackArchaeologistProfile:
    name: str
    agent_id: str
    brief_action: str
    check_action: str
    required_fields: tuple[str, ...]
    deliverable: str


def _has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _check(name: str, passed: bool, evidence: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "evidence": evidence}


PROFILE = SlackArchaeologistProfile(
    "SlackArchaeologist",
    "slack_archaeologist_001",
    "slack_archaeology_brief",
    "slack_archaeology_check",
    ("channel_or_thread_ref", "messages"),
    "structured, attributed, chronologically-ordered timeline reconstruction of a "
    "Slack channel/DM/thread from caller-supplied message records",
)


class SlackArchaeologist(AgentBase):
    """Deterministic Slack-history reconstruction for incident reconstruction and evidence
    gathering: completeness, duplicate-id, and dangling-thread-reference checks over
    caller-supplied message records, plus a real chronological, attributed timeline built
    from that data -- never an LLM guess at what was said or when."""

    profile = PROFILE

    def __init__(self, generation: int = 1, ghost: dict[str, Any] | None = None) -> None:
        super().__init__(
            agent_id=self.profile.agent_id,
            name=self.profile.name,
            district="chief_of_staff",
            generation=generation,
        )
        self.capabilities = [self.profile.brief_action, self.profile.check_action]
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][slack_archaeologist] initialized {}", self.name)

    def _evidence_state(self, evidence: Any) -> tuple[dict[str, Any], list[str], list[str]]:
        supplied = evidence if isinstance(evidence, dict) else {}
        present = [field for field in self.profile.required_fields if _has_value(supplied.get(field))]
        missing = [field for field in self.profile.required_fields if field not in present]
        return supplied, present, missing

    def build_brief(self, evidence: Any) -> dict[str, Any]:
        _, present, missing = self._evidence_state(evidence)
        return {
            "persona": self.name,
            "deliverable": self.profile.deliverable,
            "status": "ready" if not missing else "needs_human",
            "required_evidence": list(self.profile.required_fields),
            "present_evidence": present,
            "missing_evidence": missing,
            "deterministic": True,
            "read_only": True,
        }

    def evaluate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        messages = evidence["messages"]
        if not isinstance(messages, list) or not messages:
            raise ValueError("messages must be a non-empty list")
        ids_seen: set[str] = set()
        duplicate_ids: list[str] = []
        missing_author_or_ts: list[str] = []
        bad_timestamps: list[str] = []
        parsed: list[tuple[datetime, dict[str, Any]]] = []
        for msg in messages:
            if not isinstance(msg, dict):
                raise ValueError("each message must be a mapping")
            mid = str(msg.get("id", ""))
            if not mid:
                raise ValueError("every message needs a non-empty id")
            if mid in ids_seen:
                duplicate_ids.append(mid)
            ids_seen.add(mid)
            author, ts_raw = msg.get("author"), msg.get("timestamp")
            if not _has_value(author) or not _has_value(ts_raw):
                missing_author_or_ts.append(mid)
                continue
            try:
                ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            except ValueError:
                bad_timestamps.append(mid)
                continue
            parsed.append((ts, msg))
        all_ids = {str(m.get("id", "")) for m in messages}
        dangling_threads = [
            str(msg.get("id", ""))
            for msg in messages
            if (parent := msg.get("thread_id") or msg.get("parent_id"))
            and str(parent) not in all_ids
            and str(parent) != str(msg.get("id", ""))
        ]
        parsed.sort(key=lambda item: item[0])
        timeline = [
            {"id": m.get("id"), "author": m.get("author"), "timestamp": ts.isoformat(), "text": m.get("text", "")}
            for ts, m in parsed
        ]
        checks = [
            _check("no_duplicate_message_ids", not duplicate_ids, duplicate_ids),
            _check("every_message_has_author_and_timestamp", not missing_author_or_ts, missing_author_or_ts),
            _check("every_timestamp_parses", not bad_timestamps, bad_timestamps),
            _check("no_dangling_thread_references", not dangling_threads, dangling_threads),
        ]
        return {
            "status": "passed" if all(item["passed"] for item in checks) else "needs_human",
            "checks": checks,
            "message_count": len(messages),
            "timeline": timeline,
            "duplicate_ids": duplicate_ids,
            "missing_author_or_timestamp": missing_author_or_ts,
            "bad_timestamps": bad_timestamps,
            "dangling_thread_references": dangling_threads,
            "missing_evidence": [],
            "deterministic": True,
            "read_only": True,
        }

    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        task_type = str(task.get("type", self.profile.brief_action))
        if task_type not in self.capabilities:
            return {
                "status": "error",
                "error": f"Unsupported task type '{task_type}' for {self.name}",
                "supported_tasks": self.capabilities,
            }
        # 2026-09-30 (Phase 3 codebase audit finding): same bug class as
        # districts/agency/agency_specialists.py (same commit series) -- the
        # real governor dispatch shape nests evidence under task["params"],
        # but this method only ever read task.get("evidence") directly,
        # already fixed once, later, in districts/marketing/
        # marketing_specialists.py but never backported here. Same fix.
        params = task.get("params") if isinstance(task.get("params"), dict) else {}
        raw_evidence = task.get("evidence") or params.get("evidence")
        try:
            evidence, _, missing = self._evidence_state(raw_evidence)
            if task_type == self.profile.brief_action or missing:
                report = self.build_brief(evidence)
            else:
                report = self.evaluate(evidence)
                report.setdefault("persona", self.name)
                report.setdefault("deliverable", self.profile.deliverable)
                report.setdefault("missing_evidence", [])
                report.setdefault("deterministic", True)
                report.setdefault("read_only", True)
            if report.get("status") in {"ready", "passed"}:
                self.award_points(10, f"{task_type}_completed")
            return {"status": "ok", "report": report}
        except (TypeError, ValueError) as exc:
            logger.warning("[VECTOR][slack_archaeologist] rejected evidence: {}", exc)
            return {
                "status": "ok",
                "report": {
                    **self.build_brief(raw_evidence),
                    "status": "needs_human",
                    "validation_error": str(exc),
                },
            }
        except Exception as exc:
            logger.error("[VECTOR][slack_archaeologist] failed: {}", exc)
            self.deduct_points(30, "slack_archaeologist_task_failed")
            return {"status": "error", "error": str(exc)}


if __name__ == "__main__":
    async def _smoke() -> None:
        agent = SlackArchaeologist()
        missing = await agent.run({"type": "slack_archaeology_check", "evidence": {}})
        assert missing["report"]["status"] == "needs_human"
        complete = await agent.run(
            {
                "type": "slack_archaeology_check",
                "evidence": {
                    "channel_or_thread_ref": "C123",
                    "messages": [
                        {"id": "a", "author": "alice", "timestamp": "2026-09-29T10:00:00Z", "text": "hi"},
                    ],
                },
            }
        )
        assert complete["report"]["status"] == "passed"
        logger.info("[VECTOR][slack_archaeologist] smoke check passed")

    asyncio.run(_smoke())
