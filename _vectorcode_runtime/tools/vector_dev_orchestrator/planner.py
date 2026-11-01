"""Bounded, read-only autonomous planner.

Turns an owner-supplied program goal into a small, ordered list of work
packages the worker can execute one by one.

  input : program goal + repo state + accepted-evidence ledger + known blockers
  output: <= max_packages WorkPackages, each with objective, scope, allowed
          mutation paths, forbidden scope, acceptance criteria, relevant
          tests, behavioral evidence required, dependencies, risk/difficulty,
          preferred implementer (only if justified), independent reviewer
          policy and stop/escalation conditions.

Division of labour:
  * a PROPOSER (a model, or a fake in tests) suggests packages as plain data;
  * this module VALIDATES them deterministically -- the proposer is never
    trusted: required fields, sane scope, safe defaults, dependency DAG,
    ledger de-duplication, approval-gate flagging and difficulty inference
    are all decided here in code.

The planner is read-only. It never edits files; the model proposer runs with
read-only tools, and the planner additionally fingerprints the working tree
around the proposer call and fails closed if anything changed.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from approval import ApprovalPolicy
from difficulty_inference import infer_difficulty
from models import Difficulty, TaskSpec
from runner import invalid_test_targets
from text_signals import norm_repo_path

MAX_PACKAGES_DEFAULT = 6
MAX_PATHS_PER_PACKAGE = 8
_PROMPT_BUDGET = 14000

# Never a legitimate mutation target for an autonomous package.
PROTECTED_PATH_PREFIXES = (
    ".git/",
    ".claude/",
    ".env",
    "docs/CODEX_VECTOR_V1_HANDOFF.md",
    "docs/VECTOR_FORENSIC_AUDIT_REPORT_2026-09-15.md",
    "docs/VECTOR_OS_LONG_TERM_VISION.md",
    "VECTOR_TECHNICAL_KNOWLEDGE/",
    "vector_memory",
)
BRIDGE_PREFIX = "tools/vector_dev_orchestrator/"

DEFAULT_FORBIDDEN_SCOPE = (
    "Do not push, merge, reset, clean, rebase or delete branches/worktrees.",
    "Do not change credentials, API keys, .env files or provider configuration.",
    "Do not add, remove or upgrade dependencies.",
    "Do not touch files outside the allowed mutation paths.",
    "Do not edit protected owner/audit documents.",
)

_STOPWORDS = frozenset(
    "a an and are as at be by for from in is it of on or that the this to with "
    "add fix make update use using new all any into via per".split()
)


class PlannerError(RuntimeError):
    """The planner could not produce a trustworthy plan."""

    # proposer invocations spent before failing (for run-budget accounting)
    calls: int = 1


class PlannerMutationError(PlannerError):
    """The read-only planning step changed the working tree."""


# --- data --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One accepted piece of work the planner must not reopen."""

    package_id: str
    title: str
    objective: str
    status: str = "accepted"
    evidence: str = ""
    commit: str = ""


@dataclass(frozen=True, slots=True)
class BlockerRecord:
    """A known blocker: work matching it is not re-proposed blindly."""

    fingerprint: str
    description: str
    count: int = 1
    # bounded, redacted failure diagnosis (category, exit code, output tail)
    evidence: str = ""


@dataclass(frozen=True, slots=True)
class WorkPackage:
    package_id: str
    title: str
    objective: str
    scope: str
    allowed_paths: tuple[str, ...]
    forbidden_scope: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    test_targets: tuple[str, ...]
    behavioral_evidence: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    risk: str = "low"
    requested_difficulty: str = Difficulty.ROUTINE.value
    inferred_difficulty: str = ""
    effective_difficulty: str = ""
    difficulty_reason: str = ""
    preferred_owner: str | None = None
    preferred_owner_reason: str = ""
    reviewer_policy: str = "independent provider (never the implementer)"
    stop_conditions: tuple[str, ...] = ()
    acceptance_critical: bool = False
    review_only: bool = False
    needs_owner: bool = False
    owner_reasons: tuple[str, ...] = ()

    @property
    def fingerprint(self) -> str:
        return fingerprint_text(self.title + " " + self.objective)

    def description(self) -> str:
        return f"{self.title}\n\n{self.objective}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PlanningInput:
    goal: str
    repo_state: dict[str, Any] = field(default_factory=dict)
    ledger: list[LedgerEntry] = field(default_factory=list)
    blockers: list[BlockerRecord] = field(default_factory=list)
    max_packages: int = MAX_PACKAGES_DEFAULT
    # validator complaints about the PREVIOUS proposal (one repair round)
    feedback: list[str] = field(default_factory=list)
    # Most proposer invocations this call may spend (1 = no repair round). The
    # supervisor sets it from the remaining provider-call budget so planning can
    # never push a program over its budget.
    max_calls: int = 2


@dataclass(slots=True)
class Plan:
    packages: list[WorkPackage] = field(default_factory=list)
    dropped: list[tuple[str, str]] = field(default_factory=list)  # (label, reason)
    # Subset of `dropped` that means the PROPOSAL was malformed (as opposed to
    # "already accepted" / "known blocker" / over budget): a repair round is
    # worthwhile only for these.
    invalid: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    proposer_calls: int = 1

    @property
    def ids(self) -> list[str]:
        return [p.package_id for p in self.packages]


Proposer = Callable[[PlanningInput], list[dict[str, Any]]]


# --- text fingerprints -------------------------------------------------


def _stem(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"

    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]

    return word


def _tokens(text: str) -> frozenset[str]:
    words = re.findall(r"[a-z0-9_]+", text.lower())
    return frozenset(
        _stem(w) for w in words if len(w) > 2 and w not in _STOPWORDS
    )


def fingerprint_text(text: str) -> str:
    joined = " ".join(sorted(_tokens(text)))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def similar(left: str, right: str, threshold: float = 0.8) -> bool:
    a, b = _tokens(left), _tokens(right)

    if not a or not b:
        return False

    return len(a & b) / len(a | b) >= threshold


# --- repo inspection (read-only) --------------------------------------


def _git(repo_root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", shell=False, check=False, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    return proc.stdout if proc.returncode == 0 else ""


def repo_fingerprint(repo_root: Path) -> str:
    """HEAD + porcelain status: changes iff the tree was touched."""

    return _git(repo_root, "rev-parse", "HEAD") + "\n" + _git(
        repo_root, "status", "--porcelain", "--untracked-files=all"
    )


def inspect_repo_state(
    repo_root: Path,
    evidence_dirs: tuple[str, ...] = ("VECTOR_TECHNICAL_KNOWLEDGE",),
) -> dict[str, Any]:
    """Cheap, read-only facts the proposer and the reviewers can rely on."""

    repo_root = Path(repo_root)
    state: dict[str, Any] = {
        "head": _git(repo_root, "rev-parse", "HEAD").strip(),
        "branch": _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD").strip(),
        "dirty_files": [
            line[3:] for line in _git(repo_root, "status", "--porcelain").splitlines()
        ][:40],
        "existing_reports": [],
    }

    for name in evidence_dirs:
        folder = repo_root / name

        if not folder.is_dir():
            continue

        for path in sorted(folder.glob("*.md"))[:60]:
            try:
                first = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
            except (OSError, IndexError):
                first = ""

            state["existing_reports"].append(
                {"path": f"{name}/{path.name}", "title": first.lstrip("# ").strip()[:120]}
            )

    return state


# --- validation --------------------------------------------------------


def _clean_path(raw: str) -> str:
    text = norm_repo_path(raw)
    return text or "."


def _path_problem(path: str, *, allow_bridge: bool) -> str | None:
    if not path or path == ".":
        return "empty or repository-root path"
    if re.match(r"^[a-zA-Z]:", path) or path.startswith("/"):
        return "absolute path"
    if ".." in path.split("/"):
        return "parent traversal"
    if path in ("*", "**", "**/*", "*/"):
        return "wildcard covers the whole repository"
    for prefix in PROTECTED_PATH_PREFIXES:
        if path == prefix or path.startswith(prefix):
            return f"protected path {prefix}"
    if path.startswith(BRIDGE_PREFIX) and not allow_bridge:
        return "the bridge must not modify itself in a program"
    return None


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    return tuple(str(v).strip() for v in value if str(v).strip())


def validate_package(
    raw: dict[str, Any],
    *,
    index: int,
    policy: ApprovalPolicy,
    allow_bridge: bool,
) -> tuple[WorkPackage | None, str]:
    """(package, "") on success, or (None, reason) if it must be dropped."""

    title = str(raw.get("title", "")).strip()
    objective = str(raw.get("objective", "")).strip()
    label = title or f"package #{index + 1}"

    if not title or not objective:
        return None, "missing title or objective"

    allowed = tuple(dict.fromkeys(_clean_path(p) for p in _as_tuple(raw.get("allowed_paths"))))
    criteria = _as_tuple(raw.get("acceptance_criteria"))
    tests = tuple(t.replace("\\", "/") for t in _as_tuple(raw.get("test_targets")))
    behavior = _as_tuple(raw.get("behavioral_evidence"))
    review_only = bool(raw.get("review_only", False))

    if review_only:
        # The worker's cycle requires a change + deterministic tests to
        # certify; a review-only package has nothing it could execute.
        return None, "review-only packages are not executable through the worker"

    if not allowed:
        return None, "no allowed mutation paths"
    if len(allowed) > MAX_PATHS_PER_PACKAGE:
        return None, f"scope too wide: {len(allowed)} paths (max {MAX_PATHS_PER_PACKAGE})"
    for path in allowed:
        problem = _path_problem(path, allow_bridge=allow_bridge)
        if problem:
            return None, f"unsafe allowed path {path!r}: {problem}"
    if not criteria:
        return None, "no acceptance criteria"
    if not tests:
        return None, "no relevant tests"
    bad_targets = invalid_test_targets(list(tests))
    if bad_targets:
        return None, (
            "invalid test target (each must be ONE plain pytest path or node id such as "
            "tests/test_x.py or tests/test_x.py::test_y, never embedded pytest arguments): "
            + "; ".join(bad_targets)
        )
    if not behavior:
        return None, "no behavioral evidence required"

    owner = raw.get("preferred_owner")
    owner_reason = str(raw.get("preferred_owner_reason", "")).strip()

    if owner is not None and str(owner).lower() not in ("claude", "codex"):
        return None, f"invalid preferred_owner {owner!r}"

    owner = str(owner).lower() if owner else None

    if owner and not owner_reason:
        # A preference is only honoured when it is justified.
        owner = None

    forbidden = tuple(dict.fromkeys(_as_tuple(raw.get("forbidden_scope")) + DEFAULT_FORBIDDEN_SCOPE))
    stop = _as_tuple(raw.get("stop_conditions")) or (
        "Stop and report if the objective cannot be met inside the allowed paths.",
        "Stop and report if the same test failure survives one correction.",
    )

    try:
        requested = Difficulty(str(raw.get("difficulty", Difficulty.ROUTINE.value)).lower())
    except ValueError:
        return None, f"invalid difficulty {raw.get('difficulty')!r}"

    acceptance_critical = bool(raw.get("acceptance_critical", False))
    text = f"{title}. {objective}. " + " ".join(criteria)
    inference = infer_difficulty(
        text,
        requested=requested,
        spec=TaskSpec(
            objective=objective,
            allowed_paths=allowed,
            forbidden_scope=forbidden,
            acceptance_criteria=criteria,
            test_targets=tests,
            review_only=review_only,
            acceptance_critical=acceptance_critical,
        ),
    )
    decision = policy.evaluate_description(f"{title}. {objective}")

    package = WorkPackage(
        package_id=str(raw.get("package_id") or f"p{index + 1}").strip(),
        title=title,
        objective=objective,
        scope=str(raw.get("scope", "")).strip() or objective,
        allowed_paths=allowed,
        forbidden_scope=forbidden,
        acceptance_criteria=criteria,
        test_targets=tests,
        behavioral_evidence=behavior,
        dependencies=_as_tuple(raw.get("dependencies")),
        risk=decision.risk.value if hasattr(decision.risk, "value") else str(decision.risk),
        requested_difficulty=requested.value,
        inferred_difficulty=inference.inferred.value,
        effective_difficulty=inference.effective.value,
        difficulty_reason=inference.reason_text,
        preferred_owner=owner,
        preferred_owner_reason=owner_reason if owner else "",
        stop_conditions=stop,
        acceptance_critical=acceptance_critical,
        review_only=review_only,
        needs_owner=decision.requires_human,
        owner_reasons=tuple(decision.reasons),
    )
    return package, ""


def _topological(packages: list[WorkPackage], plan: Plan) -> list[WorkPackage]:
    """Order by dependencies (stable); drop packages in cycles or with unknown deps."""

    by_id = {p.package_id: p for p in packages}
    keep = dict(by_id)

    # unknown dependencies are unsatisfiable -> drop (and whatever depends on them)
    changed = True
    while changed:
        changed = False
        for pid, pkg in list(keep.items()):
            missing = [d for d in pkg.dependencies if d not in keep]
            if missing:
                plan.dropped.append((pkg.title, f"unresolvable dependency {missing}"))
                plan.invalid.append((pkg.title, f"unresolvable dependency {missing}"))
                del keep[pid]
                changed = True

    ordered: list[WorkPackage] = []
    placed: set[str] = set()
    remaining = [p for p in packages if p.package_id in keep]

    while remaining:
        progress = False
        for pkg in list(remaining):
            if all(d in placed for d in pkg.dependencies):
                ordered.append(pkg)
                placed.add(pkg.package_id)
                remaining.remove(pkg)
                progress = True
        if not progress:
            for pkg in remaining:
                plan.dropped.append((pkg.title, "dependency cycle"))
                plan.invalid.append((pkg.title, "dependency cycle"))
            break

    return ordered


def validate_plan(
    proposals: list[dict[str, Any]],
    planning: PlanningInput,
    *,
    allow_bridge: bool = False,
    policy: ApprovalPolicy | None = None,
) -> Plan:
    """Deterministically turn raw proposals into a trustworthy Plan."""

    policy = policy or ApprovalPolicy()
    plan = Plan()
    accepted: list[WorkPackage] = []
    seen_ids: set[str] = set()

    for index, raw in enumerate(proposals if isinstance(proposals, list) else []):
        if not isinstance(raw, dict):
            plan.dropped.append((f"package #{index + 1}", "not an object"))
            plan.invalid.append((f"package #{index + 1}", "not an object"))
            continue

        package, reason = validate_package(
            raw, index=index, policy=policy, allow_bridge=allow_bridge
        )

        if package is None:
            label = str(raw.get("title") or f"package #{index + 1}")
            plan.dropped.append((label, reason))
            plan.invalid.append((label, reason))
            continue

        if package.package_id in seen_ids:
            plan.dropped.append((package.title, f"duplicate package id {package.package_id}"))
            plan.invalid.append((package.title, f"duplicate package id {package.package_id}"))
            continue

        # Do not reopen accepted work.
        done = next(
            (
                e for e in planning.ledger
                if e.status == "accepted"
                and (
                    e.package_id == package.package_id
                    or fingerprint_text(e.title + " " + e.objective) == package.fingerprint
                    or similar(e.title + " " + e.objective, package.title + " " + package.objective)
                )
            ),
            None,
        )

        if done is not None:
            plan.dropped.append(
                (package.title, f"already accepted ({done.package_id}); not reopened")
            )
            continue

        # Do not blindly re-propose work that matches a known blocker.
        blocked = next(
            (
                b for b in planning.blockers
                if b.fingerprint == package.fingerprint
                or similar(b.description, package.title + " " + package.objective)
            ),
            None,
        )

        if blocked is not None:
            plan.dropped.append(
                (package.title, f"matches known blocker: {blocked.description[:80]}")
            )
            continue

        seen_ids.add(package.package_id)
        accepted.append(package)

    ordered = _topological(accepted, plan)

    if len(ordered) > planning.max_packages:
        for pkg in ordered[planning.max_packages:]:
            plan.dropped.append((pkg.title, f"beyond max_packages={planning.max_packages}"))
        ordered = ordered[: planning.max_packages]

        # dependents of a truncated package would be unsatisfiable
        kept = {p.package_id for p in ordered}
        ordered = [p for p in ordered if all(d in kept for d in p.dependencies)]

    plan.packages = ordered

    if not plan.packages:
        plan.warnings.append("Plan is empty: nothing valid remains to do.")

    return plan


# --- planner -----------------------------------------------------------


class Planner:
    """Read-only planner: propose (untrusted) -> validate (trusted)."""

    def __init__(
        self,
        repo_root: Path,
        proposer: Proposer,
        *,
        allow_bridge_paths: bool = False,
        policy: ApprovalPolicy | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.proposer = proposer
        self.allow_bridge_paths = allow_bridge_paths
        self.policy = policy or ApprovalPolicy()

    def plan(self, planning: PlanningInput) -> Plan:
        if not planning.goal.strip():
            raise PlannerError("A program goal is required.")

        if planning.max_packages < 1:
            raise PlannerError("max_packages must be at least 1.")

        if not planning.repo_state:
            planning.repo_state = inspect_repo_state(self.repo_root)

        before = repo_fingerprint(self.repo_root)
        proposals = self._propose(planning, before)
        result = validate_plan(
            proposals, planning, allow_bridge=self.allow_bridge_paths, policy=self.policy
        )

        if not result.invalid:
            return result

        # ONE repair round: the proposer sees exactly what the validator rejected
        # (e.g. a malformed test target). Still invalid afterwards -> fail closed;
        # nothing malformed ever reaches execution. No budget for a second call ->
        # fail closed immediately.
        if planning.max_calls < 2:
            error = PlannerError(
                "The plan is invalid and no provider-call budget remains for a repair round: "
                + "; ".join(f"{label}: {reason}" for label, reason in result.invalid)[:400]
            )
            error.calls = 1
            raise error

        feedback = [f"{label}: {reason}"[:300] for label, reason in result.invalid][:8]
        repaired_input = replace(planning, feedback=feedback)

        try:
            proposals = self._propose(repaired_input, before)
        except PlannerError as exc:
            exc.calls = 2
            raise

        result = validate_plan(
            proposals, repaired_input, allow_bridge=self.allow_bridge_paths, policy=self.policy
        )
        result.proposer_calls = 2

        if result.invalid:
            error = PlannerError(
                "The plan was still invalid after one repair round: "
                + "; ".join(f"{label}: {reason}" for label, reason in result.invalid)[:500]
            )
            error.calls = 2
            raise error

        result.warnings.append("plan repaired after validator feedback (1 round)")
        return result

    def _propose(self, planning: PlanningInput, before: str) -> list[dict[str, Any]]:
        proposals = self.proposer(planning)

        if repo_fingerprint(self.repo_root) != before:
            raise PlannerMutationError(
                "The planning step changed the working tree; a planner is read-only. "
                "Nothing was queued."
            )

        return proposals


# --- default model proposer -------------------------------------------

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["packages"],
    "properties": {
        "packages": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "package_id", "title", "objective", "scope", "allowed_paths",
                    "forbidden_scope", "acceptance_criteria", "test_targets",
                    "behavioral_evidence", "dependencies", "difficulty",
                    "preferred_owner", "preferred_owner_reason", "stop_conditions",
                    "acceptance_critical", "review_only",
                ],
                "properties": {
                    "package_id": {"type": "string"},
                    "title": {"type": "string"},
                    "objective": {"type": "string"},
                    "scope": {"type": "string"},
                    "allowed_paths": {"type": "array", "items": {"type": "string"}},
                    "forbidden_scope": {"type": "array", "items": {"type": "string"}},
                    "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                    "test_targets": {"type": "array", "items": {"type": "string"}},
                    "behavioral_evidence": {"type": "array", "items": {"type": "string"}},
                    "dependencies": {"type": "array", "items": {"type": "string"}},
                    "difficulty": {
                        "type": "string",
                        "enum": [d.value for d in Difficulty],
                    },
                    "preferred_owner": {"type": "string", "enum": ["", "claude", "codex"]},
                    "preferred_owner_reason": {"type": "string"},
                    "stop_conditions": {"type": "array", "items": {"type": "string"}},
                    "acceptance_critical": {"type": "boolean"},
                    "review_only": {"type": "boolean"},
                },
            },
        }
    },
}


def build_planning_prompt(planning: PlanningInput) -> str:
    ledger = "\n".join(
        f"- [{e.package_id}] {e.title} :: {e.evidence or 'accepted'}"
        for e in planning.ledger
    ) or "(none yet)"
    blockers = "\n".join(
        f"- {b.description} (seen {b.count}x)"
        + (f"\n  evidence: {b.evidence[:700]}" if b.evidence else "")
        for b in planning.blockers[:6]
    ) or "(none)"
    feedback = "\n".join(f"- {line}" for line in planning.feedback[:8])
    reports = "\n".join(
        f"- {r['path']}: {r['title']}"
        for r in planning.repo_state.get("existing_reports", [])
    ) or "(none)"

    prompt = (
        "You are the READ-ONLY planner of the VECTOR development orchestrator. "
        "Do not edit anything. Inspect the repository and existing reports, "
        "then decompose the goal into a SMALL ordered list of independent "
        f"work packages (at most {planning.max_packages}).\n\n"
        f"PROGRAM GOAL:\n{planning.goal}\n\n"
        f"REPO: HEAD {planning.repo_state.get('head', '?')} on "
        f"{planning.repo_state.get('branch', '?')}\n\n"
        f"EXISTING REPORTS / EVIDENCE (read before proposing; do NOT reopen "
        f"completed work):\n{reports}\n\n"
        f"ACCEPTED WORK LEDGER (already done, never re-propose):\n{ledger}\n\n"
        f"KNOWN BLOCKERS (do not blindly repeat these; kind=test_spec means the previous "
        f"test_targets were wrong, so fix the targets rather than the implementation):\n{blockers}\n\n"
        + (
            f"YOUR PREVIOUS PROPOSAL WAS REJECTED BY THE VALIDATOR. Fix exactly these:\n{feedback}\n\n"
            if feedback
            else ""
        )
        +
        "RULES FOR EVERY PACKAGE:\n"
        "- test_targets: each entry is ONE plain pytest path or node id, e.g. "
        "tests/test_x.py or tests/test_x.py::test_y. NEVER put pytest arguments (-k, -x, "
        "--maxfail, several paths, quotes) inside an entry; to run a subset use node ids.\n"
        "- one bounded objective; specific allowed_paths (files or narrow "
        "directories, never the repo root); relevant pytest targets; "
        "behavioral_evidence = the observable behaviour that proves it works "
        "(not just 'tests pass'); acceptance_criteria the reviewer can check.\n"
        "- dependencies list package_ids that must be accepted first.\n"
        "- difficulty is your estimate; the controller may only raise it.\n"
        "- preferred_owner only with a real reason (empty string otherwise).\n"
        "- NEVER propose: pushing/merging/publishing, deleting owner data, "
        "credential or spending changes, dependency changes, or a rewrite "
        "of a subsystem. If the goal needs one, say so in a package titled "
        "'OWNER DECISION NEEDED: ...' instead.\n"
        "Reply with ONLY a JSON object {\"packages\": [...]} matching the schema."
    )

    return prompt[:_PROMPT_BUDGET]


def _extract_json(text: str) -> Any:
    text = (text or "").strip()

    try:
        return json.loads(text)
    except ValueError:
        pass

    start, end = text.find("{"), text.rfind("}")

    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except ValueError:
            return None

    return None


def make_model_proposer(
    provider_fn: Callable[[str], str],
) -> Proposer:
    """Proposer backed by any `prompt -> text` callable (a read-only model)."""

    def propose(planning: PlanningInput) -> list[dict[str, Any]]:
        text = provider_fn(build_planning_prompt(planning))
        payload = _extract_json(text)

        if isinstance(payload, dict) and isinstance(payload.get("packages"), list):
            proposals = payload["packages"]
        elif isinstance(payload, list):
            proposals = payload
        else:
            raise PlannerError("Planner model returned no parseable packages JSON.")

        for item in proposals:
            if isinstance(item, dict) and item.get("preferred_owner") == "":
                item["preferred_owner"] = None

        return proposals

    return propose


def claude_read_only_provider(
    repo_root: Path,
    *,
    model: str = "sonnet",
    effort: str = "high",
    timeout_seconds: int = 900,
) -> Callable[[str], str]:
    """`prompt -> text` via Claude Code with read-only tools and a JSON schema."""

    from claude_adapter import ClaudeAdapter
    from execution_cycle import ExecutionCycle

    adapter = ClaudeAdapter(Path(repo_root), timeout_seconds=timeout_seconds)

    def call(prompt: str) -> str:
        result = adapter.run_read_only(
            prompt=prompt, model=model, effort=effort, json_schema=PLAN_SCHEMA
        )

        if not result.succeeded:
            raise PlannerError(
                f"Claude planner call failed (exit {result.exit_code}, "
                f"timed_out={result.timed_out}): {(result.stderr or '')[-300:]}"
            )

        return ExecutionCycle._extract_result_text(result)

    return call


def codex_read_only_provider(
    repo_root: Path,
    *,
    model: str = "gpt-5.6-terra",
    timeout_seconds: int = 900,
) -> Callable[[str], str]:
    """`prompt -> text` via Codex in a read-only sandbox with a strict schema."""

    from codex_adapter import CodexAdapter
    from execution_cycle import ExecutionCycle

    adapter = CodexAdapter(Path(repo_root), timeout_seconds=timeout_seconds)

    def call(prompt: str) -> str:
        result = adapter.run_read_only(prompt=prompt, model=model, output_schema=PLAN_SCHEMA)

        if not result.succeeded:
            raise PlannerError(
                f"Codex planner call failed (exit {result.exit_code}, "
                f"timed_out={result.timed_out}): {(result.stderr or '')[-300:]}"
            )

        return ExecutionCycle._extract_result_text(result)

    return call


# --- self-test ---------------------------------------------------------


def _good(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "package_id": "p1",
        "title": "Add retry to the queue helper",
        "objective": "Make the queue helper retry twice on transient failure.",
        "scope": "queue helper only",
        "allowed_paths": ["core/queue_helper.py", "tests/test_queue_helper.py"],
        "acceptance_criteria": ["helper retries twice", "existing tests still pass"],
        "test_targets": ["tests/test_queue_helper.py"],
        "behavioral_evidence": ["a failing call succeeds on the 2nd retry in the test"],
        "difficulty": "routine",
    }
    base.update(overrides)
    return base


def _self_test() -> None:
    import shutil
    import tempfile

    planning = PlanningInput(goal="Harden the queue helper.", repo_state={"head": "x"})

    # 1. A well-formed program decomposes into ordered packages with a DAG.
    proposals = [
        _good(package_id="p2", title="Document the retry behaviour",
              objective="Document how the queue helper retries transient failures.",
              allowed_paths=["docs/queue.md"], test_targets=["tests/test_docs.py"],
              dependencies=["p1"]),
        _good(),
        _good(package_id="p3", title="Add jitter to retry delays",
              objective="Add bounded random jitter to the retry delay calculation.",
              allowed_paths=["core/retry_delay.py"], test_targets=["tests/test_retry_delay.py"],
              dependencies=["p1", "p2"]),
    ]
    plan = validate_plan(proposals, planning)
    assert plan.ids == ["p1", "p2", "p3"], plan.ids
    first = plan.packages[0]
    assert first.forbidden_scope[-len(DEFAULT_FORBIDDEN_SCOPE):] == DEFAULT_FORBIDDEN_SCOPE
    assert first.stop_conditions and first.reviewer_policy
    assert first.requested_difficulty == "routine" and first.effective_difficulty
    assert first.preferred_owner is None

    # 2. Structural validation drops unsafe / incomplete proposals with reasons.
    bad = [
        _good(package_id="a", title="No paths", allowed_paths=[]),
        _good(package_id="b", title="Root path", allowed_paths=["."]),
        _good(package_id="c", title="Traversal", allowed_paths=["../outside.py"]),
        _good(package_id="d", title="Absolute", allowed_paths=["C:/Windows/x.py"]),
        _good(package_id="e", title="Protected", allowed_paths=[".claude/settings.json"]),
        _good(package_id="f", title="Protected doc",
              allowed_paths=["docs/VECTOR_OS_LONG_TERM_VISION.md"]),
        _good(package_id="g", title="Bridge self edit",
              allowed_paths=["tools/vector_dev_orchestrator/router.py"]),
        _good(package_id="h", title="No criteria", acceptance_criteria=[]),
        _good(package_id="i", title="No tests", test_targets=[]),
        _good(package_id="j", title="No evidence", behavioral_evidence=[]),
        _good(package_id="k", title="Too wide", allowed_paths=[f"m{n}/" for n in range(9)]),
        _good(package_id="l", title="Bad owner", preferred_owner="gemini"),
        _good(package_id="m", title="Bad difficulty", difficulty="impossible"),
        "not a dict",
        _good(package_id="n", title="", objective=""),
        _good(package_id="o", title="Review only", review_only=True),
    ]
    bad_plan = validate_plan(bad, planning)
    assert bad_plan.packages == [] and len(bad_plan.dropped) == len(bad)
    assert any("protected path" in r for _, r in bad_plan.dropped)
    assert any("bridge must not modify itself" in r for _, r in bad_plan.dropped)
    assert bad_plan.warnings

    # 3. The bridge may be a target only when explicitly allowed.
    self_edit = [_good(allowed_paths=["tools/vector_dev_orchestrator/router.py"])]
    assert validate_plan(self_edit, planning).packages == []
    assert validate_plan(self_edit, planning, allow_bridge=True).ids == ["p1"]

    # 4. Dependencies: unknown and cyclic packages are dropped; DAG order is stable.
    dep = validate_plan(
        [
            _good(package_id="x", title="Orphan dependent", objective="Depends on a ghost package here.",
                  dependencies=["ghost"]),
            _good(package_id="y", title="Cycle alpha", objective="Cycle member alpha does something.",
                  dependencies=["z"]),
            _good(package_id="z", title="Cycle beta", objective="Cycle member beta does another thing.",
                  dependencies=["y"]),
            _good(package_id="ok", title="Independent good work", objective="Unrelated independent bounded work."),
        ],
        planning,
    )
    assert dep.ids == ["ok"]
    reasons = " ".join(r for _, r in dep.dropped)
    assert "unresolvable dependency" in reasons and "dependency cycle" in reasons

    # 5. Duplicate ids and max_packages are enforced; dependents of cut packages go too.
    dup = validate_plan([_good(), _good(title="Other", objective="Something quite different entirely.")], planning)
    assert dup.ids == ["p1"] and any("duplicate package id" in r for _, r in dup.dropped)
    capped_input = PlanningInput(goal="g", repo_state={"head": "x"}, max_packages=2)
    capped = validate_plan(
        [
            _good(package_id=f"c{n}", title=f"Distinct work number {n} {'abcdefgh'[n]}",
                  objective=f"Bounded objective {'abcdefgh'[n]} {n} zeta{n}",
                  dependencies=([f"c{n - 1}"] if n else []))
            for n in range(4)
        ],
        capped_input,
    )
    assert capped.ids == ["c0", "c1"] and sum("max_packages" in r for _, r in capped.dropped) == 2

    # 6. Completed work is never reopened; known blockers are not blindly repeated.
    ledgered = PlanningInput(
        goal="g", repo_state={"head": "x"},
        ledger=[LedgerEntry("old1", "Add retry to the queue helper",
                            "Make the queue helper retry twice on transient failure.",
                            evidence="report 2026-09-01")],
        blockers=[BlockerRecord("f", "Rate limiter design conflicts with the sandbox")],
    )
    kept = validate_plan(
        [
            _good(),  # same as ledger -> dropped
            _good(package_id="p9", title="Add retries to queue helper again",
                  objective="Make queue helper retry twice on transient failures.",
                  allowed_paths=["core/other.py"]),  # near-duplicate -> dropped
            _good(package_id="p8", title="Rate limiter design conflicts with the sandbox",
                  objective="Rate limiter design conflicts with the sandbox layer."),
            _good(package_id="p7", title="Something genuinely new here",
                  objective="Add structured logging fields to the scheduler tick."),
        ],
        ledgered,
    )
    assert kept.ids == ["p7"], kept.ids
    assert sum("already accepted" in r for _, r in kept.dropped) == 2
    assert any("known blocker" in r for _, r in kept.dropped)

    # 7. Approval-gate flagging and difficulty floors (requested may not lower them).
    risky = validate_plan(
        [
            _good(package_id="s1", title="Rotate the API key for the provider",
                  objective="Rotate the API key stored for the provider and update the credential store.",
                  allowed_paths=["core/keys.py"], difficulty="scout"),
            _good(package_id="s2", title="Tighten the authentication check",
                  objective="Tighten authentication and token validation in the login path.",
                  allowed_paths=["core/auth.py"], test_targets=["tests/test_auth.py"],
                  difficulty="scout"),
            _good(package_id="s3", title="Tidy a helper", objective="Rename a private helper for readability.",
                  allowed_paths=["core/tidy.py"], test_targets=["tests/test_tidy.py"]),
        ],
        planning,
    )
    s1, s2, s3 = risky.packages
    assert s1.needs_owner and s1.owner_reasons
    assert not s3.needs_owner
    assert s2.requested_difficulty == "scout"
    assert Difficulty(s2.effective_difficulty).value in ("hard", "critical")
    assert Difficulty(s3.effective_difficulty) in (Difficulty.SCOUT, Difficulty.ROUTINE)
    assert "security" in s2.difficulty_reason.lower()

    # 8. A preferred owner is honoured only with a justification.
    owners = validate_plan(
        [
            _good(package_id="o1", preferred_owner="codex",
                  preferred_owner_reason="needs a long autonomous refactor"),
            _good(package_id="o2", title="Second independent thing", objective="Entirely separate objective two.",
                  preferred_owner="claude"),
        ],
        planning,
    )
    assert owners.packages[0].preferred_owner == "codex"
    assert owners.packages[1].preferred_owner is None

    # 9. Planner: read-only enforcement against a real git repo.
    temp = Path(tempfile.mkdtemp(prefix="vector_planner_test_"))

    try:
        def git(*args: str) -> None:
            subprocess.run(["git", "-C", str(temp), *args], check=True, capture_output=True)

        git("init", "-q")
        git("config", "user.email", "p@example.invalid")
        git("config", "user.name", "P")
        (temp / "a.txt").write_text("a\n", encoding="utf-8")
        (temp / "VECTOR_TECHNICAL_KNOWLEDGE").mkdir()
        (temp / "VECTOR_TECHNICAL_KNOWLEDGE" / "R.md").write_text("# Old report\nbody\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-q", "-m", "base")

        state = inspect_repo_state(temp)
        assert state["head"] and state["existing_reports"] == [
            {"path": "VECTOR_TECHNICAL_KNOWLEDGE/R.md", "title": "Old report"}
        ]

        seen_states: list[dict[str, Any]] = []

        def good_proposer(p: PlanningInput) -> list[dict[str, Any]]:
            seen_states.append(p.repo_state)
            return [_good()]

        result = Planner(temp, good_proposer).plan(PlanningInput(goal="Harden the queue helper."))
        assert result.ids == ["p1"] and seen_states[0]["existing_reports"], "planner inspects reports first"

        def writing_proposer(p: PlanningInput) -> list[dict[str, Any]]:
            (temp / "sneaky.txt").write_text("mutation\n", encoding="utf-8")
            return [_good()]

        try:
            Planner(temp, writing_proposer).plan(PlanningInput(goal="g"))
        except PlannerMutationError:
            pass
        else:
            raise AssertionError("a proposer that edits the tree must fail closed")

        for bad_input in (PlanningInput(goal="  "), PlanningInput(goal="g", max_packages=0)):
            try:
                Planner(temp, good_proposer).plan(bad_input)
            except PlannerError:
                pass
            else:
                raise AssertionError("invalid planning input must be refused")
    finally:
        shutil.rmtree(temp, ignore_errors=True)

    # 10. Model proposer: tolerant JSON extraction, prompt carries ledger/blockers, garbage fails.
    captured: list[str] = []
    payload = json.dumps({"packages": [_good(preferred_owner="")]})

    propose = make_model_proposer(lambda prompt: captured.append(prompt) or f"Sure!\n{payload}\nDone")
    proposed = propose(ledgered)
    assert proposed[0]["preferred_owner"] is None
    assert "Add retry to the queue helper" in captured[0] and "Rate limiter design" in captured[0]
    assert "READ-ONLY" in captured[0] and "PROGRAM GOAL" in captured[0]
    assert len(build_planning_prompt(PlanningInput(goal="x" * 50000))) <= _PROMPT_BUDGET

    try:
        make_model_proposer(lambda prompt: "no json here")(ledgered)
    except PlannerError:
        pass
    else:
        raise AssertionError("unparseable planner output must fail closed")

    assert PLAN_SCHEMA["properties"]["packages"]["items"]["additionalProperties"] is False
    item_schema = PLAN_SCHEMA["properties"]["packages"]["items"]
    assert set(item_schema["required"]) == set(item_schema["properties"]), "strict schema: all props required"

    assert similar("add retry queue helper", "add retry queue helper")
    assert not similar("add retry queue helper", "rotate encryption keys nightly")


if __name__ == "__main__":
    _self_test()
