"""Deterministic, conservative automatic difficulty classification.

The caller's requested difficulty is never the sole routing authority:
effective = max(requested, inferred, safety_floor).

  - a requested difficulty may RAISE the level;
  - it can never LOWER a demonstrated safety floor (security/auth,
    architecture, migrations, concurrency/persistence, external effects);
  - with no structured scope (ad-hoc task) only description-content signals
    apply, so plain prepare_task() callers are not silently up-tiered by
    "unknown scope".

Understandable rules only -- no model calls, no ML. Reuses the same
negation-aware phrase matcher as approval.py, so "Do not modify security
code" does not create a security floor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from models import Difficulty, TaskSpec
from router import difficulty_rank, max_difficulty
from text_signals import norm_repo_path, normalize, phrase_triggers, split_sentences

_SECURITY_PHRASES = (
    "security", "authentication", "authorization", "credential", "secret",
    "encryption", "vulnerability", "exploit", "permission gateway", "jwt",
    "oauth", "password", "api key", "csrf", "privilege",
)
_ARCHITECTURE_PHRASES = (
    "architecture", "architectural", "system design", "redesign",
    "replace the entire", "replace the whole", "rewrite the entire",
    "rewrite the whole", "new subsystem",
)
_MIGRATION_PHRASES = (
    "migration", "alter table", "database schema change", "schema change",
    "data model change",
)
_CONCURRENCY_PHRASES = (
    "concurrency", "concurrent", "race condition", "deadlock", "thread-safe",
    "atomic write", "recovery", "persistence", "checkpoint", "transaction",
    "restart", "resume",
)
_EXTERNAL_EFFECT_PHRASES = (
    "send email", "send message", "post to", "upload to", "network call",
    "external api", "payment", "purchase", "deploy", "publish",
)

# Path segments that mark security-critical code regardless of wording.
_SECURITY_PATH_SEGMENTS = {
    "security", "auth", "authentication", "authorization", "permissions",
    "permission_gateway", "credentials", "secrets", "gateway",
}

_PATH_RE = re.compile(r"[\w./-]+\.(?:py|ts|js|yaml|yml|json|toml)\b")


@dataclass(frozen=True, slots=True)
class DifficultyInference:
    requested: str
    inferred: Difficulty
    floor: Difficulty
    effective: Difficulty
    reasons: tuple[str, ...]

    @property
    def reason_text(self) -> str:
        return "; ".join(self.reasons)


def _is_test_path(path: str) -> bool:
    p = norm_repo_path(path)
    return p.startswith("tests/") or "/tests/" in p or p.startswith("test_")


def _segments(path: str) -> set[str]:
    return {seg.lower().rsplit(".", 1)[0] for seg in path.replace("\\", "/").split("/") if seg}


def infer_difficulty(
    description: str,
    *,
    requested: Difficulty | str | None = None,
    spec: TaskSpec | None = None,
) -> DifficultyInference:
    spec = spec or TaskSpec()
    text = " ".join([description, spec.objective])
    sentences = split_sentences(normalize(text))
    reasons: list[str] = []

    floor = Difficulty.SCOUT
    inferred = Difficulty.SCOUT

    def raise_floor(level: Difficulty, why: str) -> None:
        nonlocal floor
        floor = max_difficulty(floor, level)
        reasons.append(f"floor {level.value}: {why}")

    def raise_inferred(level: Difficulty, why: str) -> None:
        nonlocal inferred
        inferred = max_difficulty(inferred, level)
        reasons.append(f"{level.value}: {why}")

    # --- safety floors (never lowerable by a requested difficulty) -------
    if phrase_triggers(sentences, _SECURITY_PHRASES):
        raise_floor(Difficulty.HARD, "security/auth implications in the task text")

    if any(_segments(p) & _SECURITY_PATH_SEGMENTS for p in spec.allowed_paths):
        raise_floor(Difficulty.HARD, "allowed paths include security/auth/gateway code")

    if phrase_triggers(sentences, _MIGRATION_PHRASES):
        raise_floor(Difficulty.HARD, "migration/schema change")

    if phrase_triggers(sentences, _ARCHITECTURE_PHRASES):
        raise_floor(Difficulty.SERIOUS, "architecture change")

    if phrase_triggers(sentences, _CONCURRENCY_PHRASES):
        raise_floor(Difficulty.SERIOUS, "concurrency/persistence/recovery semantics")

    if phrase_triggers(sentences, _EXTERNAL_EFFECT_PHRASES):
        raise_floor(Difficulty.SERIOUS, "external side effects")

    # --- scope-based inference (only when structured scope is known) -----
    if spec.scope_known:
        paths = list(spec.allowed_paths)
        production = [p for p in paths if not _is_test_path(p)]
        subsystems = {p.replace("\\", "/").split("/")[0] for p in production}

        if spec.review_only:
            reasons.append("scout: review/read-only, no mutation risk")
        elif production:
            raise_inferred(Difficulty.ROUTINE, "changes production code")
        elif paths:
            reasons.append("scout: test-only change")

        if len(paths) > 6 or len(subsystems) >= 3:
            raise_inferred(Difficulty.SERIOUS, f"wide scope ({len(paths)} paths, {len(subsystems)} subsystems)")
        elif len(paths) > 2 and not spec.review_only:
            raise_inferred(Difficulty.ROUTINE, f"{len(paths)} allowed paths")

        if len(spec.test_targets) > 3:
            raise_inferred(Difficulty.ROUTINE, "many test targets")

        if spec.acceptance_critical and not spec.review_only and production:
            raise_inferred(Difficulty.SERIOUS, "acceptance-critical production change")

        vague = (
            not spec.allowed_paths
            or not spec.test_targets
            or len(description.split()) < 12
        )

        if vague and not spec.review_only:
            bumped = max_difficulty(Difficulty.ROUTINE, Difficulty(_next(inferred)))
            raise_inferred(bumped, "uncertain scope (missing paths/tests or vague description)")

    requested_level: Difficulty | None = None

    if requested:
        requested_level = Difficulty(requested)
        reasons.append(f"requested {requested_level.value}")

    effective = max_difficulty(inferred, floor)

    if requested_level is not None:
        effective = max_difficulty(effective, requested_level)

    if difficulty_rank(effective) > difficulty_rank(requested_level or Difficulty.SCOUT) and requested_level:
        reasons.append(f"requested {requested_level.value} raised to {effective.value}")

    return DifficultyInference(
        requested=requested_level.value if requested_level else "",
        inferred=inferred,
        floor=floor,
        effective=effective,
        reasons=tuple(reasons),
    )


def _next(level: Difficulty) -> str:
    order = [Difficulty.SCOUT, Difficulty.ROUTINE, Difficulty.SERIOUS, Difficulty.HARD, Difficulty.CRITICAL]
    return order[min(order.index(level) + 1, len(order) - 1)].value


def _self_test() -> None:
    D = Difficulty

    def spec(**kw) -> TaskSpec:
        return TaskSpec(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in kw.items()})

    clear = "Fix the off-by-one in the pagination helper and cover it with a regression test."
    long_desc = clear + " Keep the change small and preserve all existing behaviour and public names."

    # B. Under-labelled security task is upgraded; requested cannot lower the floor.
    sec = infer_difficulty(
        "Rotate the authentication credential handling in the login helper.",
        requested=D.SCOUT,
    )
    assert sec.effective is D.HARD and sec.floor is D.HARD and sec.requested == "scout"
    assert "security" in sec.reason_text and "raised" in sec.reason_text

    # ...also when only the PATH reveals it (description looks innocent).
    path_sec = infer_difficulty(long_desc, requested=D.SCOUT, spec=spec(
        allowed_paths=["core/security/policy.py"], test_targets=["tests/test_policy.py"]))
    assert path_sec.effective is D.HARD

    # A caller may RAISE above the floor, never below it.
    assert infer_difficulty("Change the authentication flow.", requested=D.CRITICAL).effective is D.CRITICAL

    # Negated prohibitions do not create a security floor.
    calm = infer_difficulty(
        "Add a test. Do not modify security code, permissions or architecture.",
        requested=D.SCOUT,
    )
    assert calm.floor is D.SCOUT and calm.effective is D.SCOUT

    # C. A routine single-file production fix stays routine (no strongest route).
    routine = infer_difficulty(long_desc, requested=D.ROUTINE, spec=spec(
        allowed_paths=["core/pagination.py", "tests/test_pagination.py"],
        test_targets=["tests/test_pagination.py"]))
    assert routine.effective is D.ROUTINE and routine.inferred is D.ROUTINE

    # ...and a small test-only change is scout.
    test_only = infer_difficulty(long_desc, requested=D.SCOUT, spec=spec(
        allowed_paths=["tests/test_pagination.py"], test_targets=["tests/test_pagination.py"]))
    assert test_only.effective is D.SCOUT

    # A requested tier is honoured when higher than inferred.
    assert infer_difficulty(long_desc, requested=D.SERIOUS, spec=spec(
        allowed_paths=["tests/t.py"], test_targets=["tests/t.py"])).effective is D.SERIOUS

    # Under-labelling a production change is corrected upward.
    under = infer_difficulty(long_desc, requested=D.SCOUT, spec=spec(
        allowed_paths=["core/x.py"], test_targets=["tests/test_x.py"]))
    assert under.effective is D.ROUTINE

    # Wide scope, architecture, concurrency, migration, external effects.
    wide = infer_difficulty(long_desc, spec=spec(
        allowed_paths=[f"core/m{i}.py" for i in range(4)] + ["api/a.py", "districts/d.py", "tests/t.py"],
        test_targets=["tests/t.py"]))
    assert wide.effective is D.SERIOUS
    assert infer_difficulty("Redesign the architecture of the memory layer.").effective is D.SERIOUS
    assert infer_difficulty("Fix the race condition in the queue recovery path.").effective is D.SERIOUS
    assert infer_difficulty("Add an alter table migration for the goals index.").effective is D.HARD
    assert infer_difficulty("Send email when the job finishes.").effective is D.SERIOUS

    # Acceptance-critical production work is at least serious.
    assert infer_difficulty(long_desc, spec=spec(
        allowed_paths=["core/x.py"], test_targets=["tests/test_x.py"], acceptance_critical=True,
    )).effective is D.SERIOUS

    # Uncertain scope is bumped conservatively (structured specs only).
    vague = infer_difficulty("Tidy things up.", spec=spec(allowed_paths=["tests/t.py"]))
    assert vague.effective is D.ROUTINE and "uncertain" in vague.reason_text

    # Ad-hoc tasks (no spec) are NOT bumped for unknown scope.
    assert infer_difficulty("Pin the implementer provider for one task.", requested=D.SCOUT).effective is D.SCOUT

    # Review-only work carries no mutation risk but still respects floors.
    ro = infer_difficulty(long_desc, spec=spec(
        allowed_paths=["core/x.py"], test_targets=["tests/test_x.py"], review_only=True))
    assert ro.effective is D.SCOUT
    assert infer_difficulty("Review the authentication code.", spec=spec(
        allowed_paths=["core/x.py"], review_only=True)).effective is D.HARD

    # Invalid requested value fails closed.
    try:
        infer_difficulty("x", requested="impossible")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid requested difficulty must raise")

    # Every inference records a human-readable reason.
    assert sec.reason_text and routine.reason_text


if __name__ == "__main__":
    _self_test()
