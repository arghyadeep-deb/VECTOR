import sys
import asyncio
import datetime
import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG


@dataclass
class Candidate:
    action_type: str
    params: dict
    goal_ids: list[str] = field(default_factory=list)
    confidence: float = 0.5
    urgency: float = 0.5
    timing_score: float = 1.0
    estimated_cost_inr: float = 0.0
    source: str = "system"
    # R7 (Task 92) — instance identity, NOT a policy/situation identity.
    # candidate_id: unique per Candidate object the moment it is constructed
    # (every generated/scored candidate gets one, whether or not it ever
    # wins). decision_id: which evaluate() call this candidate belongs to —
    # "" until DecisionEngine.evaluate() assigns it (a Candidate built
    # outside evaluate(), e.g. in isolated tests, legitimately has no
    # decision yet). Neither is ever used as, or derived from,
    # PolicyMemory.make_situation_hash()'s reusable (action_type, params)
    # identity — see decision_id's own note on DecisionEngine.evaluate().
    candidate_id: str = field(default_factory=lambda: "c:" + uuid.uuid4().hex)
    decision_id: str = ""
    # Computed during scoring
    goal_alignment: float = 0.0
    policy_score: float = 0.5
    total_score: float = 0.0
    # RULE 8 — past reasoning injected before scoring
    reasoning_steps: list[str] = field(default_factory=list)
    reasoning_chain: list[dict] = field(default_factory=list)
    # RULE 1 — world-state snapshot injected before scoring (ContextEngine).
    # Available to scoring/audit, but does NOT currently change the score
    # formula itself — see DecisionEngine.evaluate() docstring.
    context_snapshot: dict = field(default_factory=dict)


@dataclass
class Decision:
    winner: Candidate
    all_candidates: list[Candidate]
    reasoning: str
    timestamp: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())
    evaluated: int = 0
    reasoning_chain: list[str] = field(default_factory=list)
    # R7 (Task 92) — one decision_id per evaluate() call; every candidate in
    # `all_candidates` (including `winner`) is stamped with this same value
    # via Candidate.decision_id. See DecisionEngine.evaluate().
    decision_id: str = field(default_factory=lambda: "d:" + uuid.uuid4().hex)


class DecisionEngine:
    """
    Scores 4 candidates per decision using the 5-factor weighted formula.
    RULE 7: policy.get_score() BEFORE. policy.update_from_outcome() AFTER.
    ALL candidates logged — including rejected. No silent drops.

    Scoring: goal_alignment(30%) + confidence(25%) + policy(20%) +
             urgency(15%) + timing(10%) - cost(5%)
    """

    W_GOAL = 0.30
    W_CONF = 0.25
    W_POLICY = 0.20
    W_URGENCY = 0.15
    W_TIMING = 0.10
    W_COST = 0.05

    def __init__(self):
        self._policy = None
        self._goals = None
        self._memory = None
        self._reasoning_bank = None
        self._context_engine = None
        self._neural_trainer = None
        self._epistemic = None
        self._metacognition = None
        self._correction_learner = None
        self._agent_registry = None
        self._plan_store = None
        self._mc_bias_cache = None
        self._mc_cache_time = 0.0
        self._decision_count = 0
        # Neural learning loop state (closed by record_outcome)
        self._last_neural = None          # {"state": np.ndarray, "action": int}
        self._action_index: dict[str, int] = {}  # action_type -> stable action id
        self._neural_action_dim = 16
        # R6 (Task 91) — staleness-only candidate diversity. Process-local,
        # not persisted: a restart clears all streaks by design. Tracks how
        # many CONSECUTIVE evaluate() calls ended with the same (action_type,
        # params) identity as the final winner. See
        # _select_staleness_aware_winner() for the full contract.
        self._winner_streak_hash: str | None = None
        self._winner_streak_count: int = 0
        logger.info("[VECTOR][decision_engine] initialized")

    def _get_reasoning_bank(self):
        """ReasoningBank: inject past reasoning chains before scoring (RULE 8)."""
        if self._reasoning_bank is None:
            try:
                try:
                    from vectorcode.src.reasoning_bank import ReasoningBank
                except ImportError:
                    # importlib fallback: load by absolute file path so sys.path gaps never disable RULE 8
                    import importlib.util as _ilu
                    _rb_path = Path(__file__).parent.parent.parent / "vectorcode" / "src" / "reasoning_bank.py"
                    _spec = _ilu.spec_from_file_location("vectorcode.src.reasoning_bank", _rb_path)
                    _mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
                    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
                    ReasoningBank = _mod.ReasoningBank
                self._reasoning_bank = ReasoningBank()
                self._reasoning_bank.load()
                _entry_count = len(self._reasoning_bank._entries)
                logger.info(
                    "[VECTOR][decision_engine] ReasoningBank online — RULE 8 active ({} entries)",
                    _entry_count,
                )
            except Exception as e:
                logger.warning(
                    "[VECTOR][decision_engine] ReasoningBank unavailable — RULE 8 disabled: {}", e
                )
                self._reasoning_bank = False  # sentinel: do not retry
        return self._reasoning_bank if self._reasoning_bank is not False else None

    def _get_context_engine(self):
        """ContextEngine: world-state snapshot injected before scoring (RULE 1)."""
        if self._context_engine is None:
            from core.loop.context_engine import ContextEngine
            self._context_engine = ContextEngine()
        return self._context_engine

    def _get_agent_registry(self):
        """R23 self-model: the real, live AgentRegistry singleton -- the
        SAME one Governor.dispatch() itself reads for capability routing.
        No new registry, no new state."""
        if self._agent_registry is None:
            from core.city.agent_registry import get_registry
            self._agent_registry = get_registry()
        return self._agent_registry

    def _get_plan_store(self):
        """R23 world-model: the real, live PlanStore singleton -- the SAME
        one AutonomousLoop._get_plan_store()/_get_plan_candidates() itself
        reads. No new store, no new state."""
        if self._plan_store is None:
            from core.runtime.plans import get_plan_store
            self._plan_store = get_plan_store()
        return self._plan_store

    def _get_policy(self):
        if self._policy is None:
            from core.memory.policy import PolicyMemory
            self._policy = PolicyMemory()
        return self._policy

    def _get_goals(self):
        if self._goals is None:
            from core.brain.goal_system import GoalSystem
            self._goals = GoalSystem()
        return self._goals

    def _get_memory(self):
        if self._memory is None:
            from core.memory.episodic import EpisodicMemory
            self._memory = EpisodicMemory()
        return self._memory

    def _get_correction_learner(self):
        """R8 — explicit owner-correction lessons, bounded decision-path influence."""
        if self._correction_learner is None:
            try:
                from core.memory.correction_learner import CorrectionLearner
                self._correction_learner = CorrectionLearner()
            except Exception as e:
                logger.debug("[VECTOR][decision_engine] correction_learner unavailable: {}", e)
                self._correction_learner = False
        return None if self._correction_learner is False else self._correction_learner

    def _get_neural_trainer(self):
        if self._neural_trainer is None:
            try:
                from vectorcode.src.neural_training import VECTORTrainer
                self._neural_trainer = VECTORTrainer("a2c", state_dim=8, action_dim=16)
            except Exception as e:
                logger.debug("[VECTOR][decision_engine] neural trainer unavailable: {}", e)
                self._neural_trainer = False
        return None if self._neural_trainer is False else self._neural_trainer

    def _action_id(self, action_type: str) -> int:
        """Map an action_type to a stable index in [0, action_dim)."""
        if action_type not in self._action_index:
            self._action_index[action_type] = len(self._action_index) % self._neural_action_dim
        return self._action_index[action_type]

    def record_outcome(self, reward: float, next_state=None) -> None:
        """Close the neural learning loop: train the policy network on the real
        reward for the action it last observed. Called by the autonomous loop
        AFTER an action executes and its 5-factor reward is computed.

        This is what makes the network actually LEARN — previously select_action
        was called and discarded, and the net never saw an outcome.
        """
        if not self._last_neural:
            return
        trainer = self._get_neural_trainer()
        if trainer is None:
            return
        try:
            import numpy as np
            state = self._last_neural["state"]
            exp = {
                "state": state,
                "action": int(self._last_neural["action"]),
                "reward": float(reward),
                "next_state": next_state if next_state is not None else state,
                "done": True,
            }
            metrics = trainer.train_episode([exp])
            logger.debug(
                "[VECTOR][decision_engine] neural learn: reward={:.3f} loss={:.4f} ep={}",
                reward, metrics.get("total", metrics.get("loss", 0.0)), metrics.get("episode", 0),
            )
            # Periodic checkpoint with a real path (old code called save_checkpoint()
            # with no arg → TypeError, so it never actually saved).
            if self._decision_count % 100 == 0:
                from core.runtime_paths import data_path
                ckpt = Path(data_path("models")) / "neural_policy.pt"
                trainer.save_checkpoint(ckpt)
        except Exception as e:
            logger.debug("[VECTOR][decision_engine] record_outcome skipped: {}", e)
        finally:
            self._last_neural = None

    def _get_epistemic(self):
        if self._epistemic is None:
            try:
                from core.brain.epistemic_tracker import EpistemicTracker
                self._epistemic = EpistemicTracker()
            except Exception as e:
                logger.debug("[VECTOR][decision_engine] epistemic tracker unavailable: {}", e)
                self._epistemic = False
        return None if self._epistemic is False else self._epistemic

    def _get_metacognition(self):
        if self._metacognition is None:
            try:
                from core.city.meta_cognition import MetaCognition
                self._metacognition = MetaCognition()
            except Exception as e:
                logger.debug("[VECTOR][decision_engine] metacognition unavailable: {}", e)
                self._metacognition = False
        return None if self._metacognition is False else self._metacognition

    def _bias_penalty(self, candidate: Candidate) -> float:
        try:
            import time
            now = time.monotonic()
            if self._mc_bias_cache is None or now - self._mc_cache_time > 300:
                mc = self._get_metacognition()
                if mc is None:
                    self._mc_bias_cache = []
                else:
                    samples = [{
                        "action_type": candidate.action_type,
                        "confidence": candidate.confidence,
                        "params": candidate.params,
                    }]
                    self._mc_bias_cache = mc.detect_bias(samples) or []
                self._mc_cache_time = now

            penalty = 0.0
            for bias in self._mc_bias_cache or []:
                bias_type = str(bias.get("bias_type", "")).lower()
                severity = str(bias.get("severity", "low")).lower()
                weight = {"low": 0.03, "medium": 0.06, "high": 0.10}.get(severity, 0.03)
                if bias_type == "overconfidence" and self._finite(candidate.confidence, 0.0) > 0.85:
                    penalty += weight
                elif bias_type != "overconfidence":
                    penalty += weight * 0.5
            return max(0.0, min(1.0, penalty))
        except Exception as e:
            logger.debug("[VECTOR][decision_engine] bias penalty skipped: {}", e)
            return 0.0

    def _correction_penalty(self, candidate: Candidate) -> float:
        """R8 — bounded [0.0, 0.12] penalty from a real, persisted, explicit
        owner correction lesson whose situation exactly matches this
        candidate's action_type. See
        CorrectionLearner.get_correction_penalty()'s docstring for the full
        exact-match/no-LLM-interpretation rationale and why this is
        deliberately independent of validate_lesson()'s VALIDATED status.

        R9 follow-up (found during R9's own regression pass, same session):
        `get_correction_penalty()` calls into EpisodicMemory.recall() (a real
        FTS5 query against the shared production DB), which under real-world
        DB size/lock contention can be slow. _score_candidate() is a
        synchronous hot path scoring EVERY candidate on EVERY decision — an
        unbounded wait here would reintroduce exactly the class of problem
        R1 (Task 88, core/inference/ollama_safe.py::_multi_backend_fallback)
        already fixed elsewhere in this codebase. Reuses that exact same
        bounded-wait pattern: single-thread executor, future.result(timeout=),
        never blocks the decision path past the deadline. On timeout, treat
        it as "no correction found" (0.0) -- an honest degrade, not a crash,
        and never a false penalty."""
        try:
            if not CONFIG.get("correction_scoring", True):
                return 0.0
            learner = self._get_correction_learner()
            if learner is None:
                return 0.0

            from concurrent.futures import ThreadPoolExecutor
            timeout = float(CONFIG.get("correction_penalty_timeout_sec", 1.5))
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(learner.get_correction_penalty, candidate.action_type)
            try:
                return future.result(timeout=timeout)
            except TimeoutError:
                logger.warning(
                    "[VECTOR][decision_engine] correction_penalty lookup exceeded "
                    "{}s for '{}' -- treating as no-correction-found rather than "
                    "blocking the decision path", timeout, candidate.action_type,
                )
                return 0.0
            finally:
                executor.shutdown(wait=False)
        except Exception as e:
            logger.debug("[VECTOR][decision_engine] correction penalty skipped: {}", e)
            return 0.0

    def _veto_penalty(self, situation_hash: str, candidate: Candidate) -> float:
        """E4 (update-rule audit) — bounded [0.0, 0.10] penalty from
        PolicyMemory.get_veto_count() for this exact canonical situation.

        `veto_count` (Task 89/D3) has existed since R4/R5 specifically to
        track counterfactual-vetoed proposals SEPARATELY from avg_reward —
        but nothing ever read it for scoring (confirmed INERT by direct
        repo-wide audit; see VECTOR_TECHNICAL_KNOWLEDGE/E4_UPDATE_RULE_REPORT.md).
        A candidate whose exact situation has been vetoed many times before
        currently scores no differently than one that has never been
        vetoed at all — this closes that gap with the smallest possible
        wiring, reusing the existing column rather than adding a new one.

        Deliberately a SOFT, bounded nudge, not a hard block: an
        aggressively rising veto_count already has its own hard
        avoidance mechanism (CounterfactualMemory.should_avoid()'s
        Jaccard-similarity check, which can outright block execution) —
        this only makes an already-frequently-vetoed situation slightly
        less likely to keep winning the ranking in the first place,
        mirroring the same bounded-penalty pattern as bias_penalty,
        epistemic_penalty, and correction_penalty. Capped at 0.10 so it
        can shift a close ranking but never dominate the 5-factor formula
        on its own."""
        try:
            if not CONFIG.get("veto_scoring", True):
                return 0.0
            veto_count = self._get_policy().get_veto_count(candidate.action_type, situation_hash)
            return round(min(0.10, veto_count * 0.02), 4)
        except Exception as e:
            logger.debug("[VECTOR][decision_engine] veto penalty skipped: {}", e)
            return 0.0

    def _finite(self, value: float, default: float = 0.0) -> float:
        try:
            value = float(value)
            if math.isnan(value) or math.isinf(value):
                return default
            return value
        except Exception:
            return default

    def _score_goal_alignment(self, candidate: Candidate) -> float:
        """How well does this action serve active goals? 0.0-1.0"""
        if not candidate.goal_ids:
            return 0.3

        goals = self._get_goals().get_active_goals()
        goal_map = {g["id"]: g for g in goals}
        score = 0.0
        for gid in candidate.goal_ids:
            if gid in goal_map:
                g = goal_map[gid]
                priority_weight = g.get("priority", 5) / 10.0
                progress_gap = 1.0 - g.get("progress", 0.0)
                score = max(score, priority_weight * progress_gap)
        return min(1.0, score)

    def _make_situation_hash(self, candidate: Candidate) -> str:
        """
        Task 89 (D2) — delegates to PolicyMemory.make_situation_hash(), the
        single canonical identity function shared by this reader and every
        connected writer in autonomous_loop.py. Previously this method had
        its OWN independent formula (`f"{action_type}:{sorted(params.items())}"`,
        Python repr of a sorted list of tuples) which matched only the
        counterfactual-veto writer and none of the real-outcome writers,
        which used `json.dumps(params, sort_keys=True, default=str)` — two
        different serializations of the same logical situation, hashing
        differently, silently preventing real rewards from ever being read
        back by this method. See core/memory/policy.py's docstring for the
        full "v2:"-prefixed canonicalization and why no migration is needed.
        """
        return self._get_policy().make_situation_hash(candidate.action_type, candidate.params)

    def _epistemic_penalty(self, candidate: Candidate) -> tuple[float, float]:
        """Epistemic confidence dampening (JARVIS Gap 3).

        Returns (factor, confidence) where factor is a multiplier in [0.70, 1.0]:
        - Unknown domain (no belief) → 1.0 (neutral — not penalised for ignorance)
        - Stale belief (TTL expired) → 0.70 (heavy — information may be wrong)
        - Low confidence (<0.3) → 0.80
        - Medium confidence (0.3-0.5) → 0.90
        - High confidence (≥0.5) → 1.0 (well-known domain, no dampening)

        The penalty is applied as a post-score multiplier so the 5-factor
        formula stays intact.  A factor of 1.0 means no change.

        R16 (2026-09-10) — the "domain" key used to be
        `action_type.split("_")[0]`, grouping every action_type by its
        first underscore-delimited token. That was never a deliberate,
        curated domain taxonomy — it was an accidental side effect that
        silently collapsed unrelated real action_types into one shared
        epistemic bucket purely because they happen to start with the same
        word: `daily_digest` (research district) and `daily_review` (2AM
        reflection) both collapsed to `"daily"`; `check_attendance`,
        `check_calendar`, and `check_fatigue` (three unrelated districts)
        all collapsed to `"check"`; `search_web` and `search_arxiv`
        collapsed to `"search"`. A real bad outcome for one of these would
        silently dampen a totally unrelated action_type's score — this was
        live, reachable, unintentional over-generalization, not a
        hypothetical risk (confirmed reproducible via
        `tests/integration/test_epistemic_integration.py::
        test_different_domains_independent`, which failed before this fix
        because its own two fixture action_types, `domain_a_action` and
        `domain_b_action`, happened to collide the same way).
        The domain is now the exact, full `action_type` — identical
        granularity to `PolicyMemory.make_situation_hash()`'s own
        per-action_type identity discipline, and consistent with this
        repo's own established principle that cross-action generalization
        must be an explicit, curated decision (see
        `core/brain/goal_system.py`'s `_TAG_TO_ACTION_TYPE` table), never
        an accidental string-splitting side effect. No architecture
        change: still one flat `claims` row per key, still read via the
        same `get_belief()`/`merge_belief()` calls.
        """
        try:
            if not CONFIG.get("epistemic_scoring", True):
                return 1.0, 0.0
            epistemic = self._get_epistemic()
            if epistemic is None:
                return 1.0, 0.0
            domain = candidate.action_type
            claim_id = f"action_domain:{domain}"
            belief = epistemic.get_belief(claim_id)
            if belief is None:
                # Unknown domain — neutral.  We don't penalise first-time actions.
                return 1.0, 0.0
            if belief.get("stale"):
                logger.debug(
                    "[VECTOR][decision_engine] epistemic STALE for '{}': "
                    "last_verified={}, ttl={}h — dampening 0.70",
                    domain, belief.get("last_verified", "?"),
                    belief.get("ttl_hours", 72),
                )
                return 0.70, 0.0
            conf = belief.get("current_confidence", belief.get("confidence", 0.5))
            if conf < 0.3:
                return 0.80, conf
            if conf < 0.5:
                return 0.90, conf
            return 1.0, conf
        except Exception as e:
            logger.debug("[VECTOR][decision_engine] epistemic_penalty skipped: {}", e)
            return 1.0, 0.0

    def record_epistemic_belief(self, action_type: str, outcome_status: str,
                                reward: float) -> None:
        """Record epistemic belief about an action domain after execution.

        Called by autonomous_loop._act_on() AFTER every action outcome.
        High reward → confidence rises in this domain.
        Low reward → confidence falls, making future actions in this domain
        score lower (epistemic dampening kicks in).

        R16 (2026-09-10): "domain" is the exact, full `action_type` — see
        `_epistemic_penalty()`'s docstring for why the previous
        `action_type.split("_")[0]` grouping was removed (a real,
        confirmed cross-action-type collision defect, not a deliberate
        generalization).
        """
        try:
            if not CONFIG.get("epistemic_scoring", True):
                return
            epistemic = self._get_epistemic()
            if epistemic is None:
                return
            domain = action_type
            claim_id = f"action_domain:{domain}"
            # Clamp reward to [0, 1] — same scale as epistemic confidence
            confidence = max(0.0, min(1.0, reward))
            epistemic.merge_belief(
                claim_id,
                f"last_outcome={outcome_status}",
                confidence,
                "act_loop",
            )
            logger.debug(
                "[VECTOR][decision_engine] epistemic belief updated: "
                "{} → conf={:.3f} (reward={:.3f})",
                claim_id, confidence, reward,
            )
        except Exception as e:
            logger.debug("[VECTOR][decision_engine] record_epistemic_belief skipped: {}", e)

    def decay_epistemic(self) -> int:
        """Apply confidence decay to all epistemic beliefs.

        Called by autonomous_loop._reflect_tick() during the 2AM reflection.
        Ages beliefs so stale information triggers dampening in future decisions.
        Returns the number of beliefs whose confidence was updated.
        """
        try:
            if not CONFIG.get("epistemic_scoring", True):
                return 0
            epistemic = self._get_epistemic()
            if epistemic is None:
                return 0
            count = epistemic.decay_all()
            stale = epistemic.check_staleness()
            if stale:
                logger.info(
                    "[VECTOR][decision_engine] epistemic decay: {} beliefs updated, "
                    "{} now stale: {}",
                    count, len(stale), stale[:5],
                )
            return count
        except Exception as e:
            logger.debug("[VECTOR][decision_engine] decay_epistemic skipped: {}", e)
            return 0

    def _situational_factor(self, candidate: Candidate) -> tuple[float, str]:
        """R22 (2026-09-10) — real, structured situation context now
        consumed by scoring, not merely captured.

        `candidate.context_snapshot` has existed since RULE 1's own
        real, production `ContextEngine.get_world_state()` injection
        (this file's `evaluate()`, a few lines above `_score_candidate`)
        -- but per that code's own comment, it was deliberately never
        read by the score formula. Phase 1's read-only audit (see
        VECTOR_TECHNICAL_KNOWLEDGE/R21_R23_UNDERSTANDING_FOUNDATION_
        REPORT.md) independently found this in three separate
        investigations as the precise missing causal link between real
        situational information and real decisions.

        This is deliberately the SMALLEST real connection, not a new
        subsystem: one already-real field (`presence`, sourced from the
        real FaceDetector via ContextEngine's own sense cache) becomes
        one small, bounded, POST-score multiplier -- the exact same
        shape as the existing `_epistemic_penalty()` mechanism.

        Returns (factor, presence) where factor is a multiplier in
        [1.0, 1.05]:
        - presence == "absent" (the real face detector ran and found no
          one) AND the candidate's action_type is already GREEN (real
          PermissionGateway.classify(), never anything else) -> 1.05 --
          a small boost reflecting VECTOR's own documented purpose (a
          24/7 autonomous system, CLAUDE.md) to make real, safe,
          already-unattended-eligible progress when genuinely
          unsupervised.
        - presence in ("present", "unknown") or missing/malformed, OR
          the action_type is not GREEN -> 1.0 (neutral, no change).
          "unknown" (the real detector never ran) is honestly treated
          as NO SIGNAL, never as "away" -- uncertainty is never
          silently promoted to certainty.
        - any unexpected/malformed context_snapshot shape -> 1.0
          (fails safe, never raises, never penalises).

        This can only ever BOOST an action the real permission system
        has already, independently classified GREEN -- it cannot
        promote a YELLOW/RED/FORBIDDEN/UNKNOWN action_type, and it
        never touches `PermissionGateway`/`core/config.py` in any way.
        A YELLOW/RED candidate that is already winning on its own
        real 5-factor merits can still legitimately be overtaken by a
        real, close, already-GREEN alternative once boosted -- exactly
        the same "situational context changes which legitimate
        strategy wins" behavior `idea_validator.py`'s pre-existing
        Regime gate already demonstrates inside one district, now
        extended into DecisionEngine's own central, shared path.
        """
        try:
            snapshot = candidate.context_snapshot
            if not isinstance(snapshot, dict):
                return 1.0, "malformed"
            presence = snapshot.get("presence")
            if not isinstance(presence, str) or presence not in ("present", "absent", "unknown"):
                return 1.0, "malformed"
            if presence != "absent":
                return 1.0, presence
            from core.loop.permission_gateway import PermissionGateway
            if PermissionGateway().classify(candidate.action_type) != "GREEN":
                return 1.0, presence
            return 1.05, presence
        except Exception:
            return 1.0, "error"

    def _capability_factor(self, candidate: Candidate) -> tuple[float, str]:
        """R23 self-model — a real check of what VECTOR itself currently
        CAN do, consumed at scoring time (before any commitment is made),
        not merely discovered afterward.

        Governor.dispatch() (core/city/governor.py) already performs a
        real, honest "no_capable_agent" refusal when no live agent
        declares a task_type's capability -- but only AFTER a winning
        Candidate has already been selected and dispatch has already been
        attempted. Phase 1's self-model audit found `goal_system.py`/
        `decision_engine.py` never consult agent capabilities before
        THAT point: VECTOR could commit to (score highest, "win") a
        candidate for a capability that does not currently exist,
        discovering the gap only at dispatch. This factor makes the SAME
        real fact Governor already has -- queried from the SAME real,
        live `AgentRegistry` singleton, never a new capability list --
        available one step earlier, so a real, already-capable
        alternative can legitimately outrank an incapable one on its own
        merits, before any commitment.

        Returns (factor, signal) where factor is a multiplier in
        [0.85, 1.0]:
        - some live agent's `capabilities` already includes this exact
          action_type -> 1.0 (neutral -- capability confirmed, no change)
        - no live agent currently declares it -> 0.85 (a real, bounded
          self-knowledge penalty -- NOT a hard block; Governor's own
          honest refusal remains the real, final authority on whether
          dispatch actually proceeds -- this NEVER replaces or bypasses
          it, only informs ranking one step earlier)
        - registry unavailable/errors -> 1.0 (fails safe: VECTOR must
          never penalise a candidate merely because IT couldn't check
          its own capability list -- an inability to self-inspect is not
          evidence of incapability)

        Never touches PermissionGateway/core/config.py/Governor's own
        routing logic in any way -- purely a scoring input.
        """
        try:
            registry = self._get_agent_registry()
            agents = registry.get_all_agents()
        except Exception:
            return 1.0, "error"
        for agent in agents:
            if candidate.action_type in getattr(agent, "capabilities", []):
                return 1.0, "capable"
        return 0.85, "no_capable_agent"

    def _workload_factor(self, candidate: Candidate) -> tuple[float, str]:
        """R23 world-model — a real, already-existing, system-wide fact
        (how much committed work VECTOR currently has in flight) now
        consumed at scoring time.

        `PlanStore.active_plans()` (core/runtime/plans.py) is already
        real and already system-wide/unscoped (Phase 1's world-model
        audit found this exact property) -- but was, before R23, only
        ever read by a plan's OWN owning goal (`_get_plan_candidates()`).
        No new store, no new state, no new query shape.

        Returns (factor, signal) where factor is a multiplier in
        [0.97, 1.0]:
        - VECTOR has at least one real active Plan in flight AND this
          candidate is NOT itself a continuation of an existing plan
          (`source` does not start with "plan:") -> 0.97 -- a small,
          real-world-state-driven preference for finishing committed
          work over starting something new, never a hard block.
        - this candidate IS a real plan-step continuation, OR no active
          plans exist at all -> 1.0 (neutral; nothing to prioritise
          finishing over).
        - PlanStore unavailable/errors -> 1.0 (fails safe).
        """
        try:
            store = self._get_plan_store()
            active = store.active_plans()
        except Exception:
            return 1.0, "error"
        if not active:
            return 1.0, "no_active_plans"
        source = candidate.source or ""
        if source.startswith("plan:"):
            return 1.0, "continues_active_plan"
        return 0.97, "new_work_while_plans_active"

    def _score_candidate(self, candidate: Candidate) -> float:
        """Apply the 5-factor formula + epistemic dampening.
        Mutates candidate with computed scores."""
        situation_hash = self._make_situation_hash(candidate)

        # RULE 7 — get_score() BEFORE every decision
        policy_score = self._get_policy().get_score(candidate.action_type, situation_hash)
        candidate.policy_score = policy_score

        goal_score = self._score_goal_alignment(candidate)
        candidate.goal_alignment = goal_score

        confidence = self._finite(candidate.confidence, 0.0)
        urgency = self._finite(candidate.urgency, 0.0)
        timing_score = self._finite(candidate.timing_score, 0.0)
        estimated_cost = self._finite(candidate.estimated_cost_inr, 0.0)
        cost_penalty = min(1.0, estimated_cost / 10.0)
        bias_penalty = self._bias_penalty(candidate)
        correction_penalty = self._correction_penalty(candidate)
        veto_penalty = self._veto_penalty(situation_hash, candidate)

        total = (
            self.W_GOAL * goal_score
            + self.W_CONF * confidence
            + self.W_POLICY * policy_score
            + self.W_URGENCY * urgency
            + self.W_TIMING * timing_score
            - self.W_COST * cost_penalty
            - bias_penalty
            - correction_penalty
            - veto_penalty
        )

        # Epistemic dampening (JARVIS Gap 3) — post-score multiplier.
        # If the action domain has stale or uncertain beliefs, reduce the score.
        epistemic_factor, epistemic_conf = self._epistemic_penalty(candidate)
        total *= epistemic_factor

        # R22 — real situational context (RULE 1's own context_snapshot,
        # previously captured but never consumed) as a second, independent
        # post-score multiplier. See _situational_factor()'s own docstring.
        situational_factor, situational_signal = self._situational_factor(candidate)
        total *= situational_factor

        # R23 — real self-model (capability existence) and real world-model
        # (current in-flight commitments) as two further, independent,
        # bounded post-score multipliers. See each method's own docstring.
        capability_factor, capability_signal = self._capability_factor(candidate)
        total *= capability_factor
        workload_factor, workload_signal = self._workload_factor(candidate)
        total *= workload_factor

        candidate.total_score = round(max(0.0, min(1.0, total)), 4)
        candidate.reasoning_chain = [
            {"factor": "goal_alignment", "value": goal_score, "weight": self.W_GOAL},
            {"factor": "confidence", "value": confidence, "weight": self.W_CONF},
            {"factor": "policy_score", "value": policy_score, "weight": self.W_POLICY},
            {"factor": "urgency", "value": urgency, "weight": self.W_URGENCY},
            {"factor": "timing_score", "value": timing_score, "weight": self.W_TIMING},
            {"factor": "cost_penalty", "value": cost_penalty, "weight": -self.W_COST},
        ]
        if bias_penalty > 0.0:
            candidate.reasoning_chain.append(
                {"factor": "meta_cognition", "value": bias_penalty, "weight": -1.0}
            )
        if correction_penalty > 0.0:
            candidate.reasoning_chain.append(
                {"factor": "owner_correction", "value": correction_penalty, "weight": -1.0}
            )
        if veto_penalty > 0.0:
            candidate.reasoning_chain.append(
                {"factor": "veto_history", "value": veto_penalty, "weight": -1.0}
            )
        if epistemic_factor < 1.0:
            candidate.reasoning_chain.append(
                {"factor": "epistemic_confidence", "value": epistemic_conf,
                 "weight": epistemic_factor}
            )
        if situational_factor != 1.0:
            candidate.reasoning_chain.append(
                {"factor": "situational_context", "value": situational_signal,
                 "weight": situational_factor}
            )
        if capability_factor != 1.0:
            candidate.reasoning_chain.append(
                {"factor": "self_model_capability", "value": capability_signal,
                 "weight": capability_factor}
            )
        if workload_factor != 1.0:
            candidate.reasoning_chain.append(
                {"factor": "world_model_workload", "value": workload_signal,
                 "weight": workload_factor}
            )
        candidate.reasoning_steps.extend([
            f"goal_alignment={goal_score:.3f}",
            f"confidence={confidence:.3f}",
            f"policy_score={policy_score:.3f}",
            f"urgency={urgency:.3f}",
            f"timing_score={timing_score:.3f}",
            f"cost_penalty={cost_penalty:.3f}",
        ])
        if bias_penalty > 0.0:
            candidate.reasoning_steps.append(f"meta_cognition bias_penalty={bias_penalty:.3f}")
        if correction_penalty > 0.0:
            candidate.reasoning_steps.append(f"owner_correction penalty={correction_penalty:.3f}")
        if veto_penalty > 0.0:
            candidate.reasoning_steps.append(f"veto_history penalty={veto_penalty:.3f}")
        if epistemic_factor < 1.0:
            candidate.reasoning_steps.append(
                f"epistemic_factor={epistemic_factor:.2f} "
                f"(conf={epistemic_conf:.3f})"
            )
        if situational_factor != 1.0:
            candidate.reasoning_steps.append(
                f"situational_factor={situational_factor:.2f} (presence={situational_signal})"
            )
        if capability_factor != 1.0:
            candidate.reasoning_steps.append(
                f"capability_factor={capability_factor:.2f} ({capability_signal})"
            )
        if workload_factor != 1.0:
            candidate.reasoning_steps.append(
                f"workload_factor={workload_factor:.2f} ({workload_signal})"
            )
        candidate.reasoning_steps.append(f"FINAL score={candidate.total_score:.4f}")
        return candidate.total_score

    def _select_staleness_aware_winner(self, ranked: list[Candidate]) -> Candidate:
        """
        R6 (Task 91) — candidate diversity, STALENESS-ONLY.

        Definition of "stale": the exact same (action_type, params) identity
        — via the canonical PolicyMemory.make_situation_hash() this class
        already reuses for policy lookups (_make_situation_hash) — has been
        the FINAL winner of `candidate_staleness_streak` or more CONSECUTIVE
        evaluate() calls. This is about repeated-selection history, not
        wall-clock time: a candidate that has never won, or that alternates
        with others, is never stale no matter how much time passes.

        When the top-ranked candidate is stale, the next candidate in
        `ranked` with a DIFFERENT identity becomes the winner instead — it
        was already scored by the real 5-factor formula (goal_alignment +
        confidence + policy + urgency + timing - cost, plus bias/epistemic
        dampening) earlier in evaluate(); nothing is invented, no new
        Candidate is constructed, and action_type is never changed. If every
        candidate in `ranked` shares the stale identity (e.g. a single
        candidate, or duplicates of it), the stale candidate remains the
        winner unchanged — R6 must never fabricate a substitute just to
        satisfy diversity, and must never turn "no safe alternative" into
        "no decision" when the existing contract (decision_engine always
        returns a real winner for a non-empty candidate list) says otherwise.

        "Meaningful change" is simply: a DIFFERENT identity actually won.
        The streak counter tracks the most recent real winner, so the moment
        anything else wins even once, the previous winner's suppression
        pressure resets — the next time its identity resurfaces as the top
        scorer it is evaluated fresh, not permanently blacklisted.
        """
        top = ranked[0]
        top_hash = self._make_situation_hash(top)
        threshold = int(CONFIG.get("candidate_staleness_streak", 5))

        is_stale = (
            top_hash == self._winner_streak_hash
            and self._winner_streak_count >= threshold
        )

        winner = top
        if is_stale:
            alternative = None
            for alt in ranked[1:]:
                if self._make_situation_hash(alt) != top_hash:
                    alternative = alt
                    break
            if alternative is not None:
                logger.info(
                    "[VECTOR][decision_engine] R6 staleness: '{}' suppressed "
                    "after {} consecutive wins (threshold={}) — selecting "
                    "'{}' (score={:.3f}) instead",
                    top.action_type, self._winner_streak_count, threshold,
                    alternative.action_type, alternative.total_score,
                )
                winner = alternative
            # else: no distinct alternative exists among the real scored
            # candidates — preserve existing behavior, do NOT invent one.

        winner_hash = self._make_situation_hash(winner)
        if winner_hash == self._winner_streak_hash:
            self._winner_streak_count += 1
        else:
            self._winner_streak_hash = winner_hash
            self._winner_streak_count = 1
        return winner

    async def evaluate(self, candidates: list[Candidate]) -> Decision:
        """Score all candidates. Return winner. Log ALL including rejected."""
        if not candidates:
            logger.warning("[VECTOR][decision_engine] no candidates provided")
            noop = Candidate("noop", {}, source="fallback")
            noop_decision = Decision(winner=noop, all_candidates=[], reasoning="No candidates", evaluated=0)
            noop.decision_id = noop_decision.decision_id  # R7 — keep winner/Decision ids consistent
            return noop_decision

        # RULE 1 — inject world-state context before scoring. Was previously
        # only used to hydrate LLM calls made *after* a winner was already
        # picked; candidate scoring itself never saw it. Available on every
        # candidate (context_snapshot) for scoring/audit/training-data, same
        # as RULE 8's reasoning injection below. R22 (2026-09-10): this
        # comment used to say context_snapshot "does NOT change the score
        # formula itself" — true when written, no longer true.
        # _score_candidate()'s own _situational_factor() now reads one real
        # field (context_snapshot["presence"]) as a small, bounded,
        # GREEN-only post-score multiplier — see that method's docstring
        # for the full real BEFORE/AFTER capability this closes
        # (VECTOR_TECHNICAL_KNOWLEDGE/R21_R23_UNDERSTANDING_FOUNDATION_
        # REPORT.md). The snapshot itself is still also available for
        # audit/training-data as before.
        try:
            world_state = self._get_context_engine().get_world_state()
            for c in candidates:
                c.context_snapshot = world_state
        except Exception as _ctx_err:
            logger.warning("[VECTOR][decision_engine] RULE 1 context inject failed: {}", _ctx_err)

        # RULE 8 — inject past reasoning before scoring
        bank = self._get_reasoning_bank()
        if bank is not None:
            try:
                for c in candidates:
                    query = f"{c.action_type} {' '.join(str(v) for v in c.params.values())}"
                    past_snippet = bank.inject_past_reasoning(query, top_k=3)
                    if past_snippet:
                        c.reasoning_steps = [past_snippet]
            except Exception as _rb_err:
                logger.warning("[VECTOR][decision_engine] RULE 8 inject failed: {}", _rb_err)

        for c in candidates:
            self._score_candidate(c)

        ranked = sorted(candidates, key=lambda c: c.total_score, reverse=True)
        winner = self._select_staleness_aware_winner(ranked)
        self._decision_count += 1

        # R7 (Task 92) — one decision_id per evaluate() CALL (an event/
        # instance identifier), stamped onto every candidate scored in this
        # call — including the winner and every rejected candidate. This is
        # deliberately NOT the same value as any candidate's situation_hash
        # (PolicyMemory.make_situation_hash(action_type, params)): the same
        # (action_type, params) pair can appear across many different
        # decision_ids over time (that reusable identity is what
        # PolicyMemory learns against); decision_id instead answers "which
        # exact evaluate() call produced this candidate/outcome?". Every
        # Candidate already carries its own unique candidate_id from
        # construction (see the dataclass) — decision_id here only records
        # *which decision occurrence* that candidate_id belongs to.
        decision_id = "d:" + uuid.uuid4().hex
        for c in ranked:
            c.decision_id = decision_id

        # Neural learning loop: record (state, action) for this decision so
        # record_outcome() can train the network on the real reward later.
        # The score-based winner remains the executed action (safe); the net
        # learns to predict reward-maximizing actions over the real action space.
        trainer = self._get_neural_trainer()
        if trainer is not None:
            try:
                import numpy as np
                state = np.array(
                    [
                        len(candidates),
                        max(c.total_score for c in candidates),
                        sum(c.total_score for c in candidates) / len(candidates),
                        max(self._finite(c.confidence, 0.0) for c in candidates),
                        max(self._finite(c.urgency, 0.0) for c in candidates),
                        min(self._finite(c.estimated_cost_inr, 0.0) for c in candidates),
                        max(self._finite(c.estimated_cost_inr, 0.0) for c in candidates),
                        1.0,
                    ],
                    dtype=np.float32,
                )
                self._last_neural = {"state": state, "action": self._action_id(winner.action_type)}
            except Exception as e:
                self._last_neural = None
                logger.debug("[VECTOR][decision_engine] neural state build skipped: {}", e)

        # Log ALL candidates including rejected — RULE 8. R7 (Task 92): each
        # logged row now also carries decision_id + candidate_id, giving the
        # "candidate_generated/scored" and "candidate_selected" correlation
        # states an existing, queryable record — no schema change, since
        # EpisodicMemory.store()'s `context` is already a schemaless JSON
        # column.
        mem = self._get_memory()
        for c in ranked:
            status = "winner" if c is winner else "rejected"
            mem.store(
                event_type="decision_candidate",
                content=f"{status}: {c.action_type} score={c.total_score}",
                tags=["decision", status, c.action_type],
                context={
                    "score": c.total_score,
                    "goal_alignment": c.goal_alignment,
                    "policy": c.policy_score,
                    "confidence": c.confidence,
                    "decision_id": c.decision_id,
                    "candidate_id": c.candidate_id,
                    "candidate_status": status,
                },
                source="decision_engine",
            )

        reasoning = (
            f"Winner: {winner.action_type} (score={winner.total_score}) "
            f"over {len(ranked)-1} alternatives. "
            f"goal_alignment={winner.goal_alignment:.2f} "
            f"policy={winner.policy_score:.2f} "
            f"confidence={winner.confidence:.2f}"
        )
        logger.info(f"[VECTOR][decision_engine] {reasoning}")

        return Decision(
            winner=winner,
            all_candidates=ranked,
            reasoning=reasoning,
            evaluated=len(candidates),
            reasoning_chain=[reasoning],
            decision_id=decision_id,
        )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    engine = DecisionEngine()
    candidates = [
        Candidate("search_web", {"query": "KIIT attendance"}, goal_ids=["g_kiit_attendance"], confidence=0.8, urgency=0.6),
        Candidate("check_calendar", {}, confidence=0.9, urgency=0.3),
        Candidate("commit_code", {"repo": "VECTOR"}, goal_ids=["g_vector_phase1"], confidence=0.7, urgency=0.5),
        Candidate("set_reminder", {"text": "Karpathy 30min"}, goal_ids=["g_karpathy_30"], confidence=0.6, urgency=0.4),
    ]
    decision = asyncio.run(engine.evaluate(candidates))
    ok = (
        decision.winner is not None
        and decision.evaluated == 4
        and 0.0 <= decision.winner.total_score <= 1.0
    )
    print(
        f"✅ decision_engine OK — winner={decision.winner.action_type} "
        f"score={decision.winner.total_score}, {decision.evaluated} evaluated"
        if ok else "❌ FAILED"
    )
