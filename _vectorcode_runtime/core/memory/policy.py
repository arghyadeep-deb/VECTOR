import sys
import hashlib
import json

from loguru import logger
from core.config import CONFIG


class PolicyMemory:
    """
    RULE 7 — Policy wired BOTH directions. Either alone = not learning.
    get_score()           BEFORE every decision.
    update_from_outcome() AFTER every action.

    Online averaging: new_avg = (old_avg * n + reward) / (n + 1)
    """

    DEFAULT_SCORE = float(CONFIG.get("policy_default_score", 0.5))

    def __init__(self):
        logger.info("[VECTOR][policy] initialized")

    @staticmethod
    def make_situation_hash(context: dict | str, params: dict | None = None) -> str:
        """
        Deterministic hash of situation context for policy lookup. Two calling
        conventions, disambiguated by whether `params` is passed:

        1. make_situation_hash(context: dict | str) -- the ORIGINAL, unchanged
           convention already used by core/memory/router.py (:180, :316).
           Canonicalizes `context` directly via json.dumps(sort_keys=True).
           Returns the same 12-char hex hash as before -- zero behavior
           change for existing callers.

        2. make_situation_hash(action_type: str, params: dict) -- Task 89 (D2)
           addition. This is the single canonical identity function for the
           (action_type, params) pairs decision_engine.py's reader and
           autonomous_loop.py's writers key on. Before this fix, the reader
           used `f"{action_type}:{sorted(params.items())}"` while several
           writers independently used `f"{action_type}:{json.dumps(params,
           sort_keys=True, default=str)}"` -- two different serializations of
           the same logical situation, hashing differently and silently
           preventing real-outcome rewards from ever being read back.
           Canonicalizes the full (action_type, params) pair as one JSON
           object (params are NOT filtered/allowlisted -- every key, including
           display-only ones like "title", is still part of the identity,
           exactly matching today's semantics; only the SERIALIZATION is
           unified). Prefixed "v2:" so these hashes can never collide with
           either the old sorted()-repr rows or the old mismatched
           json.dumps rows already sitting in policy_memory -- no migration,
           no backfill, old rows are simply never looked up by new code.
        """
        if params is not None:
            key = json.dumps(
                {"action_type": context, "params": params}, sort_keys=True, default=str
            )
            return "v2:" + hashlib.sha256(key.encode()).hexdigest()[:12]
        if isinstance(context, dict):
            key = json.dumps(context, sort_keys=True, default=str)
        else:
            key = str(context)
        return hashlib.sha256(key.encode()).hexdigest()[:12]

    def get_score(self, action_type: str, situation_hash: str) -> float:
        """
        RULE 7 — Call BEFORE every decision.
        Returns avg reward [0.0-1.0] for this (action, situation) pair.
        Returns DEFAULT_SCORE if no data yet.
        """
        try:
            # get_temp_cursor() (core.memory.episodic) resolves the shared
            # singleton connection fresh on every call and holds _write_lock
            # for the duration — a cached EpisodicMemory().conn (the old
            # self._get_mem().conn pattern) goes stale if the singleton is
            # ever closed/reopened (KNOWN_ISSUES #21-class defect), and raw
            # conn.execute() outside _write_lock races other threads on the
            # one shared connection.
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cursor:
                row = cursor.execute(
                    "SELECT avg_reward, sample_count FROM policy_memory "
                    "WHERE action_type=? AND situation_hash=?",
                    (action_type, situation_hash),
                ).fetchone()
            if row:
                avg_reward, count = row
                # Task 89 (D3): a row can now exist that has ONLY ever received
                # record_suppression() calls (veto_count > 0, avg_reward still
                # NULL because no real outcome has ever landed on this exact
                # canonical identity). Treat that the same as "no data yet" --
                # returning DEFAULT_SCORE, not crashing float(None) into the
                # broad except below (which would work but log a spurious
                # ERROR on every such lookup).
                if avg_reward is None:
                    return self.DEFAULT_SCORE
                logger.debug(
                    f"[VECTOR][policy] {action_type}/{situation_hash[:6]} "
                    f"→ {avg_reward:.3f} ({count} samples)"
                )
                return float(avg_reward)
        except Exception as e:
            logger.error(f"[VECTOR][policy] get_score failed: {e}")
        return self.DEFAULT_SCORE

    def update_from_outcome(
        self, action_type: str, situation_hash: str, reward: float
    ) -> None:
        """
        RULE 7 — Call AFTER every action with the real outcome reward.
        reward: 0.0 = complete failure → 1.0 = excellent.
        """
        reward = max(0.0, min(1.0, reward))
        try:
            # The whole read-modify-write online average must happen inside a
            # single _write_lock hold, or two threads updating the same
            # (action_type, situation_hash) can both read the same (old_avg, n)
            # and the second commit silently clobbers the first's update —
            # a lost-update race that degrades the RULE 7 learning signal with
            # no error and no log line. get_temp_cursor() holds _write_lock for
            # its whole `with` block, so this is now atomic across threads
            # (still process-local only — see core.memory.episodic._write_lock's
            # own docs; it is not cross-process protection).
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cursor:
                row = cursor.execute(
                    "SELECT avg_reward, sample_count FROM policy_memory "
                    "WHERE action_type=? AND situation_hash=?",
                    (action_type, situation_hash),
                ).fetchone()

                if row:
                    old_avg, n = row
                    # Task 89 (D3): a row can exist here with avg_reward=NULL,
                    # sample_count=0 -- created by record_suppression() for a
                    # veto that landed before any real outcome ever did. The
                    # cumulative-mean arithmetic itself is UNCHANGED (still a
                    # plain online average); this only special-cases the one
                    # new starting state my own schema addition introduces, so
                    # a real outcome landing after a suppression-only row
                    # doesn't crash on `None * 0`.
                    if old_avg is None:
                        old_avg, n = 0.0, 0
                    new_avg = (old_avg * n + reward) / (n + 1)
                    cursor.execute(
                        "UPDATE policy_memory SET avg_reward=?, sample_count=?, "
                        "last_updated=datetime('now') "
                        "WHERE action_type=? AND situation_hash=?",
                        (new_avg, n + 1, action_type, situation_hash),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO policy_memory "
                        "(action_type, situation_hash, avg_reward, sample_count, last_updated) "
                        "VALUES (?, ?, ?, 1, datetime('now'))",
                        (action_type, situation_hash, reward),
                    )
            logger.debug(f"[VECTOR][policy] updated {action_type} reward={reward:.3f}")
        except Exception as e:
            logger.error(f"[VECTOR][policy] update_from_outcome failed: {e}")

    def record_suppression(self, action_type: str, situation_hash: str) -> None:
        """
        Task 89 (D3) — suppression/veto channel, SEPARATE from update_from_outcome().

        Call this (never update_from_outcome()) when a counterfactual veto
        blocks a proposal before it ever executes. Increments veto_count for
        this (action_type, situation_hash) WITHOUT touching avg_reward or
        sample_count -- a veto is a control-flow event ("this proposal was
        suppressed"), not an outcome measurement, and must never be blended
        into the same cumulative mean real 5-factor/VectorCode outcome
        rewards accumulate into (that conflation was the exact bug this
        method replaces: the veto path used to call
        update_from_outcome(..., reward=0.05), a hardcoded literal with no
        relationship to any actual result).

        CounterfactualMemory's own `rejections` table already records every
        veto in full detail (proposal text, reason, timestamp) -- this method
        is NOT a duplicate of that. It exists only so decision_engine's
        get_score() / future tooling can see "how often has this exact
        canonical situation been suppressed" as a value distinct from
        avg_reward, never mixed into it.

        A brand-new row created here has avg_reward=NULL, sample_count=0 --
        get_score() treats that identically to "no data yet" (returns
        DEFAULT_SCORE), and a subsequent real update_from_outcome() call on
        the same key starts its cumulative mean from (0.0, 0), not from the
        veto count.
        """
        try:
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cursor:
                row = cursor.execute(
                    "SELECT veto_count FROM policy_memory WHERE action_type=? AND situation_hash=?",
                    (action_type, situation_hash),
                ).fetchone()
                if row:
                    cursor.execute(
                        "UPDATE policy_memory SET veto_count=COALESCE(veto_count, 0) + 1, "
                        "last_updated=datetime('now') "
                        "WHERE action_type=? AND situation_hash=?",
                        (action_type, situation_hash),
                    )
                else:
                    cursor.execute(
                        "INSERT INTO policy_memory "
                        "(action_type, situation_hash, avg_reward, sample_count, veto_count, last_updated) "
                        "VALUES (?, ?, NULL, 0, 1, datetime('now'))",
                        (action_type, situation_hash),
                    )
            logger.debug(f"[VECTOR][policy] suppression recorded for {action_type}/{situation_hash[:6]}")
        except Exception as e:
            logger.error(f"[VECTOR][policy] record_suppression failed: {e}")

    def get_veto_count(self, action_type: str, situation_hash: str) -> int:
        """
        E4 (update-rule audit) — read side of record_suppression()'s veto_count
        column. This column has existed since Task 89 (D3) and this method's
        own docstring already stated the intent ("so decision_engine's
        get_score() / future tooling can see... how often has this exact
        canonical situation been suppressed") but nothing ever actually read
        it until now — confirmed by repo-wide audit to be write-only (INERT)
        before this method existed. Returns 0 for no data, exactly like
        get_score() returns DEFAULT_SCORE for no data — never raises.
        """
        try:
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cursor:
                row = cursor.execute(
                    "SELECT veto_count FROM policy_memory WHERE action_type=? AND situation_hash=?",
                    (action_type, situation_hash),
                ).fetchone()
            if row and row[0] is not None:
                return int(row[0])
        except Exception as e:
            logger.error(f"[VECTOR][policy] get_veto_count failed: {e}")
        return 0

    def get_top_actions(self, limit: int = 10) -> list[dict]:
        """Top-performing action types with ≥3 samples, by avg reward."""
        try:
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cursor:
                rows = cursor.execute(
                    "SELECT action_type, avg_reward, sample_count FROM policy_memory "
                    "WHERE sample_count >= 3 ORDER BY avg_reward DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [{"action": r[0], "avg_reward": round(r[1], 3), "samples": r[2]} for r in rows]
        except Exception as e:
            logger.error(f"[VECTOR][policy] get_top_actions failed: {e}")
            return []

    def get_stats(self) -> dict:
        try:
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cursor:
                total = cursor.execute("SELECT COUNT(*) FROM policy_memory").fetchone()[0]
                avg = cursor.execute("SELECT AVG(avg_reward) FROM policy_memory").fetchone()[0] or 0.0
            return {"total_entries": total, "overall_avg_reward": round(float(avg), 3)}
        except Exception as e:
            logger.error(f"[VECTOR][policy] get_stats failed: {e}")
            return {"total_entries": 0, "overall_avg_reward": 0.0}


if __name__ == "__main__":
    import uuid
    sys.stdout.reconfigure(encoding="utf-8")

    pm = PolicyMemory()
    # Use unique key per run so fresh DB state is guaranteed
    run_id = uuid.uuid4().hex[:8]
    h = pm.make_situation_hash({"task": "smoke_test", "run": run_id})

    score_before = pm.get_score("smoke_web_test", h)  # fresh key → must be default

    pm.update_from_outcome("smoke_web_test", h, 0.9)
    pm.update_from_outcome("smoke_web_test", h, 0.7)
    pm.update_from_outcome("smoke_web_test", h, 0.8)

    score_after = pm.get_score("smoke_web_test", h)
    stats = pm.get_stats()

    # Task 89 (D2/D3) — new (action_type, params) canonical convention +
    # suppression channel, exercised with a fresh, collision-free key.
    action_type2 = f"smoke_veto_test_{run_id}"
    params2 = {"goal_id": f"g_{run_id}", "title": "irrelevant display text"}
    h2 = pm.make_situation_hash(action_type2, params2)
    h2_again = pm.make_situation_hash(action_type2, dict(params2))  # different dict identity, same content

    veto_score_before = pm.get_score(action_type2, h2)
    pm.record_suppression(action_type2, h2)
    veto_score_after_suppression = pm.get_score(action_type2, h2)
    pm.update_from_outcome(action_type2, h2, 0.9)  # real outcome after a suppression-only row
    veto_score_after_outcome = pm.get_score(action_type2, h2)

    ok = (
        score_before == PolicyMemory.DEFAULT_SCORE
        and score_after > score_before
        and stats["total_entries"] >= 1
        and h2.startswith("v2:")
        and h2 == h2_again  # same (action_type, params) content → identical canonical hash
        and veto_score_before == PolicyMemory.DEFAULT_SCORE
        # suppression must NOT move avg_reward off default
        and veto_score_after_suppression == PolicyMemory.DEFAULT_SCORE
        # a real outcome after a suppression-only row must still land cleanly
        and veto_score_after_outcome == 0.9
    )
    print(
        f"✅ policy OK — default={score_before}, after 3 updates={score_after:.3f}, "
        f"entries={stats['total_entries']}, v2 hash={h2}, "
        f"suppression-then-outcome={veto_score_after_outcome:.3f}"
        if ok else "❌ FAILED"
    )
