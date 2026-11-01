"""Mission planning and sequential execution for VECTOR.

Phase 4 builds on the single-action executor. A mission is an ordered list of
gateway-protected actions. Execution stops on the first blocked or failed step
so VECTOR does not drift into unverified autonomy.
"""

from __future__ import annotations

import datetime
import asyncio
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from core.loop.permission_gateway import PermissionGateway
from core.runtime.executor import AutonomousExecutor
from core.runtime_paths import data_path


ACTIVE_STATUSES = {"planned", "running"}


@dataclass
class MissionStep:
    id: str
    action_type: str
    params: dict[str, Any] = field(default_factory=dict)
    status: str = "planned"
    report: dict[str, Any] | None = None
    reason: str = ""
    source: str = "explicit"
    confidence: float = 1.0
    requires_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MissionEvent:
    id: str
    type: str
    timestamp: str
    message: str
    step_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MissionArtifact:
    id: str
    type: str
    title: str
    created_at: str
    step_id: str = ""
    content: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MissionRecoveryPolicy:
    max_retries: int = 1
    retry_count: int = 0
    rollback_status: str = "not_requested"
    rollback_reason: str = ""
    last_retry_at: str = ""
    last_rollback_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Mission:
    id: str
    objective: str
    proposed_by: str
    status: str
    steps: list[MissionStep]
    created_at: str
    updated_at: str
    reason: str = ""
    review_required: bool = False
    decomposition: dict[str, Any] = field(default_factory=dict)
    job_id: str = ""
    progress: float = 0.0
    events: list[MissionEvent] = field(default_factory=list)
    artifacts: list[MissionArtifact] = field(default_factory=list)
    recovery: MissionRecoveryPolicy = field(default_factory=MissionRecoveryPolicy)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [step.to_dict() for step in self.steps]
        data["events"] = [event.to_dict() for event in self.events]
        data["artifacts"] = [artifact.to_dict() for artifact in self.artifacts]
        data["recovery"] = self.recovery.to_dict()
        return data

    def record_event(
        self,
        event_type: str,
        message: str,
        step_id: str = "",
        data: dict[str, Any] | None = None,
    ) -> MissionEvent:
        event = MissionEvent(
            id=uuid.uuid4().hex[:10],
            type=event_type,
            timestamp=MissionRunner._now(),
            message=message,
            step_id=step_id,
            data=data or {},
        )
        self.events.append(event)
        return event

    def add_artifact(
        self,
        artifact_type: str,
        title: str,
        content: dict[str, Any],
        step_id: str = "",
    ) -> MissionArtifact:
        artifact = MissionArtifact(
            id=uuid.uuid4().hex[:10],
            type=artifact_type,
            title=title,
            created_at=MissionRunner._now(),
            step_id=step_id,
            content=content,
        )
        self.artifacts.append(artifact)
        return artifact


def _mission_event_from_dict(data: dict[str, Any]) -> MissionEvent:
    return MissionEvent(
        id=str(data.get("id") or uuid.uuid4().hex[:10]),
        type=str(data.get("type") or "event"),
        timestamp=str(data.get("timestamp") or MissionRunner._now()),
        message=str(data.get("message") or ""),
        step_id=str(data.get("step_id") or ""),
        data=data.get("data") if isinstance(data.get("data"), dict) else {},
    )


def _mission_artifact_from_dict(data: dict[str, Any]) -> MissionArtifact:
    return MissionArtifact(
        id=str(data.get("id") or uuid.uuid4().hex[:10]),
        type=str(data.get("type") or "result"),
        title=str(data.get("title") or "Artifact"),
        created_at=str(data.get("created_at") or MissionRunner._now()),
        step_id=str(data.get("step_id") or ""),
        content=data.get("content") if isinstance(data.get("content"), dict) else {},
    )


def _mission_recovery_from_dict(data: dict[str, Any]) -> MissionRecoveryPolicy:
    return MissionRecoveryPolicy(
        max_retries=int(data.get("max_retries", 1) or 0),
        retry_count=int(data.get("retry_count", 0) or 0),
        rollback_status=str(data.get("rollback_status") or "not_requested"),
        rollback_reason=str(data.get("rollback_reason") or ""),
        last_retry_at=str(data.get("last_retry_at") or ""),
        last_rollback_at=str(data.get("last_rollback_at") or ""),
    )


def _mission_step_from_dict(data: dict[str, Any]) -> MissionStep:
    return MissionStep(
        id=str(data.get("id") or "step-1"),
        action_type=str(data.get("action_type") or "respond"),
        params=data.get("params") if isinstance(data.get("params"), dict) else {},
        status=str(data.get("status") or "planned"),
        report=data.get("report") if isinstance(data.get("report"), dict) else None,
        reason=str(data.get("reason") or ""),
        source=str(data.get("source") or "explicit"),
        confidence=float(data.get("confidence", 1.0) or 0.0),
        requires_review=bool(data.get("requires_review", False)),
    )


def _mission_from_dict(data: dict[str, Any]) -> Mission:
    steps_data = data.get("steps") if isinstance(data.get("steps"), list) else []
    steps = [
        _mission_step_from_dict(step)
        for step in steps_data
        if isinstance(step, dict)
    ]
    if not steps:
        steps = [MissionStep(id="step-1", action_type="respond")]
    return Mission(
        id=str(data.get("id") or uuid.uuid4().hex[:12]),
        objective=str(data.get("objective") or ""),
        proposed_by=str(data.get("proposed_by") or "api.missions"),
        status=str(data.get("status") or "planned"),
        steps=steps,
        created_at=str(data.get("created_at") or MissionRunner._now()),
        updated_at=str(data.get("updated_at") or MissionRunner._now()),
        reason=str(data.get("reason") or ""),
        review_required=bool(data.get("review_required", False)),
        decomposition=data.get("decomposition")
        if isinstance(data.get("decomposition"), dict)
        else {},
        job_id=str(data.get("job_id") or ""),
        progress=float(data.get("progress", 0.0) or 0.0),
        events=[
            _mission_event_from_dict(event)
            for event in (data.get("events") if isinstance(data.get("events"), list) else [])
            if isinstance(event, dict)
        ],
        artifacts=[
            _mission_artifact_from_dict(artifact)
            for artifact in (
                data.get("artifacts") if isinstance(data.get("artifacts"), list) else []
            )
            if isinstance(artifact, dict)
        ],
        recovery=_mission_recovery_from_dict(data.get("recovery"))
        if isinstance(data.get("recovery"), dict)
        else MissionRecoveryPolicy(),
    )


@dataclass
class MissionJob:
    id: str
    mission_id: str
    status: str
    dry_run: bool
    created_at: str
    updated_at: str
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MissionStore:
    """Restart-safe mission registry backed by a compact JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self._missions: dict[str, Mission] = {}
        self._path = path
        self._loaded = False

    @property
    def path(self) -> Path:
        return self._path or data_path("missions", "missions.json")

    def add(self, mission: Mission) -> Mission:
        self._ensure_loaded()
        self._missions[mission.id] = mission
        self.save()
        return mission

    def get(self, mission_id: str) -> Mission | None:
        self._ensure_loaded()
        return self._missions.get(mission_id)

    def list(self, limit: int = 20) -> list[Mission]:
        self._ensure_loaded()
        missions = sorted(self._missions.values(), key=lambda m: m.updated_at, reverse=True)
        return missions[: max(1, min(limit, 100))]

    def clear(self, persist: bool = False) -> None:
        self._missions.clear()
        self._loaded = True
        if persist:
            self.save()

    def save(self) -> None:
        payload = {
            "version": 1,
            "missions": [mission.to_dict() for mission in self._missions.values()],
        }
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        # Windows: os.replace (Path.replace) raises PermissionError [WinError 5]
        # if the destination is momentarily held open by another reader (a real
        # race under concurrent access). Retry a few times with a short backoff
        # before giving up — atomic-rename semantics are preserved on success.
        import time as _time
        for _attempt in range(5):
            try:
                tmp_path.replace(path)
                return
            except PermissionError:
                if _attempt == 4:
                    raise
                _time.sleep(0.05)

    def reload(self) -> None:
        self._missions.clear()
        self._loaded = False
        self._ensure_loaded()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        path = self.path
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = raw.get("missions", []) if isinstance(raw, dict) else []
            if not isinstance(items, list):
                return
            for item in items:
                if not isinstance(item, dict):
                    continue
                mission = _mission_from_dict(item)
                self._missions[mission.id] = mission
        except Exception:
            self._missions.clear()


MISSION_STORE = MissionStore()


class MissionJobStore:
    """In-process background mission job registry."""

    def __init__(self) -> None:
        self._jobs: dict[str, MissionJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def submit(self, mission: Mission, runner: "MissionRunner", dry_run: bool = False) -> MissionJob:
        job = MissionJob(
            id=uuid.uuid4().hex[:10],
            mission_id=mission.id,
            status="queued",
            dry_run=dry_run,
            created_at=MissionRunner._now(),
            updated_at=MissionRunner._now(),
        )
        self._jobs[job.id] = job
        mission.job_id = job.id
        mission.status = "queued"
        mission.reason = "Mission queued for background execution."
        mission.record_event("job_queued", mission.reason, data={"job_id": job.id})
        mission.updated_at = MissionRunner._now()
        runner.store.save()
        try:
            task = asyncio.create_task(self.run_job(job.id, runner))
            self._tasks[job.id] = task
        except RuntimeError as exc:
            job.status = "failed"
            job.error = f"No running event loop: {exc}"
            job.updated_at = MissionRunner._now()
            mission.status = "failed"
            mission.reason = job.error
            mission.record_event("job_failed", job.error, data={"job_id": job.id})
            runner.store.save()
        return job

    async def run_job(self, job_id: str, runner: "MissionRunner") -> MissionJob:
        job = self._jobs[job_id]
        job.status = "running"
        job.updated_at = MissionRunner._now()
        mission = runner.store.get(job.mission_id)
        if mission is None:
            job.status = "failed"
            job.error = f"Mission {job.mission_id!r} not found"
            job.updated_at = MissionRunner._now()
            return job
        mission.record_event("job_started", "Background mission job started.", data={"job_id": job.id})
        runner.store.save()
        try:
            result = await runner.run(mission, dry_run=job.dry_run)
            job.result = result.to_dict()
            job.status = "completed" if result.status in ("completed", "planned") else result.status
            job.updated_at = MissionRunner._now()
            mission.record_event(
                "job_finished",
                f"Background mission job finished with status {job.status}.",
                data={"job_id": job.id, "status": job.status},
            )
            runner.store.save()
            return job
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.updated_at = MissionRunner._now()
            mission.status = "failed"
            mission.reason = f"Background mission failed: {exc}"
            mission.record_event("job_failed", mission.reason, data={"job_id": job.id})
            mission.updated_at = MissionRunner._now()
            runner.store.save()
            return job

    def get(self, job_id: str) -> MissionJob | None:
        return self._jobs.get(job_id)

    def list(self, limit: int = 20) -> list[MissionJob]:
        jobs = sorted(self._jobs.values(), key=lambda j: j.updated_at, reverse=True)
        return jobs[: max(1, min(limit, 100))]

    def clear(self) -> None:
        self._jobs.clear()
        self._tasks.clear()


MISSION_JOBS = MissionJobStore()


RISKY_OBJECTIVE_TERMS = {
    "delete",
    "wipe",
    "format",
    "erase",
    "transfer",
    "payment",
    "pay ",
    "buy ",
    "sell ",
    "trade",
    "deploy",
    "email",
    "message",
    "password",
    "secret",
    "key rotate",
    "revoke key",
}


class ObjectiveDecomposer:
    """Conservative rule-based objective-to-step translator.

    The point is not to be clever. It gives VECTOR a safe first pass at
    decomposition while refusing to infer dangerous actions.
    """

    def decompose(self, objective: str, max_steps: int = 8) -> dict[str, Any]:
        text = " ".join(str(objective or "").strip().split())
        lowered = text.lower()
        max_steps = max(1, min(max_steps, 20))

        risky = sorted(term.strip() for term in RISKY_OBJECTIVE_TERMS if term in lowered)
        if risky:
            return {
                "status": "needs_review",
                "review_required": True,
                "reason": "Objective contains risky terms that require explicit reviewed steps.",
                "matched_terms": risky,
                "steps": [
                    {
                        "action_type": "respond",
                        "params": {
                            "message": (
                                "I need explicit reviewed steps before executing this mission: "
                                + text
                            )
                        },
                        "source": "decomposer_safety",
                        "confidence": 0.35,
                        "requires_review": True,
                    }
                ],
            }

        clauses = self._split_clauses(lowered)
        steps: list[dict[str, Any]] = []
        unmatched: list[str] = []
        for clause in clauses:
            mapped = self._map_clause(clause, original=text)
            if mapped is None:
                unmatched.append(clause)
                continue
            steps.append(mapped)
            if len(steps) >= max_steps:
                break

        if not steps:
            steps = [
                {
                    "action_type": "respond",
                    "params": {"message": text},
                    "source": "decomposer_fallback",
                    "confidence": 0.55,
                    "requires_review": False,
                }
            ]

        review_required = bool(unmatched)
        return {
            "status": "decomposed_with_review" if review_required else "decomposed",
            "review_required": review_required,
            "reason": (
                "Some clauses were not confidently mapped."
                if review_required
                else "Objective decomposed into safe candidate steps."
            ),
            "unmatched_clauses": unmatched,
            "steps": steps[:max_steps],
        }

    def _split_clauses(self, text: str) -> list[str]:
        normalized = text
        for sep in [" then ", " and then ", ";", "\n"]:
            normalized = normalized.replace(sep, " and ")
        return [part.strip(" .,") for part in normalized.split(" and ") if part.strip(" .,")]

    def _map_clause(self, clause: str, original: str) -> dict[str, Any] | None:
        if any(word in clause for word in ["weather", "temperature", "forecast"]):
            return {
                "action_type": "check_weather",
                "params": {"location": self._extract_location(clause) or "Kolkata"},
                "source": "decomposer_rule",
                "confidence": 0.8,
                "requires_review": False,
            }

        if any(word in clause for word in ["search", "research", "look up", "find "]):
            return {
                "action_type": "search_web",
                "params": {"query": self._clean_query(clause)},
                "source": "decomposer_rule",
                "confidence": 0.78,
                "requires_review": False,
            }

        if "timer" in clause or "countdown" in clause:
            return {
                "action_type": "set_timer",
                "params": {"duration_sec": self._extract_duration_seconds(clause)},
                "source": "decomposer_rule",
                "confidence": 0.75,
                "requires_review": False,
            }

        if "remind" in clause or "reminder" in clause:
            return {
                "action_type": "set_reminder",
                "params": {"text": clause},
                "source": "decomposer_rule",
                "confidence": 0.7,
                "requires_review": True,
            }

        if any(word in clause for word in ["summarize", "explain", "answer", "tell me"]):
            return {
                "action_type": "respond",
                "params": {"message": original},
                "source": "decomposer_rule",
                "confidence": 0.65,
                "requires_review": False,
            }

        return None

    @staticmethod
    def _clean_query(clause: str) -> str:
        query = clause
        for prefix in ["search for", "search", "research", "look up", "find"]:
            if query.startswith(prefix):
                query = query[len(prefix) :].strip()
        return query or clause

    @staticmethod
    def _extract_location(clause: str) -> str | None:
        for marker in [" in ", " at ", " for "]:
            if marker in clause:
                value = clause.split(marker, 1)[1].strip(" .")
                return value.title() if value else None
        return None

    @staticmethod
    def _extract_duration_seconds(clause: str) -> int:
        import re

        match = re.search(r"(\d+)\s*(second|sec|minute|min|hour|hr)s?", clause)
        if not match:
            return 60
        amount = int(match.group(1))
        unit = match.group(2)
        if unit.startswith(("hour", "hr")):
            return amount * 3600
        if unit.startswith(("minute", "min")):
            return amount * 60
        return amount


class MissionPlanAdvisor:
    """Local-model advisory planner with conservative fallback behavior."""

    SYSTEM_PROMPT = (
        "You are VECTOR's mission planning advisor. Return only compact JSON with "
        "a 'steps' array. Each step must have action_type, params, reason, and "
        "confidence. Prefer safe read-only or response actions. Do not claim that "
        "approval has been granted."
    )

    def __init__(
        self,
        permission_gateway: PermissionGateway | None = None,
        chat_fn: Callable[..., str] | None = None,
        model: str | None = None,
        decomposer: ObjectiveDecomposer | None = None,
    ) -> None:
        self.permission_gateway = permission_gateway
        self.chat_fn = chat_fn
        self.model = model
        self.decomposer = decomposer or ObjectiveDecomposer()

    def advise(self, objective: str, max_steps: int = 8) -> dict[str, Any]:
        text = " ".join(str(objective or "").strip().split())
        max_steps = max(1, min(max_steps, 20))
        fallback = self.decomposer.decompose(text, max_steps=max_steps)
        response = self._call_model(text, max_steps=max_steps)
        if not response:
            return self._with_planner_metadata(
                fallback,
                source="rule_fallback",
                reason="Local LLM planner unavailable; used conservative rule-based decomposition.",
                fallback_used=True,
            )

        parsed = self._parse_json(response)
        raw_steps = parsed.get("steps") if isinstance(parsed, dict) else None
        if not isinstance(raw_steps, list):
            return self._with_planner_metadata(
                fallback,
                source="parse_fallback",
                reason="Local LLM planner returned unparseable steps; used conservative rule-based decomposition.",
                fallback_used=True,
                raw_response=response[:1200],
            )

        steps = self._sanitize_steps(raw_steps, max_steps=max_steps)
        if not steps:
            return self._with_planner_metadata(
                fallback,
                source="empty_fallback",
                reason="Local LLM planner returned no usable steps; used conservative rule-based decomposition.",
                fallback_used=True,
                raw_response=response[:1200],
            )

        review_required = any(step.get("requires_review") for step in steps)
        status = "llm_decomposed_with_review" if review_required else "llm_decomposed"
        reason = (
            "Local LLM produced candidate steps; non-GREEN or low-confidence steps require review."
            if review_required
            else "Local LLM produced GREEN-classified candidate steps."
        )
        return {
            "status": status,
            "review_required": review_required,
            "reason": reason,
            "planner": {
                "source": "local_llm",
                "model": self._model_name(),
                "fallback_used": False,
            },
            "steps": steps,
        }

    def _call_model(self, objective: str, max_steps: int) -> str:
        try:
            chat_fn = self.chat_fn
            _kwargs = {}
            if chat_fn is None:
                from core.inference.ollama_safe import chat as chat_fn
                _kwargs["caller_id"] = "runtime_missions_planner"

            objective_prompt = (
                f"Objective: {objective}\n"
                f"Maximum steps: {max_steps}\n"
                "Return JSON only, for example: "
                '{"steps":[{"action_type":"respond","params":{"message":"..."},'
                '"reason":"why","confidence":0.8}]}'
            )
            # RULE 1: session_hydration_prompt() before every LLM call.
            from core.loop.context_engine import ContextEngine
            hydration = ContextEngine().session_hydration_prompt({"query": objective_prompt})
            messages = [
                {"role": "system", "content": hydration},
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": objective_prompt},
            ]
            return str(chat_fn(model=self._model_name(), messages=messages, timeout=20.0, **_kwargs) or "")
        except Exception:
            return ""

    def _model_name(self) -> str:
        if self.model:
            return self.model
        try:
            from core.config import CONFIG

            return str(CONFIG.get("models", {}).get("reasoning") or "vector-reasoning")
        except Exception:
            return "vector-reasoning"

    def _parse_json(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.S)
        if fenced:
            cleaned = fenced.group(1)
        elif not cleaned.startswith("{"):
            match = re.search(r"\{.*\}", cleaned, flags=re.S)
            cleaned = match.group(0) if match else cleaned
        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _sanitize_steps(self, raw_steps: list[Any], max_steps: int) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        for item in raw_steps[:max_steps]:
            if not isinstance(item, dict):
                continue
            action_type = str(item.get("action_type") or item.get("action") or "").strip()
            if not action_type or len(action_type) > 80:
                continue
            params = item.get("params") if isinstance(item.get("params"), dict) else {}
            confidence = self._confidence(item.get("confidence", 0.55))
            risk_level = self._classify(action_type)
            requires_review = bool(item.get("requires_review")) or risk_level != "GREEN" or confidence < 0.7
            steps.append(
                {
                    "action_type": action_type,
                    "params": params,
                    "source": "llm_planner",
                    "confidence": confidence,
                    "requires_review": requires_review,
                    "reason": str(item.get("reason") or "Suggested by local LLM planner.")[:500],
                    "safety_level": risk_level,
                }
            )
        return steps

    def _classify(self, action_type: str) -> str:
        gateway = self.permission_gateway or PermissionGateway()
        try:
            return str(gateway._classify(action_type))
        except Exception:
            return "UNKNOWN"

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            return round(max(0.0, min(1.0, float(value))), 3)
        except Exception:
            return 0.55

    @staticmethod
    def _with_planner_metadata(
        decomposition: dict[str, Any],
        source: str,
        reason: str,
        fallback_used: bool,
        raw_response: str = "",
    ) -> dict[str, Any]:
        data = dict(decomposition)
        data["reason"] = reason
        data["planner"] = {
            "source": source,
            "model": "",
            "fallback_used": fallback_used,
        }
        if raw_response:
            data["planner"]["raw_response"] = raw_response
        return data


class MissionRunner:
    def __init__(
        self,
        permission_gateway: PermissionGateway | None = None,
        app_state: Any | None = None,
        store: MissionStore | None = None,
    ) -> None:
        self.permission_gateway = permission_gateway
        self.app_state = app_state
        self.store = store or MISSION_STORE

    def plan(
        self,
        objective: str,
        steps: list[dict[str, Any]] | None = None,
        proposed_by: str = "api.missions",
        max_steps: int = 8,
        decompose: bool = False,
        llm_plan: bool = False,
    ) -> Mission:
        now = self._now()
        decomposition: dict[str, Any] = {}
        if decompose and not steps:
            if llm_plan:
                decomposition = MissionPlanAdvisor(
                    permission_gateway=self.permission_gateway,
                ).advise(objective, max_steps=max_steps)
            else:
                decomposition = ObjectiveDecomposer().decompose(objective, max_steps=max_steps)
            steps = decomposition.get("steps", [])
        normalized = self._normalize_steps(objective, steps, max_steps=max_steps)
        mission = Mission(
            id=uuid.uuid4().hex[:12],
            objective=objective,
            proposed_by=proposed_by,
            status="planned",
            steps=normalized,
            created_at=now,
            updated_at=now,
            reason=decomposition.get("reason", "Mission planned."),
            review_required=bool(decomposition.get("review_required", False)),
            decomposition=decomposition,
        )
        mission.record_event(
            "planned",
            "Mission planned.",
            data={"step_count": len(mission.steps), "decomposed": bool(decomposition)},
        )
        return self.store.add(mission)

    async def run(
        self,
        mission: Mission,
        dry_run: bool = False,
    ) -> Mission:
        mission.status = "running" if not dry_run else "planned"
        mission.progress = 0.0
        mission.updated_at = self._now()
        mission.record_event(
            "dry_run_started" if dry_run else "run_started",
            "Mission dry run started." if dry_run else "Mission execution started.",
        )
        self.store.save()
        executor = AutonomousExecutor(
            permission_gateway=self.permission_gateway,
            app_state=self.app_state,
        )

        total_steps = max(1, len(mission.steps))
        for idx, step in enumerate(mission.steps, start=1):
            if step.status not in ACTIVE_STATUSES:
                continue
            mission.record_event(
                "step_started",
                f"Step {step.id} started: {step.action_type}.",
                step_id=step.id,
                data={"action_type": step.action_type, "index": idx},
            )
            report = await executor.execute(
                action_type=step.action_type,
                params=step.params,
                proposed_by=mission.proposed_by,
                dry_run=dry_run,
            )
            step.report = report.to_dict()
            step.status = report.status
            step.reason = report.reason
            mission.progress = round(idx / total_steps, 3)
            mission.updated_at = self._now()
            mission.record_event(
                "step_" + ("completed" if report.status == "executed" else report.status),
                f"Step {step.id} {report.status}: {report.reason}",
                step_id=step.id,
                data={"status": report.status, "checks": report.verification.get("checks", [])},
            )
            self._capture_artifact(mission, step, report.to_dict())
            self.store.save()
            if report.status != "executed" and not dry_run:
                mission.status = "blocked" if report.status == "blocked" else "failed"
                mission.reason = f"Stopped at step {step.id}: {report.reason}"
                mission.progress = round(idx / total_steps, 3)
                mission.record_event(
                    mission.status,
                    mission.reason,
                    step_id=step.id,
                    data={"progress": mission.progress},
                )
                self.store.save()
                return mission

        if dry_run:
            mission.status = "planned"
            mission.reason = "Dry run completed. No actions executed."
            mission.progress = 1.0
            mission.record_event("dry_run_completed", mission.reason, data={"progress": 1.0})
        else:
            mission.status = "completed"
            mission.reason = "All mission steps executed and verified."
            mission.progress = 1.0
            mission.record_event("completed", mission.reason, data={"progress": 1.0})
        mission.updated_at = self._now()
        self.store.save()
        return mission

    async def retry(self, mission: Mission) -> Mission:
        if mission.status not in {"blocked", "failed"}:
            mission.record_event(
                "retry_skipped",
                f"Retry skipped because mission status is {mission.status}.",
            )
            self.store.save()
            return mission
        if mission.recovery.retry_count >= mission.recovery.max_retries:
            mission.record_event(
                "retry_denied",
                "Retry denied: retry budget exhausted.",
                data={
                    "retry_count": mission.recovery.retry_count,
                    "max_retries": mission.recovery.max_retries,
                },
            )
            self.store.save()
            return mission

        mission.recovery.retry_count += 1
        mission.recovery.last_retry_at = self._now()
        retry_from = None
        for step in mission.steps:
            if step.status in {"blocked", "failed"}:
                retry_from = step.id
                step.status = "planned"
                step.reason = ""
                step.report = None
                break
        if retry_from is None:
            retry_from = "step-1"
            for step in mission.steps:
                step.status = "planned"
                step.reason = ""
                step.report = None

        mission.status = "planned"
        mission.reason = f"Retry {mission.recovery.retry_count} scheduled from {retry_from}."
        mission.record_event(
            "retry_scheduled",
            mission.reason,
            step_id=retry_from,
            data={
                "retry_count": mission.recovery.retry_count,
                "max_retries": mission.recovery.max_retries,
            },
        )
        self.store.save()
        return await self.run(mission, dry_run=False)

    def request_rollback(self, mission: Mission, reason: str = "") -> Mission:
        mission.recovery.rollback_status = "requested"
        mission.recovery.rollback_reason = reason or "Manual rollback requested."
        mission.recovery.last_rollback_at = self._now()
        mission.status = "rollback_requested"
        mission.reason = mission.recovery.rollback_reason
        compensating = []
        for artifact in reversed(mission.artifacts):
            compensating.append(
                {
                    "artifact_id": artifact.id,
                    "step_id": artifact.step_id,
                    "type": artifact.type,
                    "title": artifact.title,
                    "action": "manual_review_required",
                }
            )
        mission.add_artifact(
            artifact_type="rollback_plan",
            title="Rollback review plan",
            content={
                "status": "manual_review_required",
                "reason": mission.recovery.rollback_reason,
                "compensating_actions": compensating,
            },
        )
        mission.record_event(
            "rollback_requested",
            mission.recovery.rollback_reason,
            data={"compensating_actions": len(compensating)},
        )
        self.store.save()
        return mission

    def _capture_artifact(self, mission: Mission, step: MissionStep, report: dict[str, Any]) -> None:
        result = report.get("result") if isinstance(report.get("result"), dict) else {}
        if not result:
            return
        artifact_payload = {
            key: value
            for key, value in result.items()
            if key not in {"timestamp", "params"}
        }
        if not artifact_payload:
            return
        artifact_type = str(artifact_payload.get("status") or "result")
        mission.add_artifact(
            artifact_type=artifact_type,
            title=f"{step.action_type} result",
            content=artifact_payload,
            step_id=step.id,
        )

    def _normalize_steps(
        self,
        objective: str,
        steps: list[dict[str, Any]] | None,
        max_steps: int,
    ) -> list[MissionStep]:
        raw_steps = steps or []
        if not raw_steps:
            raw_steps = [{"action_type": "respond", "params": {"message": objective}}]

        normalized: list[MissionStep] = []
        for idx, item in enumerate(raw_steps[: max(1, min(max_steps, 20))], start=1):
            action_type = str(item.get("action_type") or item.get("action") or "").strip()
            if not action_type:
                action_type = "respond"
            params = item.get("params") if isinstance(item.get("params"), dict) else {}
            normalized.append(
                MissionStep(
                    id=f"step-{idx}",
                    action_type=action_type,
                    params=params,
                    source=str(item.get("source") or "explicit"),
                    confidence=float(item.get("confidence", 1.0) or 0.0),
                    requires_review=bool(item.get("requires_review", False)),
                )
            )
        return normalized

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()
