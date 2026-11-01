"""Development model routing and provider ownership for VECTOR.

Task-aware routing (section 1-6 upgrade): model selection now considers
BOTH difficulty AND task category/role, is quota-aware (controller-
provided, never scraped), and supports bounded, deterministic
escalation. All of this composes on top of the original difficulty-only
primitives (choose_owner, reviewer_for, choose_implementer,
choose_reviewer), which remain unchanged so nothing that already
depended on them regresses.
"""

from __future__ import annotations

from dataclasses import dataclass

from models import (
    Difficulty,
    ModelChoice,
    Provider,
    ProviderQuota,
    QuotaBand,
    QuotaState,
    TaskCategory,
)
from text_signals import normalize, phrase_triggers, split_sentences

# Re-exported so `from router import Difficulty` (used throughout the
# rest of this package) keeps working unchanged -- Difficulty now lives
# in models.py so DevTask can persist it without a models<->router
# circular import.
__all__ = [
    "Difficulty",
    "ModelRouter",
    "RoutingDecision",
    "classify_task_category",
    "quota_band_for_percent",
    "difficulty_rank",
    "max_difficulty",
    "escalate_difficulty",
]


# --- Difficulty ordering --------------------------------------------

_DIFFICULTY_RANK: dict[Difficulty, int] = {
    Difficulty.SCOUT: 0,
    Difficulty.ROUTINE: 1,
    Difficulty.SERIOUS: 2,
    Difficulty.HARD: 3,
    Difficulty.CRITICAL: 4,
}


def difficulty_rank(difficulty: Difficulty) -> int:
    return _DIFFICULTY_RANK[difficulty]


def max_difficulty(left: Difficulty, right: Difficulty) -> Difficulty:
    return left if difficulty_rank(left) >= difficulty_rank(right) else right


# Bounded escalation ladder (section 6): exactly one tier up, capped at
# CRITICAL -- never wraps, never loops.
_ESCALATION_LADDER: dict[Difficulty, Difficulty] = {
    Difficulty.SCOUT: Difficulty.ROUTINE,
    Difficulty.ROUTINE: Difficulty.SERIOUS,
    Difficulty.SERIOUS: Difficulty.HARD,
    Difficulty.HARD: Difficulty.CRITICAL,
    Difficulty.CRITICAL: Difficulty.CRITICAL,
}


def escalate_difficulty(difficulty: Difficulty) -> Difficulty:
    """Bump difficulty exactly one tier, capped at CRITICAL."""

    return _ESCALATION_LADDER[difficulty]


# --- Task-category classification (section 1) -----------------------
#
# A small, deterministic, keyword-based classifier -- NOT a giant ML
# classifier. Reuses the same negation-aware phrase matcher as
# approval.py (via text_signals.py) so a description like "Do not
# modify architecture." does not get misclassified as ARCHITECTURE
# work. First matching category wins; unmatched text defaults to
# IMPLEMENTATION (the least surprising default -- most development
# tasks are ordinary implementation work).

_CATEGORY_PHRASES: tuple[tuple[TaskCategory, tuple[str, ...]], ...] = (
    (
        TaskCategory.SECURITY_SENSITIVE,
        (
            "security",
            "authentication",
            "authorization",
            "credential",
            "secret",
            "encryption",
            "vulnerability",
            "exploit",
            "permission gateway",
        ),
    ),
    (
        TaskCategory.ARCHITECTURE,
        (
            "architecture",
            "architectural",
            "system design",
            "redesign",
            "adr",
        ),
    ),
    (
        TaskCategory.INTEGRATION,
        (
            "integration",
            "cross-module",
            "cross-service",
            "end-to-end",
        ),
    ),
    (
        TaskCategory.DEBUGGING,
        (
            "debug",
            "root cause",
            "traceback",
            "stack trace",
            "diagnose the",
        ),
    ),
    (
        TaskCategory.TEST_REPAIR,
        (
            "test repair",
            "fix failing test",
            "flaky test",
            "repair the test",
            "broken test",
        ),
    ),
    (
        TaskCategory.DOCUMENTATION,
        (
            "documentation",
            "docstring",
            "readme",
            "write docs",
            "update docs",
        ),
    ),
    (
        TaskCategory.EXPLORATION,
        (
            "inspect",
            "explore the",
            "investigate the repository",
            "scout",
            "survey the codebase",
        ),
    ),
    (
        TaskCategory.TRIVIAL_EDIT,
        (
            "trivial edit",
            "tiny deterministic",
            "mechanical edit",
            "simple config assertion",
            "one-line change",
        ),
    ),
)


def classify_task_category(description: str) -> TaskCategory:
    """Deterministically classify a task description into a TaskCategory.

    Unmatched or empty text safely defaults to IMPLEMENTATION rather
    than raising -- classification must never crash routing.
    """

    normalized = normalize(description)
    sentences = split_sentences(normalized)

    for category, phrases in _CATEGORY_PHRASES:
        if phrase_triggers(sentences, phrases):
            return category

    return TaskCategory.IMPLEMENTATION


# --- Category-driven minimum difficulty (section 1, 4) ---------------
#
# Only categories that are ALWAYS risk-elevated regardless of stated
# difficulty get an automatic floor. This is deliberately narrow: it
# only ever pushes difficulty UP (never down), so it can never silently
# reduce capability below what a caller explicitly requested.

_CATEGORY_MIN_DIFFICULTY: dict[TaskCategory, Difficulty] = {
    TaskCategory.SECURITY_SENSITIVE: Difficulty.HARD,
    TaskCategory.ARCHITECTURE: Difficulty.SERIOUS,
}


# What each category NORMALLY costs (POLICY.md sec. 3). A default, not a floor: it
# applies only when nobody stated a difficulty, and inference/floors can only raise it.
_CATEGORY_DEFAULT_DIFFICULTY: dict[TaskCategory, Difficulty] = {
    TaskCategory.EXPLORATION: Difficulty.SCOUT,
    TaskCategory.DOCUMENTATION: Difficulty.SCOUT,
    TaskCategory.TRIVIAL_EDIT: Difficulty.SCOUT,
    TaskCategory.IMPLEMENTATION: Difficulty.ROUTINE,
    TaskCategory.DEBUGGING: Difficulty.ROUTINE,
    TaskCategory.TEST_REPAIR: Difficulty.ROUTINE,
    TaskCategory.INTEGRATION: Difficulty.SERIOUS,
    TaskCategory.ARCHITECTURE: Difficulty.SERIOUS,
    TaskCategory.SECURITY_SENSITIVE: Difficulty.HARD,
}


def default_difficulty_for_category(category: TaskCategory) -> Difficulty:
    return _CATEGORY_DEFAULT_DIFFICULTY[category]


def apply_category_floor(
    difficulty: Difficulty,
    category: TaskCategory,
) -> Difficulty:
    floor = _CATEGORY_MIN_DIFFICULTY.get(category)

    if floor is None:
        return difficulty

    return max_difficulty(difficulty, floor)


# --- Quota-aware conservation (section 5) -----------------------------

def quota_band_for_percent(percent: float | None) -> QuotaBand:
    """Band a controller-supplied remaining-quota percentage.

    None (quota state unknown) maps to UNKNOWN, which routing treats
    identically to NORMAL -- an unknown quota reading must never
    silently restrict capability.
    """

    if percent is None:
        return QuotaBand.UNKNOWN

    if percent >= 60:
        return QuotaBand.NORMAL

    if percent >= 30:
        return QuotaBand.CONSERVE

    if percent >= 15:
        return QuotaBand.RESERVE

    return QuotaBand.EMERGENCY


_CONSERVE_CAP = Difficulty.ROUTINE
_RESERVE_CAP = Difficulty.SCOUT
_EMERGENCY_CAP = Difficulty.SCOUT

_QUOTA_CAP_BY_BAND: dict[QuotaBand, Difficulty] = {
    QuotaBand.CONSERVE: _CONSERVE_CAP,
    QuotaBand.RESERVE: _RESERVE_CAP,
    QuotaBand.EMERGENCY: _EMERGENCY_CAP,
}


def apply_quota_conservation(
    difficulty: Difficulty,
    band: QuotaBand,
    category: TaskCategory,
) -> Difficulty:
    """Cap the IMPLEMENTER model tier under tight quota, never below risk.

    - SECURITY_SENSITIVE work is exempt: never conserved.
    - HARD/CRITICAL difficulty is exempt: quota conservation only ever
      touches SCOUT/ROUTINE/SERIOUS-tier work, so genuinely hard/
      critical tasks always keep their configured strong model --
      "reserve strongest models for serious/hard tasks" is exactly
      this exemption.
    - NORMAL/UNKNOWN bands never change anything.

    Only the IMPLEMENTER selection is conserved this way; the
    independent REVIEWER intentionally is not (see ModelRouter.route),
    so a cost-conserved implementer still gets a full-strength review.
    """

    if category is TaskCategory.SECURITY_SENSITIVE:
        return difficulty

    if band in (QuotaBand.NORMAL, QuotaBand.UNKNOWN):
        return difficulty

    if difficulty_rank(difficulty) >= difficulty_rank(Difficulty.HARD):
        return difficulty

    cap = _QUOTA_CAP_BY_BAND[band]

    if difficulty_rank(difficulty) <= difficulty_rank(cap):
        return difficulty

    return cap


# Honest availability level -> conservation band. UNKNOWN maps to the
# UNKNOWN band, which reduces no capability (safe under missing telemetry).
# EXHAUSTED is normally handled before routing (the provider cannot be
# used at all); it maps to EMERGENCY only as a defensive fallback.
_BAND_FOR_LEVEL: dict[ProviderQuota, QuotaBand] = {
    ProviderQuota.UNKNOWN: QuotaBand.UNKNOWN,
    ProviderQuota.NORMAL: QuotaBand.NORMAL,
    ProviderQuota.CONSTRAINED: QuotaBand.RESERVE,
    ProviderQuota.EXHAUSTED: QuotaBand.EMERGENCY,
}


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """Full result of one task-aware routing pass."""

    owner: Provider
    reviewer: Provider
    implementer_model: ModelChoice
    reviewer_model: ModelChoice
    difficulty: Difficulty
    task_category: TaskCategory
    quota_band: QuotaBand
    # The reviewer provider is in EMERGENCY: review must wait (POLICY.md sec. 10).
    review_deferred: bool = False
    # Non-empty when a quota EMERGENCY overrode the 50/50 scheduler's owner.
    ownership_note: str = ""


class ModelRouter:
    """Choose development models independently of VECTOR runtime routing."""

    def choose_owner(
        self,
        previous_owner: Provider | None,
    ) -> Provider:
        """Alternate implementation ownership 50/50 between providers."""
        if previous_owner is None:
            return Provider.CODEX

        if previous_owner is Provider.CODEX:
            return Provider.CLAUDE

        return Provider.CODEX

    @staticmethod
    def reviewer_for(owner: Provider) -> Provider:
        """The other provider always performs cross-provider review."""
        if owner is Provider.CODEX:
            return Provider.CLAUDE

        return Provider.CODEX

    def choose_implementer(
        self,
        *,
        provider: Provider,
        difficulty: Difficulty,
    ) -> ModelChoice:
        if provider is Provider.CODEX:
            return self._codex_implementer(difficulty)

        return self._claude_implementer(difficulty)

    def choose_reviewer(
        self,
        *,
        provider: Provider,
        difficulty: Difficulty,
    ) -> ModelChoice:
        if provider is Provider.CODEX:
            return self._codex_reviewer(difficulty)

        return self._claude_reviewer(difficulty)

    # --- Task-aware composition (sections 1-6) ------------------------
    #
    # Everything below composes the primitives above with category
    # classification, quota conservation and bounded escalation. It
    # does not change any of the primitives' behavior; a caller that
    # never uses `route()`/`escalate_difficulty()` sees no difference.

    @staticmethod
    def escalate_difficulty(difficulty: Difficulty) -> Difficulty:
        """Bump difficulty exactly one bounded tier (never past CRITICAL)."""

        return escalate_difficulty(difficulty)

    @staticmethod
    def apply_category_floor(
        difficulty: Difficulty,
        category: TaskCategory,
    ) -> Difficulty:
        return apply_category_floor(difficulty, category)

    @staticmethod
    def apply_quota_conservation(
        difficulty: Difficulty,
        band: QuotaBand,
        category: TaskCategory,
    ) -> Difficulty:
        return apply_quota_conservation(difficulty, band, category)

    def route(
        self,
        *,
        description: str,
        base_difficulty: Difficulty,
        task_category: TaskCategory | None = None,
        previous_owner: Provider | None = None,
        quota_state: QuotaState | None = None,
        quota_levels: dict[Provider, ProviderQuota] | None = None,
        quota_bands: dict[Provider, QuotaBand] | None = None,
    ) -> RoutingDecision:
        """One task-aware routing pass: owner/reviewer + both models.

        - `task_category` is auto-classified from `description` when
          omitted (deterministic keyword classifier, see
          classify_task_category).
        - Category can only ever push the effective difficulty UP
          (SECURITY_SENSITIVE/ARCHITECTURE floors), never down --
          routing never silently loses capability based on a guessed
          category.
        - `quota_state` conserves the IMPLEMENTER selection only, per
          the OWNER provider's own remaining quota; the REVIEWER is
          never quota-conserved, so a conserved (cheaper) implementer
          still gets a full-strength independent review.
        - 50/50 ownership alternation (choose_owner) is unchanged and
          unaffected by any of this.
        """

        category = (
            task_category
            if task_category is not None
            else classify_task_category(description)
        )

        effective_difficulty = self.apply_category_floor(
            base_difficulty,
            category,
        )

        quota = quota_state if quota_state is not None else QuotaState()

        def band_for(provider: Provider) -> QuotaBand:
            # precedence: explicit bands > availability levels > percentages
            if quota_bands is not None and provider in quota_bands:
                return quota_bands[provider]

            if quota_levels is not None and provider in quota_levels:
                return _BAND_FOR_LEVEL[quota_levels[provider]]

            return quota_band_for_percent(
                quota.codex_remaining_percent
                if provider is Provider.CODEX
                else quota.claude_remaining_percent
            )

        owner = self.choose_owner(previous_owner)
        ownership_note = ""
        other = self.reviewer_for(owner)

        # POLICY.md sec. 8/9: never spend an EMERGENCY provider as the implementer
        # when the other one is not also in EMERGENCY (Claude-first while Codex is low).
        if band_for(owner) is QuotaBand.EMERGENCY and band_for(other) is not QuotaBand.EMERGENCY:
            ownership_note = (
                f"Ownership: {other.value}-first because {owner.value} is in quota "
                "EMERGENCY (POLICY.md sec. 9); the 50/50 scheduler state is unchanged."
            )
            owner = other

        reviewer = self.reviewer_for(owner)
        band = band_for(owner)
        review_deferred = band_for(reviewer) is QuotaBand.EMERGENCY

        implementer_difficulty = self.apply_quota_conservation(
            effective_difficulty,
            band,
            category,
        )

        implementer_model = self.choose_implementer(
            provider=owner,
            difficulty=implementer_difficulty,
        )

        reviewer_model = self.choose_reviewer(
            provider=reviewer,
            difficulty=effective_difficulty,
        )

        return RoutingDecision(
            owner=owner,
            reviewer=reviewer,
            implementer_model=implementer_model,
            reviewer_model=reviewer_model,
            difficulty=effective_difficulty,
            task_category=category,
            quota_band=band,
            review_deferred=review_deferred,
            ownership_note=ownership_note,
        )

    @staticmethod
    def _codex_implementer(
        difficulty: Difficulty,
    ) -> ModelChoice:
        routes = {
            Difficulty.SCOUT: ModelChoice(
                provider=Provider.CODEX,
                model="gpt-5.6-luna",
                effort="low",
                reason="Cheap repository scouting or simple work.",
            ),
            Difficulty.ROUTINE: ModelChoice(
                provider=Provider.CODEX,
                model="gpt-5.6-terra",
                effort="medium",
                reason="Routine implementation and tests.",
            ),
            Difficulty.SERIOUS: ModelChoice(
                provider=Provider.CODEX,
                model="gpt-5.6-sol",
                effort="medium",
                reason="Main Codex engineering workhorse.",
            ),
            Difficulty.HARD: ModelChoice(
                provider=Provider.CODEX,
                model="gpt-6-astra",
                effort="low",
                reason="Hard engineering escalation using Astra Low.",
            ),
            Difficulty.CRITICAL: ModelChoice(
                provider=Provider.CODEX,
                model="gpt-6-astra",
                effort="medium",
                reason="Critical engineering escalation.",
            ),
        }

        return routes[difficulty]

    @staticmethod
    def _claude_implementer(
        difficulty: Difficulty,
    ) -> ModelChoice:
        routes = {
            Difficulty.SCOUT: ModelChoice(
                provider=Provider.CLAUDE,
                model="haiku",
                effort="low",
                reason="Cheap scouting and simple work.",
            ),
            Difficulty.ROUTINE: ModelChoice(
                provider=Provider.CLAUDE,
                model="sonnet",
                effort="medium",
                reason="Routine implementation work.",
            ),
            Difficulty.SERIOUS: ModelChoice(
                provider=Provider.CLAUDE,
                model="sonnet",
                effort="high",
                reason="Main Claude engineering workhorse.",
            ),
            Difficulty.HARD: ModelChoice(
                provider=Provider.CLAUDE,
                model="sonnet",
                effort="high",
                reason="Hard implementation before Opus escalation.",
            ),
            Difficulty.CRITICAL: ModelChoice(
                provider=Provider.CLAUDE,
                model="opus",
                effort="high",
                reason="Critical architecture/debugging escalation.",
            ),
        }

        return routes[difficulty]

    @staticmethod
    def _codex_reviewer(
        difficulty: Difficulty,
    ) -> ModelChoice:
        if difficulty is Difficulty.SCOUT:
            return ModelChoice(
                provider=Provider.CODEX,
                model="gpt-5.6-luna",
                effort="low",
                reason="Cheap scouting cross-provider review.",
            )

        if difficulty is Difficulty.ROUTINE:
            return ModelChoice(
                provider=Provider.CODEX,
                model="gpt-5.6-terra",
                effort="medium",
                reason="Routine cross-provider review.",
            )

        if difficulty is Difficulty.SERIOUS:
            return ModelChoice(
                provider=Provider.CODEX,
                model="gpt-5.6-sol",
                effort="medium",
                reason="Serious cross-provider review.",
            )

        if difficulty is Difficulty.HARD:
            return ModelChoice(
                provider=Provider.CODEX,
                model="gpt-6-astra",
                effort="low",
                reason="Hard adversarial review.",
            )

        return ModelChoice(
            provider=Provider.CODEX,
            model="gpt-6-astra",
            effort="medium",
            reason="Critical adversarial review.",
        )

    @staticmethod
    def _claude_reviewer(
        difficulty: Difficulty,
    ) -> ModelChoice:
        if difficulty is Difficulty.SCOUT:
            return ModelChoice(
                provider=Provider.CLAUDE,
                model="haiku",
                effort="medium",
                reason="Cheap cross-provider review.",
            )

        if difficulty in {
            Difficulty.ROUTINE,
            Difficulty.SERIOUS,
            Difficulty.HARD,
        }:
            return ModelChoice(
                provider=Provider.CLAUDE,
                model="sonnet",
                effort="high",
                reason="Primary Claude review model.",
            )

        return ModelChoice(
            provider=Provider.CLAUDE,
            model="opus",
            effort="high",
            reason="Critical adversarial review.",
        )


def _self_test() -> None:
    router = ModelRouter()

    first = router.choose_owner(None)
    second = router.choose_owner(first)
    third = router.choose_owner(second)

    assert first is Provider.CODEX
    assert second is Provider.CLAUDE
    assert third is Provider.CODEX

    assert router.reviewer_for(Provider.CODEX) is Provider.CLAUDE
    assert router.reviewer_for(Provider.CLAUDE) is Provider.CODEX

    codex_serious = router.choose_implementer(
        provider=Provider.CODEX,
        difficulty=Difficulty.SERIOUS,
    )
    assert codex_serious.model == "gpt-5.6-sol"

    claude_serious = router.choose_implementer(
        provider=Provider.CLAUDE,
        difficulty=Difficulty.SERIOUS,
    )
    assert claude_serious.model == "sonnet"

    codex_critical = router.choose_implementer(
        provider=Provider.CODEX,
        difficulty=Difficulty.CRITICAL,
    )
    assert codex_critical.model == "gpt-6-astra"

    claude_critical = router.choose_implementer(
        provider=Provider.CLAUDE,
        difficulty=Difficulty.CRITICAL,
    )
    assert claude_critical.model == "opus"

    for difficulty in Difficulty:
        owner = Provider.CODEX
        reviewer = router.reviewer_for(owner)

        implementer = router.choose_implementer(
            provider=owner,
            difficulty=difficulty,
        )
        review_model = router.choose_reviewer(
            provider=reviewer,
            difficulty=difficulty,
        )

        assert implementer.provider is Provider.CODEX
        assert review_model.provider is Provider.CLAUDE

    # Step 7 live-validation contract: a SCOUT Claude-owned task must
    # route to Claude Haiku (low effort) implementing and Codex
    # gpt-5.6-luna reviewing read-only.
    scout_owner = Provider.CLAUDE
    scout_reviewer = router.reviewer_for(scout_owner)

    assert scout_reviewer is Provider.CODEX

    scout_implementer = router.choose_implementer(
        provider=scout_owner,
        difficulty=Difficulty.SCOUT,
    )

    assert scout_implementer.provider is Provider.CLAUDE
    assert scout_implementer.model == "haiku"
    assert scout_implementer.effort == "low"

    scout_review_model = router.choose_reviewer(
        provider=scout_reviewer,
        difficulty=Difficulty.SCOUT,
    )

    assert scout_review_model.provider is Provider.CODEX
    assert scout_review_model.model == "gpt-5.6-luna"

    # Higher-difficulty Codex reviewer ladders are unchanged by the
    # SCOUT-specific fix above.
    routine_review_model = router.choose_reviewer(
        provider=Provider.CODEX,
        difficulty=Difficulty.ROUTINE,
    )
    assert routine_review_model.model == "gpt-5.6-terra"

    serious_review_model = router.choose_reviewer(
        provider=Provider.CODEX,
        difficulty=Difficulty.SERIOUS,
    )
    assert serious_review_model.model == "gpt-5.6-sol"

    hard_review_model = router.choose_reviewer(
        provider=Provider.CODEX,
        difficulty=Difficulty.HARD,
    )
    assert hard_review_model.model == "gpt-6-astra"
    assert hard_review_model.effort == "low"

    critical_review_model = router.choose_reviewer(
        provider=Provider.CODEX,
        difficulty=Difficulty.CRITICAL,
    )
    assert critical_review_model.model == "gpt-6-astra"
    assert critical_review_model.effort == "medium"

    # 50/50 ownership behavior is unaffected by the SCOUT reviewer fix.
    assert router.choose_owner(None) is Provider.CODEX
    assert router.choose_owner(Provider.CODEX) is Provider.CLAUDE
    assert router.choose_owner(Provider.CLAUDE) is Provider.CODEX

    # ================================================================
    # Task-aware routing upgrade (sections 1-7)
    # ================================================================

    # --- difficulty ordering / escalation ladder ----------------------

    assert difficulty_rank(Difficulty.SCOUT) < difficulty_rank(
        Difficulty.CRITICAL
    )
    assert max_difficulty(Difficulty.SCOUT, Difficulty.HARD) is (
        Difficulty.HARD
    )

    assert escalate_difficulty(Difficulty.SCOUT) is Difficulty.ROUTINE
    assert escalate_difficulty(Difficulty.ROUTINE) is Difficulty.SERIOUS
    assert escalate_difficulty(Difficulty.SERIOUS) is Difficulty.HARD
    assert escalate_difficulty(Difficulty.HARD) is Difficulty.CRITICAL
    # Bounded ceiling: escalating CRITICAL never wraps/loops.
    assert escalate_difficulty(Difficulty.CRITICAL) is Difficulty.CRITICAL

    # --- task-category classification (deterministic, not NLP) --------

    assert (
        classify_task_category(
            "Change authentication security and rotate a credential."
        )
        is TaskCategory.SECURITY_SENSITIVE
    )
    assert (
        classify_task_category(
            "Reconcile the module architecture and redesign the layer."
        )
        is TaskCategory.ARCHITECTURE
    )
    assert (
        classify_task_category(
            "Wire cross-module integration between two districts."
        )
        is TaskCategory.INTEGRATION
    )
    assert (
        classify_task_category(
            "Debug the failure and find the root cause."
        )
        is TaskCategory.DEBUGGING
    )
    assert (
        classify_task_category(
            "This is a flaky test; repair the test."
        )
        is TaskCategory.TEST_REPAIR
    )
    assert (
        classify_task_category(
            "Update docs and fix a docstring."
        )
        is TaskCategory.DOCUMENTATION
    )
    assert (
        classify_task_category(
            "Inspect a few files and survey the codebase."
        )
        is TaskCategory.EXPLORATION
    )
    assert (
        classify_task_category(
            "Make a trivial edit: a tiny deterministic one-line change."
        )
        is TaskCategory.TRIVIAL_EDIT
    )
    assert (
        classify_task_category(
            "Implement the ordinary feature as described."
        )
        is TaskCategory.IMPLEMENTATION
    )

    # Invalid/unknown classification fails safely: unmatched or empty
    # text defaults to IMPLEMENTATION (never crashes routing), and an
    # out-of-band category string is rejected by the enum itself
    # (fail closed, not silently coerced).
    assert classify_task_category("") is TaskCategory.IMPLEMENTATION
    assert (
        classify_task_category("asdkjhaskjdh nonsense text")
        is TaskCategory.IMPLEMENTATION
    )
    try:
        TaskCategory("not_a_real_category")
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Unknown task category strings must fail closed"
        )

    # Negation-aware: a prohibition mentioning "architecture"/"security"
    # must not misclassify -- this is the same protection approval.py
    # relies on, shared via text_signals.py.
    assert (
        classify_task_category(
            "Do not modify architecture. Do not modify security code."
        )
        is TaskCategory.IMPLEMENTATION
    )

    # --- category floor only ever pushes difficulty UP -----------------

    assert (
        apply_category_floor(Difficulty.SCOUT, TaskCategory.SECURITY_SENSITIVE)
        is Difficulty.HARD
    )
    assert (
        apply_category_floor(Difficulty.CRITICAL, TaskCategory.SECURITY_SENSITIVE)
        is Difficulty.CRITICAL
    )
    assert (
        apply_category_floor(Difficulty.SCOUT, TaskCategory.ARCHITECTURE)
        is Difficulty.SERIOUS
    )
    # Low-risk categories never lower an explicitly higher difficulty.
    assert (
        apply_category_floor(Difficulty.SERIOUS, TaskCategory.TRIVIAL_EDIT)
        is Difficulty.SERIOUS
    )
    assert (
        apply_category_floor(Difficulty.SCOUT, TaskCategory.IMPLEMENTATION)
        is Difficulty.SCOUT
    )

    # --- quota bands -----------------------------------------------

    assert quota_band_for_percent(None) is QuotaBand.UNKNOWN
    assert quota_band_for_percent(80.0) is QuotaBand.NORMAL
    assert quota_band_for_percent(60.0) is QuotaBand.NORMAL
    assert quota_band_for_percent(45.0) is QuotaBand.CONSERVE
    assert quota_band_for_percent(30.0) is QuotaBand.CONSERVE
    assert quota_band_for_percent(20.0) is QuotaBand.RESERVE
    assert quota_band_for_percent(15.0) is QuotaBand.RESERVE
    assert quota_band_for_percent(5.0) is QuotaBand.EMERGENCY
    assert quota_band_for_percent(0.0) is QuotaBand.EMERGENCY

    # --- quota-aware conservation: never below minimum for risk --------

    # NORMAL / UNKNOWN: no change at any difficulty.
    for band in (QuotaBand.NORMAL, QuotaBand.UNKNOWN):
        for difficulty in Difficulty:
            assert (
                apply_quota_conservation(
                    difficulty, band, TaskCategory.IMPLEMENTATION
                )
                is difficulty
            )

    # CONSERVE: SERIOUS -> ROUTINE; SCOUT/ROUTINE untouched;
    # HARD/CRITICAL exempt.
    assert (
        apply_quota_conservation(
            Difficulty.SERIOUS, QuotaBand.CONSERVE, TaskCategory.IMPLEMENTATION
        )
        is Difficulty.ROUTINE
    )
    assert (
        apply_quota_conservation(
            Difficulty.ROUTINE, QuotaBand.CONSERVE, TaskCategory.IMPLEMENTATION
        )
        is Difficulty.ROUTINE
    )
    assert (
        apply_quota_conservation(
            Difficulty.HARD, QuotaBand.CONSERVE, TaskCategory.IMPLEMENTATION
        )
        is Difficulty.HARD
    )

    # RESERVE / EMERGENCY: SERIOUS and ROUTINE both capped at SCOUT;
    # HARD/CRITICAL exempt ("reserve strongest models for serious/hard
    # tasks" / "do not spend premium models on trivial work").
    for band in (QuotaBand.RESERVE, QuotaBand.EMERGENCY):
        assert (
            apply_quota_conservation(
                Difficulty.SERIOUS, band, TaskCategory.IMPLEMENTATION
            )
            is Difficulty.SCOUT
        )
        assert (
            apply_quota_conservation(
                Difficulty.ROUTINE, band, TaskCategory.IMPLEMENTATION
            )
            is Difficulty.SCOUT
        )
        assert (
            apply_quota_conservation(
                Difficulty.CRITICAL, band, TaskCategory.IMPLEMENTATION
            )
            is Difficulty.CRITICAL
        )

    # Never silently downgrade below the minimum capability required
    # for risk: SECURITY_SENSITIVE work is exempt from conservation at
    # every band, even EMERGENCY.
    assert (
        apply_quota_conservation(
            Difficulty.SERIOUS,
            QuotaBand.EMERGENCY,
            TaskCategory.SECURITY_SENSITIVE,
        )
        is Difficulty.SERIOUS
    )

    # --- route(): full composed routing decision ------------------

    # SCOUT + trivial edit, both directions.
    scout_trivial_claude = router.route(
        description="Make a trivial edit: a tiny deterministic fix.",
        base_difficulty=Difficulty.SCOUT,
        previous_owner=Provider.CODEX,
    )
    assert scout_trivial_claude.owner is Provider.CLAUDE
    assert scout_trivial_claude.reviewer is Provider.CODEX
    assert scout_trivial_claude.task_category is TaskCategory.TRIVIAL_EDIT
    assert scout_trivial_claude.difficulty is Difficulty.SCOUT
    assert scout_trivial_claude.implementer_model.model == "haiku"
    assert scout_trivial_claude.reviewer_model.model == "gpt-5.6-luna"

    scout_trivial_codex = router.route(
        description="Make a trivial edit: a tiny deterministic fix.",
        base_difficulty=Difficulty.SCOUT,
        previous_owner=Provider.CLAUDE,
    )
    assert scout_trivial_codex.owner is Provider.CODEX
    assert scout_trivial_codex.reviewer is Provider.CLAUDE
    assert scout_trivial_codex.implementer_model.model == "gpt-5.6-luna"
    assert scout_trivial_codex.reviewer_model.model == "haiku"

    # ROUTINE + implementation, both directions.
    routine_claude = router.route(
        description="Implement the ordinary feature as described.",
        base_difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CODEX,
    )
    assert routine_claude.task_category is TaskCategory.IMPLEMENTATION
    assert routine_claude.implementer_model.model == "sonnet"
    assert routine_claude.reviewer_model.model == "gpt-5.6-terra"

    routine_codex = router.route(
        description="Implement the ordinary feature as described.",
        base_difficulty=Difficulty.ROUTINE,
        previous_owner=Provider.CLAUDE,
    )
    assert routine_codex.implementer_model.model == "gpt-5.6-terra"
    assert routine_codex.reviewer_model.model == "sonnet"

    # SERIOUS + debugging, both directions.
    serious_debug_claude = router.route(
        description="Debug the failure and find the root cause.",
        base_difficulty=Difficulty.SERIOUS,
        previous_owner=Provider.CODEX,
    )
    assert serious_debug_claude.task_category is TaskCategory.DEBUGGING
    assert serious_debug_claude.difficulty is Difficulty.SERIOUS
    assert serious_debug_claude.implementer_model.model == "sonnet"
    assert serious_debug_claude.implementer_model.effort == "high"
    assert serious_debug_claude.reviewer_model.model == "gpt-5.6-sol"

    serious_debug_codex = router.route(
        description="Debug the failure and find the root cause.",
        base_difficulty=Difficulty.SERIOUS,
        previous_owner=Provider.CLAUDE,
    )
    assert serious_debug_codex.implementer_model.model == "gpt-5.6-sol"
    assert serious_debug_codex.reviewer_model.model == "sonnet"

    # HARD + architecture, both directions.
    hard_arch_claude = router.route(
        description="Reconcile the module architecture and redesign it.",
        base_difficulty=Difficulty.HARD,
        previous_owner=Provider.CODEX,
    )
    assert hard_arch_claude.task_category is TaskCategory.ARCHITECTURE
    assert hard_arch_claude.difficulty is Difficulty.HARD
    assert hard_arch_claude.implementer_model.model == "sonnet"
    assert hard_arch_claude.reviewer_model.model == "gpt-6-astra"

    hard_arch_codex = router.route(
        description="Reconcile the module architecture and redesign it.",
        base_difficulty=Difficulty.HARD,
        previous_owner=Provider.CLAUDE,
    )
    assert hard_arch_codex.implementer_model.model == "gpt-6-astra"
    assert hard_arch_codex.reviewer_model.model == "sonnet"

    # CRITICAL + high-risk reasoning (security), both directions.
    critical_security_claude = router.route(
        description="Critical: change encryption and rotate a secret.",
        base_difficulty=Difficulty.CRITICAL,
        previous_owner=Provider.CODEX,
    )
    assert (
        critical_security_claude.task_category
        is TaskCategory.SECURITY_SENSITIVE
    )
    assert critical_security_claude.difficulty is Difficulty.CRITICAL
    assert critical_security_claude.implementer_model.model == "opus"
    assert critical_security_claude.reviewer_model.model == "gpt-6-astra"

    critical_security_codex = router.route(
        description="Critical: change encryption and rotate a secret.",
        base_difficulty=Difficulty.CRITICAL,
        previous_owner=Provider.CLAUDE,
    )
    assert critical_security_codex.implementer_model.model == "gpt-6-astra"
    assert critical_security_codex.reviewer_model.model == "opus"

    # A cheap category floor still applies even at a low requested
    # difficulty -- security work is never routed as cheaply as SCOUT.
    security_from_scout = router.route(
        description="Rotate a credential and fix an authentication bug.",
        base_difficulty=Difficulty.SCOUT,
        previous_owner=Provider.CODEX,
    )
    assert security_from_scout.difficulty is Difficulty.HARD
    assert security_from_scout.implementer_model.model == "sonnet"
    assert security_from_scout.reviewer_model.model == "gpt-6-astra"

    # --- reviewer role influences selection: a quota-conserved cheap
    #     implementer still gets a full-strength independent reviewer.

    conserved = router.route(
        description="Implement the ordinary feature as described.",
        base_difficulty=Difficulty.SERIOUS,
        previous_owner=Provider.CODEX,
        quota_state=QuotaState(claude_remaining_percent=45.0),
    )
    assert conserved.owner is Provider.CLAUDE
    assert conserved.quota_band is QuotaBand.CONSERVE
    # Implementer conserved down from SERIOUS -> ROUTINE...
    assert conserved.implementer_model.model == "sonnet"
    assert conserved.implementer_model.effort == "medium"
    # ...but the reviewer stays at the unconserved SERIOUS tier.
    assert conserved.reviewer_model.model == "gpt-5.6-sol"

    # --- honest per-provider levels (UNKNOWN / NORMAL / CONSTRAINED / EXHAUSTED)
    unk = router.route(
        description="Implement the ordinary feature as described.",
        base_difficulty=Difficulty.SERIOUS,
        previous_owner=Provider.CODEX,
        quota_levels={p: ProviderQuota.UNKNOWN for p in Provider},
    )
    # UNKNOWN reduces no capability: identical to the unconserved route.
    assert unk.quota_band is QuotaBand.UNKNOWN
    assert unk.implementer_model.effort == "high"
    constrained = router.route(
        description="Implement the ordinary feature as described.",
        base_difficulty=Difficulty.SERIOUS,
        previous_owner=Provider.CODEX,
        quota_levels={Provider.CLAUDE: ProviderQuota.CONSTRAINED},
    )
    assert constrained.quota_band is QuotaBand.RESERVE
    assert constrained.implementer_model.model == "haiku"  # conserved down
    assert constrained.reviewer_model.model == "gpt-5.6-sol"  # reviewer never conserved
    # Critical/security work is never downgraded to save quota.
    sec_constrained = router.route(
        description="Change the authentication flow.",
        base_difficulty=Difficulty.HARD,
        previous_owner=Provider.CODEX,
        quota_levels={Provider.CLAUDE: ProviderQuota.CONSTRAINED},
    )
    assert sec_constrained.implementer_model.model == "sonnet"
    assert sec_constrained.implementer_model.effort == "high"
    assert sec_constrained.reviewer_model.model == "gpt-6-astra"

    # --- 50/50 ownership remains intact through route() ---------------

    alternation_owner = None
    seen_owners: list[Provider] = []
    for _ in range(4):
        decision = router.route(
            description="Implement the ordinary feature as described.",
            base_difficulty=Difficulty.ROUTINE,
            previous_owner=alternation_owner,
        )
        seen_owners.append(decision.owner)
        alternation_owner = decision.owner

    assert seen_owners == [
        Provider.CODEX,
        Provider.CLAUDE,
        Provider.CODEX,
        Provider.CLAUDE,
    ]


if __name__ == "__main__":
    _self_test()
