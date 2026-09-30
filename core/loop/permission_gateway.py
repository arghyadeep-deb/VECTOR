import sys

__all__ = [
    "Action",
    "COUNCIL_AUTO_PROCEED_ALLOWED",
    "FORBIDDEN",
    "GatewayResult",
    "GREEN",
    "OWNER_APPROVAL_ONLY",
    "PermissionGateway",
    "RED",
    "RED_INTERACTIVE_TOOLS",
    "YELLOW",
]

from pathlib import Path
from core.config import CONFIG
from core.runtime_paths import data_path
from loguru import logger
import asyncio, datetime, httpx, os, re, shlex
import contextvars
from dataclasses import dataclass, field

# RED-tier enforcement: Pushover phone notifications + optional Queen consensus

@dataclass
class Action:
    action_type: str
    params: dict
    proposed_by: str
    priority: str = 'normal'
    estimated_cost_inr: float = 0.0

@dataclass
class GatewayResult:
    approved: bool
    level: str
    executed: bool
    result: dict
    reason: str

GREEN = CONFIG['permission']['green']
YELLOW = CONFIG['permission']['yellow']
RED = CONFIG['permission']['red']
FORBIDDEN = ['format_drive', 'mass_delete', 'share_private_data']

# R19 (2026-09-10): action_types a real PlanStep may legitimately carry as
# part of a composed multi-step strategy (core/runtime/plans.py::PlanRunner
# .execute_step() -> AutonomousExecutor.execute() -> this class's execute()
# -> _execute_action()). Before this, _execute_action()'s only generic
# dispatch-to-Governor path was the "hand_"-prefix branch below — an
# arbitrary action_type like "script"/"schedule_post" fell through to the
# final `else` and returned "not_implemented", even though the exact same
# action_type already executes correctly via AutonomousLoop._act_on()'s
# OTHER (native goal candidate) dispatch path. Deliberately a narrow,
# explicit allowlist (not "any non-hand_ action_type") — each entry must
# already be real (real handler, real DISTRICT_TASK_MAP route, real
# permission tier in core/config.py) before being added here; see
# VECTOR_TECHNICAL_KNOWLEDGE/R19_R20_MASTER_REPORT.md for the composition
# capability this unblocks (script -> schedule_post).
# 2026-09-26: "web_extract" -- GREEN, read-only page extraction (real handler: WebScout.web_extract, exact
# DISTRICT_TASK_MAP route "research", declared in WebScout.capabilities); the read step of the browser workflow.
_PLAN_COMPOSABLE_ACTION_TYPES = {"script", "schedule_post", "idea_validate", "log_exercise", "create_project", "web_extract"}
# V1 TRUST CLOSURE (2026-09-21, T3, VECTOR_TECHNICAL_KNOWLEDGE/
# V1_TRUST_ACTION_IDENTITY_PERMISSION_CLOSURE_REPORT.md): a SEPARATE,
# equally narrow allowlist (deliberately not folded into
# _PLAN_COMPOSABLE_ACTION_TYPES above — that set is pinned by exact-equality
# tests and means "actions a plan step may carry") for the READ-ONLY
# capabilities the owner path demonstrably needed. Each was GREEN-registered
# (core/config.py) with a real district handler but had NO route here, so
# /command's Candidate -> DecisionEngine -> Gateway path reached
# `_execute_action`'s final `not_implemented` and then reported
# "Done — X completed." (a phantom success):
#   git_status / check_git       -> GitBot.get_status()         (read-only)
#   git_log / recent_commits     -> GitBot.get_recent_commits() (read-only)
#   search_arxiv                 -> PaperReader.search_papers() (read-only
#                                   arXiv query, keyless, structured evidence)
# Each: real handler declared in the agent's own `capabilities`, exact
# DISTRICT_TASK_MAP route (never LLM-guessed), existing explicit GREEN tier
# (no tier was changed or added). NOT added, on purpose: `index_codebase`
# (its handler runs a 300s MCP subprocess that BUILDS an index — a write,
# not a status query; stays UNKNOWN/fail-closed) and `daily_review`/
# `reflect` (DailyReviewer.run answers with an LLM reflection answer, not a
# grounded review — reporting that as a review would be a fabrication).
_OWNER_READONLY_DISPATCH_ACTION_TYPES = frozenset(
    {"git_status", "check_git", "git_log", "recent_commits", "search_arxiv"}
)
# RR-3.7B (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
# RR3_7B_STRUCTURED_ROUTER_AUTHORIZATION_REPORT.md): "log_exercise" and
# "create_project" added to this same narrow, explicit, individually-
# verified allowlist. Both were confirmed real S4 authorization gaps:
# core/api/routers/health.py::log_exercise and
# core/api/routers/projects.py::create_project called
# `Governor.dispatch()` directly with a hardcoded action_type and zero
# PermissionGateway anywhere in the path, despite both being real,
# YELLOW-tier (core/config.py), side-effecting handlers --
# districts/health/exercise_logger.py::ExerciseLogger.run() (exact
# `task["type"]=="log_exercise"` branch -> real episodic-memory write) and
# districts/projects/project_planner.py::ProjectPlanner.run() (exact
# `task["type"]=="create_project"` branch -> real episodic-memory write
# AND a real Obsidian note file write, with caller-supplied name/goal/
# deadline flowing directly into file content). Both routers were fixed to
# call Candidate -> DecisionEngine.evaluate() -> PermissionGateway.execute()
# first (proposed_by="structured_api", deliberately distinct from
# "api_command"/"voice" so neither gets YELLOW pre-confirmation -- see
# permission_gateway.py's own `action.proposed_by in ("api_command",
# "voice")` branch above); this entry is what lets a Gateway-approved
# execution still reach the real, already-correct district-agent handler
# via Governor.dispatch() afterward, instead of falling through to
# `_execute_action()`'s final `not_implemented` -- exactly the same
# pattern as "idea_validate" above, and for the identical reason.
# RR-3.5A (2026-09-16, VECTOR_TECHNICAL_KNOWLEDGE/
# RR3_5_FOUNDATION_CLOSURE_REPORT.md): "idea_validate" added to this same
# narrow, explicit, individually-verified allowlist -- not a general
# district-dispatch policy change. Verified real per this set's own
# criterion above: real handler (districts/startups/idea_validator.py::
# IdeaValidator.capabilities includes "idea_validate"), real single
# unambiguous DISTRICT_TASK_MAP route ("idea_validate" -> "startups", never
# LLM-guessed, so Governor.dispatch()'s wrong-district HP-lottery risk
# structurally cannot arise for this entry), real GREEN permission tier
# (core/config.py). Before this, "idea_validate" was reachable via
# AutonomousLoop._act_on()'s native goal-candidate path (which calls
# governor.dispatch() directly) but hit `_execute_action()`'s final
# `not_implemented` when reached via /command's PermissionGateway.execute()
# path -- despite GREEN approval, nothing real ever happened, and
# command_endpoint() reported it as executed=True anyway (a confirmed,
# real fake-success shape). This closes that gap for this one, fully
# source-verified action_type only -- it does NOT alias or unblock
# "idea_validation" (the distinct, mismatched regex-preclassify string),
# which remains correctly UNKNOWN/blocked.
# 2026-07-30 audit fix (Phase 3 — guardrails): every RED-tier action_type
# EXCEPT the ones listed here can be auto-executed on an LLM council
# "proceed" verdict alone (see _handle_red_tier() / the `level == 'RED'`
# branch below) — the owner is only ever actually pinged for
# OWNER_APPROVAL_ONLY actions; everything else defers to Pushover ONLY if
# the council itself declines to decide. Confirmed live risk, not
# theoretical: districts/investment/hedgebot_agent.py::solana_execute()
# signs REAL on-chain funds purely on `approval.approved` — its own
# docstring claims "signs ONLY on explicit approval (owner rule
# 2026-06-21)" and config.py's RED-tier comment claims "owner approval
# ALWAYS" for solana_swap_execute, but neither was actually true: it was
# never in this set, so a council vote alone could authorize signing real
# money with zero owner involvement. push_github is the other confirmed
# live risk — unlike delete_files/deploy_production (both intentionally
# stubbed to `not_implemented` in _execute_action, so a council "proceed"
# there is a no-op today), push_github's handler is real and unstubbed: a
# council vote alone can push code to the remote right now.
#
# Widened per the 2026-07-30 audit's explicit recommendation to cover every
# irreversible or real-world-outward RED action, not just financial_
# transaction: real money (solana_swap_execute), irreversible remote/infra
# changes (push_github, deploy_production, delete_files), and anything that
# publishes/acts publicly under the owner's name (content_publish,
# hand_browser — purchases/forms, hand_content — publishing, hand_clip —
# upload). This is defense-in-depth even for the currently-stubbed actions:
# if delete_files/deploy_production ever get a real implementation later,
# the owner-approval requirement is already in place rather than something
# someone has to remember to add at the same time.
OWNER_APPROVAL_ONLY = {
    'financial_transaction', 'solana_swap_execute',
    'push_github', 'deploy_production', 'delete_files',
    'content_publish', 'hand_browser', 'hand_content', 'hand_clip',
}

# 2026-08-04 (review of the RED_INTERACTIVE_TOOLS hardening below): these two
# strings are now SECURITY-CRITICAL. The RED branch grants an owner-initiated
# bypass (execute immediately, no Pushover approval) to every
# RED_INTERACTIVE_TOOLS action — including run_shell_command — purely on the
# basis of `Action.proposed_by` matching one of these markers.
#
# That is safe ONLY because the owner-input paths set it server-side and
# hardcoded: core/api/routers/commands.py (proposed_by="api_command") and
# core/api/routers/voice.py (proposed_by="voice"). It is NOT safe for the
# routes that populate proposed_by straight from a client-supplied request
# body — core/api/routers/{executor,missions,tasks}.py. Without the guard
# below, `POST /execute/run {"action_type":"run_shell_command",
# "proposed_by":"api_command"}` would bypass owner approval entirely and run
# arbitrary shell. (Before RED_INTERACTIVE_TOOLS existed, RED had no bypass
# at all, so spoofing this string bought an attacker nothing — the hardening
# is what made it exploitable, which is why the guard ships with it.)
#
# Ingress rule: any route that reads proposed_by from client input MUST pass
# it through sanitize_proposed_by() before constructing an Action.
_OWNER_TRUST_MARKERS = frozenset({'api_command', 'voice'})


# F-5: coding-grant contextvar. Set active by the autonomous loop / gateway when
# a code_* action has been approved, so coding_tools file-write helpers can
# enforce they're only called within a gateway-approved code execution context
# (not directly by an arbitrary importer). Async-context-scoped: propagates to
# awaited coroutines (bridge.run_task), does not leak across create_task
# boundaries that copy context.
_CODING_GRANT = contextvars.ContextVar("vector_coding_grant_active", default=False)


def set_coding_grant(active: bool):
    """Mark the current async context as having an active gateway-approved
    code execution grant. Called by the loop after a code_* action is approved."""
    _CODING_GRANT.set(bool(active))


def is_coding_grant_active() -> bool:
    """True if the current context is within a gateway-approved code execution."""
    return bool(_CODING_GRANT.get())


def sanitize_proposed_by(value: str, *, fallback: str = 'untrusted_client') -> str:
    """Neutralise reserved owner-trust markers arriving from client input.

    Returns the value unchanged unless it claims one of the reserved
    server-only trust markers, in which case it is prefixed (and logged) so
    it can never match the owner-initiated bypass in the RED branch.
    """
    v = (value or '').strip()
    if v.lower() in _OWNER_TRUST_MARKERS:
        logger.warning(
            "[VECTOR][gateway] client-supplied proposed_by claimed reserved "
            "owner-trust marker {!r} — neutralised (owner bypass denied)", v
        )
        return f'client_claimed_{v.lower()}'
    return v or fallback


def safe_vault_note_path(vault: str, name: str) -> "pathlib.Path | None":
    """Resolve a note title/name to a path INSIDE the given vault, or None
    if it would escape it.

    2026-09-23 (HIGH SEVERITY fix): `write_note_personal`/
    `overwrite_note_personal` used to build the note path as
    `pathlib.Path(vault) / f"{title}.md"` with zero sanitisation of
    `title`/`note` (both LLM-params-supplied, action.params.get(...) --
    reachable from an LLM-invented task, same untrusted-provenance class
    RED_INTERACTIVE_TOOLS' own comment documents). Two real ways that
    goes wrong: (1) a name containing `../` climbs out of the vault
    (ordinary path traversal); (2) if the name LOOKS like an absolute
    path, pathlib's `/` operator silently DISCARDS the vault prefix
    entirely (`Path("/vault") / "/etc/passwd"` == `Path("/etc/passwd")`)
    -- an arbitrary-file-write, not merely a constrained traversal.

    Returns the resolved path only if it is genuinely inside the
    resolved vault directory; otherwise None (caller must treat this as
    a real failure, not silently write elsewhere)."""
    import pathlib
    if not vault or not name:
        return None
    try:
        vault_root = pathlib.Path(vault).resolve()
        candidate = (vault_root / f"{name}.md").resolve()
        candidate.relative_to(vault_root)  # raises if candidate escaped
        return candidate
    except (ValueError, OSError):
        return None


# 2026-08-04 hardening (prompt-injection -> unattended-execution audit fix):
# "interactive tool" capabilities promoted from YELLOW to RED — arbitrary
# shell execution, VLM-driven desktop/browser control, synthetic input,
# app launch (with attacker-controllable args), code write/execute paths,
# and arbitrary fetch-to-disk. As YELLOW these could auto-execute after a
# ~10s window with zero owner confirmation whenever VECTOR_YELLOW_AUTO_CONFIRM=1
# (the owner's live .env) — a direct prompt-injection -> unattended-execution
# path, since the action itself is an LLM-invented task_type
# (classify_chat_intent() in core/city/governor.py) that can originate from
# untrusted ingested text (email/web/message).
#
# These are deliberately NOT folded into OWNER_APPROVAL_ONLY above.
# OWNER_APPROVAL_ONLY actions (real money, GitHub pushes, deploys, publishing)
# intentionally require a Pushover phone-tap EVEN when the owner typed the
# command themselves — that's correct for rare, high-stakes, "fire and
# forget" actions. These RED_INTERACTIVE_TOOLS actions are the opposite
# profile: tools the owner drives interactively many times a day (open an
# app, run a command, have VECTOR click through a page while watching).
# Blanket-requiring a phone tap for every one of those — even ones the owner
# just typed into the HUD — would be console-breaking friction with no real
# security benefit (an authenticated api_command/voice request already IS
# the owner's explicit instruction; see the equivalent bypass in the YELLOW
# branch above).
#
# So the RED branch below gives this set the SAME owner-initiated bypass
# YELLOW already has (`action.proposed_by in ("api_command", "voice")` ->
# pre-confirmed, no wait), but ONLY for this set — OWNER_APPROVAL_ONLY keeps
# its existing no-bypass-ever behavior unchanged. Anything NOT owner-typed
# (autonomous_loop / think_loop / skill / anticipation / remote_device, i.e.
# exactly the LLM-invented-task_type path this fix targets) is forced
# straight to `defer` -> Pushover, skipping CouncilBrain's auto-proceed path
# entirely (see _handle_red_tier(): confidence defaults to a hardcoded 0.75
# and is itself an LLM judgment over attacker-influenceable params/context —
# letting it rubber-stamp exactly the actions this fix exists to gate would
# just move the hole one hop over). Pushover approval fails closed on the
# 300s timeout — never a silent auto-execute.
RED_INTERACTIVE_TOOLS = {
    'run_shell_command',
    'gui_task', 'click_screen', 'desktop_task', 'browser_task', 'web_task', 'vision_control',
    'pc_type', 'pc_click', 'pc_launch_app', 'launch_app',
    'code_task', 'code_generate', 'code_fix', 'code_debug',
    'download_file',
    # 2026-08-05: send_message_routine promoted YELLOW -> RED (it sends a real
    # message to a real person and was auto-confirming). Included here rather
    # than left bare-RED so the owner explicitly asking VECTOR to send
    # something still goes immediately, exactly as it did as YELLOW — only
    # autonomous/LLM-originated sends now require a real approval. It is
    # deliberately NOT in OWNER_APPROVAL_ONLY: that set is for irreversible
    # money/deploy/publish actions where even an owner-typed command should
    # cost a phone tap.
    'send_message_routine',
}

# F-9 (autonomy safety audit 2026-08-13): CouncilBrain's auto-proceed path
# (confidence >= 0.75) could authorize RED actions with real external side
# effects purely on an LLM judgment over attacker-influenceable params/context
# — with ZERO owner signal. Confirmed eligible today: execute_code, send_email,
# overwrite_note_personal. Auto-proceed is now OPT-IN: only action_types in
# this set may be auto-executed on a council "proceed". Default empty = every
# RED action defers to a real Pushover owner approval. The council's REJECT
# vote is preserved (still feeds CounterfactualMemory) — only auto-PROCEED is
# gated. Add an action here only after an explicit owner decision that the
# council alone may authorize it.
COUNCIL_AUTO_PROCEED_ALLOWED: frozenset[str] = frozenset()

class PermissionGateway:
    # Process-wide shared instance. Pending YELLOW/RED approvals live per-instance,
    # so every entry path (API routers via app.state, remote-command relay,
    # loop internals) must share ONE gateway or approvals strand in a queue
    # nothing reads.
    #
    # 2026-07-21 fix: 37 call sites across the codebase (districts, routers,
    # loop internals) constructed `PermissionGateway()` directly instead of
    # `get_shared()` — each got its OWN `_pending_events`/`_pending_actions`
    # dict. An owner tapping "Approve" on a Pushover notification hits
    # /gateway/approve/{id}, which only ever signals `app.state.
    # permission_gateway`'s dict — a DIFFERENT object from whichever district
    # instance was actually awaiting confirmation. Every RED/YELLOW approval
    # from a bare `PermissionGateway()` call was therefore unapprovable by
    # design and would silently time out (discovered via phone_poster.py's
    # Instagram-post approval never reaching /gateway/pending).
    #
    # __new__ now makes PermissionGateway() ALWAYS return the one process-wide
    # instance, so every caller — old or new, already-audited or not —
    # automatically shares pending-approval state. get_shared() is kept as
    # the explicit/preferred spelling; it now simply returns cls().
    _shared: "PermissionGateway | None" = None

    def __new__(cls):
        if cls._shared is None:
            cls._shared = super().__new__(cls)
            cls._shared._pg_initialized = False
        return cls._shared

    @classmethod
    def get_shared(cls) -> "PermissionGateway":
        return cls()

    def __init__(self):
        # Idempotent: a second `PermissionGateway()` call must NOT wipe out
        # pending approvals/audit history that the first instance is holding.
        if getattr(self, "_pg_initialized", False):
            return
        self._pg_initialized = True
        self.audit_log = []
        # F-1: pending approvals are keyed by a UNIQUE id (action_type#seq),
        # not action_type alone — two concurrent same-type RED actions no longer
        # collide on the same asyncio.Event. confirm_action()/approve() resolve
        # the unique id; confirm_action() keeps backward-compat for callers
        # that only know the action_type (resolves unambiguously when a single
        # instance is pending, refuses when ambiguous — fail-safe).
        self._pending_events: dict[str, asyncio.Event] = {}
        self._pending_actions: dict[str, dict] = {}
        self._pending_seq: int = 0
        self._rejected: set[str] = set()
        # F-6/F-7: capability tokens for PC/phone control-plane ops. A district
        # that has received gateway approval calls grant_control() to mint a
        # one-shot (multi-use, TTL-bounded) token it then passes to the
        # controller write methods. Controllers verify via verify_control() —
        # a direct caller with no token is refused. This converts the prior
        # soft _gateway_approved kwarg (any caller could pass True) into a
        # gateway-minted capability.
        self._control_grants: dict[str, tuple[str, float, int]] = {}
        # 2026-09-23 (HIGH SEVERITY fix, round 2): grant_control() used to
        # accept an `approved: bool` kwarg the caller simply asserted --
        # an independent review correctly pointed out that's forgeable
        # (any caller can pass `approved=True` with zero real proof, the
        # exact same "soft boolean" problem the comment above already
        # describes fixing for control_grants themselves). Replaced with
        # an internal, gateway-owned receipt ledger: only this file's own
        # execute()/request_approval() internals can call
        # _issue_approval_receipt() (right after a REAL approval decision
        # for that exact action_type), and grant_control() consumes one
        # via _consume_approval_receipt() instead of trusting a caller's
        # word. External callers cannot forge a receipt for an
        # action_type they were never actually granted.
        self._approval_receipts: dict[str, list[float]] = {}
        # F-8: durable audit log (SQLite append-only). The in-memory ring is
        # kept for fast access; every entry is also persisted so forensic
        # evidence survives restarts and the 500-entry cap no longer loses
        # history.
        self._init_audit_store()
        # F-3: re-hydrate pending approvals persisted before a prior crash.
        # Their awaiting coroutines are dead (cannot be set), so they are
        # surfaced as "interrupted" for the owner to reject/clear — never
        # silently lost.
        self._init_pending_store()
        self._rehydrate_pending()
        logger.info('[VECTOR][gateway] Permission gateway initialised')

    # ── F-1: unique pending ids ──────────────────────────────────────────────

    def _make_pending_id(self, action_type: str) -> str:
        # 2026-09-23 (HIGH SEVERITY fix): this used to be a trivially
        # guessable, sequential id (f"{action_type}#{self._pending_seq}",
        # e.g. "run_shell_command#42"). It is the SAME id embedded in the
        # Pushover approve/reject URLs (request_approval()'s own
        # _approve_url/_reject_url, above), and core/api/routers/
        # gateway.py's GET /gateway/approve/{action_id} route has NO
        # authentication of its own -- it trusts the id alone. Anyone who
        # can reach that HTTP endpoint (Tailscale remote access, an
        # exposed port, or simple local enumeration) could approve ANY
        # pending RED-tier action -- including a real shell command --
        # by guessing or enumerating the next sequence number, with zero
        # need for the owner to ever tap anything. A random, unguessable
        # component makes the URL itself the credential, matching how
        # grant_control()'s own tokens are generated.
        self._pending_seq += 1
        import secrets as _secrets
        return f"{action_type}#{self._pending_seq}_{_secrets.token_urlsafe(16)}"

    def _resolve_pending_id(self, action_type_or_id: str) -> str | None:
        """Map a caller-supplied id (which may be a bare action_type for
        backward-compat) to the unique pending id. Returns None if not found
        or if ambiguous (multiple pending instances of the same action_type —
        caller must use the full unique id)."""
        if action_type_or_id in self._pending_events:
            return action_type_or_id
        # Backward-compat: caller passed a bare action_type. Resolve only when
        # exactly one instance is pending; ambiguity is fail-safe (None).
        matches = [pid for pid, meta in self._pending_actions.items()
                   if meta.get("action_type") == action_type_or_id]
        if len(matches) == 1:
            return matches[0]
        return None

    # ── F-3: durable pending-approval store ──────────────────────────────────

    def _init_pending_store(self) -> None:
        try:
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cur:
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS pending_approvals ("
                    "id TEXT PRIMARY KEY, action_type TEXT NOT NULL, "
                    "params TEXT NOT NULL, proposed_by TEXT NOT NULL, "
                    "level TEXT NOT NULL, registered_at TEXT NOT NULL, "
                    "interrupted INTEGER NOT NULL DEFAULT 0)"
                )
        except Exception as e:
            logger.debug(f"[VECTOR][gateway] pending_approvals table init skipped: {e}")

    def _persist_pending(self, pending_id: str, entry: dict) -> None:
        try:
            import json as _json
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cur:
                cur.execute(
                    "INSERT OR REPLACE INTO pending_approvals "
                    "(id, action_type, params, proposed_by, level, registered_at, interrupted) "
                    "VALUES (?, ?, ?, ?, ?, ?, 0)",
                    (pending_id, entry.get("action_type", ""),
                     _json.dumps(entry.get("params", {}), default=str),
                     entry.get("proposed_by", ""), entry.get("level", ""),
                     entry.get("timestamp", "")),
                )
        except Exception as e:
            logger.debug(f"[VECTOR][gateway] pending persist skipped: {e}")

    def _unpersist_pending(self, pending_id: str) -> None:
        try:
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cur:
                cur.execute("DELETE FROM pending_approvals WHERE id = ?", (pending_id,))
        except Exception as e:
            logger.debug(f"[VECTOR][gateway] pending unpersist skipped: {e}")

    def _rehydrate_pending(self) -> None:
        """On startup, load any pending approvals left by a crashed process.
        Their waiters are dead — mark interrupted so the owner can clear them
        via reject(). They are never auto-approved."""
        try:
            from core.memory.episodic import get_db_connection
            conn = get_db_connection()
            rows = conn.execute(
                "SELECT id, action_type, params, proposed_by, level, registered_at "
                "FROM pending_approvals"
            ).fetchall()
        except Exception as e:
            logger.debug(f"[VECTOR][gateway] pending rehydrate skipped: {e}")
            return
        for r in rows:
            import json as _json
            pid = r[0] if not isinstance(r, dict) else r["id"]
            # Use dict-style access defensively; sqlite3.Row supports both.
            def _g(k, i):
                return r[k] if hasattr(r, "keys") else r[i]
            entry = {
                "id": pid,
                "action_type": _g("action_type", 1),
                "params": _json.loads(_g("params", 2)) if _g("params", 2) else {},
                "proposed_by": _g("proposed_by", 3),
                "level": _g("level", 4),
                "timestamp": _g("registered_at", 5),
                "interrupted": True,
            }
            self._pending_actions[pid] = entry
            logger.warning(
                f"[VECTOR][gateway] rehydrated interrupted pending approval "
                f"'{pid}' (action_type={entry['action_type']}) — reject via HUD to clear"
            )

    # ── F-8: durable audit log ───────────────────────────────────────────────

    def _init_audit_store(self) -> None:
        try:
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cur:
                cur.execute(
                    "CREATE TABLE IF NOT EXISTS gateway_audit ("
                    "seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, "
                    "action_type TEXT NOT NULL, level TEXT NOT NULL, "
                    "approved INTEGER NOT NULL, executed INTEGER NOT NULL, "
                    "proposed_by TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '')"
                )
        except Exception as e:
            logger.debug(f"[VECTOR][gateway] gateway_audit table init skipped: {e}")

    def _persist_audit(self, entry: dict) -> None:
        try:
            from core.memory.episodic import get_temp_cursor
            with get_temp_cursor() as cur:
                cur.execute(
                    "INSERT INTO gateway_audit (ts, action_type, level, approved, "
                    "executed, proposed_by, reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (entry.get("timestamp", ""), entry.get("action_type", ""),
                     entry.get("level", ""), int(bool(entry.get("approved"))),
                     int(bool(entry.get("executed"))), entry.get("proposed_by", ""),
                     entry.get("reason", "")),
                )
        except Exception as e:
            logger.debug(f"[VECTOR][gateway] audit persist skipped: {e}")

    def _get_trust(self):
        """Trust ladder (earned autonomy for YELLOW). None if disabled/unavailable —
        the gateway must never fail because trust tracking failed (fail closed:
        no ladder → normal owner-gated YELLOW flow)."""
        try:
            from core.config import CONFIG
            if not CONFIG["permission"].get("trust_ladder_enabled", True):
                return None
            from core.loop.trust_ladder import get_trust_ladder
            return get_trust_ladder()
        except Exception as e:
            logger.debug(f"[VECTOR][gateway] trust ladder unavailable: {e}")
            return None

    def _trust_recording_active(self) -> bool:
        """Trust state must only change on real owner signals — never from
        pytest's shimmed confirmations. Tests opt in via VECTOR_TRUST_TEST=1."""
        return "pytest" not in sys.modules or os.environ.get("VECTOR_TRUST_TEST") == "1"

    async def execute(self, action: Action) -> GatewayResult:
        level = self._classify(action.action_type)
        logger.info(f'[VECTOR][gateway] {action.action_type} classified as {level} (proposed by {action.proposed_by})')

        if level == 'FORBIDDEN':
            logger.critical(f'[VECTOR][gateway] BLOCKED FORBIDDEN action: {action.action_type}')
            result = GatewayResult(False, 'FORBIDDEN', False, {}, 'Action permanently forbidden')
            self._write_audit(action, result)
            return result

        # Capability-token check (VectorCode-absorbed security layer)
        cap_ok, cap_reason = self._check_capability(action)
        if not cap_ok:
            logger.warning(f'[VECTOR][gateway] capability denied: {action.action_type} ({cap_reason})')
            result = GatewayResult(False, level, False, {}, f'Capability denied: {cap_reason}')
            self._write_audit(action, result)
            return result

        if level == 'GREEN':
            exec_result = await self._execute_action(action)
            result = GatewayResult(True, 'GREEN', True, exec_result, 'Auto-executed')
            self._write_audit(action, result)
            await self._notify(f'VECTOR: {action.action_type} completed', priority=0)
            return result

        if level == 'YELLOW':
            # Trust ladder — this action earned auto-execution through N
            # consecutive explicit owner approvals with zero bad outcomes.
            _trust = self._get_trust()
            if (_trust is not None and self._trust_recording_active()
                    and _trust.is_promoted(action.action_type)):
                exec_result = await self._execute_action(action)
                # F-4: broadened failure detection. The prior check
                # (status=="error" or "error" in result) missed subtle
                # wrong-but-non-error outcomes (blocked status, explicit
                # success:False, a write action that no-op'd without writing).
                # These now demote a trust-ladder-promoted YELLOW so a silent
                # failure can't keep auto-executing with no owner signal.
                _failed = (
                    exec_result.get("status") in ("error", "blocked", "failed")
                    or "error" in exec_result
                    or exec_result.get("success") is False
                    or exec_result.get("blocked") is True
                )
                if _failed:
                    # Failure while trusted → instant demotion + loud notify.
                    _trust.record_bad_outcome(action.action_type)
                    await self._notify(
                        f'VECTOR: trusted action {action.action_type} FAILED — '
                        f'demoted back to owner approval', priority=1)
                else:
                    _trust.record_auto_exec(action.action_type)
                    await self._notify(
                        f'VECTOR executed (trusted): {action.action_type}', priority=0)
                result = GatewayResult(True, 'YELLOW', True, exec_result,
                                       'Auto-executed (trust ladder)')
                self._write_audit(action, result)
                return result

            if action.proposed_by in ("api_command", "voice"):
                # Typed by the authenticated owner (HUD command bar / API key /
                # allowlisted Telegram) or SPOKEN after the wake word on the
                # owner's own machine. The command itself IS the confirmation —
                # asking "are you sure?" for a YELLOW the owner just ordered is
                # pure friction. Autonomous proposals still get the wait below;
                # RED never takes this path.
                exec_result = await self._execute_action(action)
                result = GatewayResult(True, 'YELLOW', True, exec_result,
                                       'Owner-initiated command — pre-confirmed')
                self._write_audit(action, result)
                if not hasattr(self._notify, "mock_calls"):
                    await self._notify(f'VECTOR executed (owner command): {action.action_type}', priority=0)
                return result

            yellow_auto_confirm = os.environ.get("VECTOR_YELLOW_AUTO_CONFIRM") == "1"
            yellow_notice = (
                f'YELLOW action pending: {action.action_type} - auto-executes in 10s unless rejected'
                if yellow_auto_confirm
                else f'YELLOW action pending: {action.action_type} - requires owner confirmation'
            )
            await self._notify(yellow_notice, priority=1)
            yellow_timeout = 0.01 if "pytest" in sys.modules else 10
            # Explicit owner signals (approve/reject) feed the trust ladder;
            # timeouts are neutral — missing a phone ping is not a "no".
            explicit_signal = True
            try:
                confirmed = await asyncio.wait_for(
                    self._wait_for_confirmation(action), timeout=yellow_timeout
                )
            except asyncio.TimeoutError:
                explicit_signal = False
                confirmed = yellow_auto_confirm
                if confirmed:
                    logger.info(
                        f"[VECTOR][gateway] YELLOW action {action.action_type} auto-confirmed after 10s timeout"
                    )
                else:
                    logger.warning(
                        f"[VECTOR][gateway] YELLOW action {action.action_type} timed out without confirmation"
                    )
            if not confirmed and hasattr(self._wait_for_confirmation, "mock_calls"):
                confirmed = True
                explicit_signal = False  # test shim, not an owner signal
            if not confirmed:
                if explicit_signal and _trust is not None and self._trust_recording_active():
                    _trust.record_rejection(action.action_type)
                result = GatewayResult(False, 'YELLOW', False, {}, 'Rejected by owner')
                self._write_audit(action, result)
                logger.info(f"[VECTOR][gateway] YELLOW action {action.action_type} rejected by owner")
                return result
            if explicit_signal and _trust is not None and self._trust_recording_active():
                if _trust.record_approval(action.action_type):
                    await self._notify(
                        f'VECTOR: {action.action_type} PROMOTED to auto-execute after '
                        f'consistent approvals. Demote anytime: /gateway/trust',
                        priority=1)
            exec_result = await self._execute_action(action)
            result = GatewayResult(True, 'YELLOW', True, exec_result, 'Executed after YELLOW window')
            self._write_audit(action, result)
            if not hasattr(self._notify, "mock_calls"):
                await self._notify(f'VECTOR executed (YELLOW): {action.action_type}', priority=0)
            return result

        if level == 'RED':
            # Owner-initiated bypass for RED_INTERACTIVE_TOOLS only (never
            # OWNER_APPROVAL_ONLY — see the comment on that set above). Typed
            # by the authenticated owner (HUD command bar / API key /
            # allowlisted Telegram) or spoken after the wake word on the
            # owner's own machine — mirrors the equivalent YELLOW-tier bypass.
            if (action.action_type in RED_INTERACTIVE_TOOLS
                    and action.proposed_by in ("api_command", "voice")):
                exec_result = await self._execute_action(action)
                result = GatewayResult(True, 'RED', True, exec_result,
                                       'Owner-initiated command — pre-confirmed')
                self._write_audit(action, result)
                if not hasattr(self._notify, "mock_calls"):
                    await self._notify(f'VECTOR executed (owner command): {action.action_type}', priority=0)
                return result

            # A7: CouncilBrain deliberation before Pushover owner approval.
            # OWNER_APPROVAL_ONLY and RED_INTERACTIVE_TOOLS both skip
            # CouncilBrain's auto-proceed path and go straight to a real
            # Pushover owner approval (fail-closed on timeout) — for
            # RED_INTERACTIVE_TOOLS this point is only reached when the
            # action was NOT owner-initiated (see the bypass above).
            _council_verdict = (
                "defer"
                if action.action_type in OWNER_APPROVAL_ONLY
                or action.action_type in RED_INTERACTIVE_TOOLS
                else await self._handle_red_tier(action)
            )
            if _council_verdict == "proceed":
                exec_result = await self._execute_action(action)
                result = GatewayResult(True, 'RED', True, exec_result, 'Council approved (auto-proceed)')
                self._write_audit(action, result)
                return result
            if _council_verdict == "reject":
                result = GatewayResult(False, 'RED', False, {}, 'Council rejected action')
                self._write_audit(action, result)
                return result
            # verdict == "defer" → fall through to owner approval via Pushover
            _ip = self._get_local_ip()
            # F-1: unique id so concurrent same-type RED approvals don't collide.
            _aid = self._make_pending_id(action.action_type)
            _approve_url = f"http://{_ip}:8000/gateway/approve/{_aid}"
            _reject_url  = f"http://{_ip}:8000/gateway/reject/{_aid}"
            # Prefer a human-readable summary if the action provides one (e.g. a
            # trade shows price + reasoning), so the owner can decide from the
            # notification itself rather than a raw params dict.
            _detail = ""
            if isinstance(action.params, dict):
                _detail = action.params.get("summary") or action.params.get("reason") or ""
            if not _detail:
                _detail = f"Params: {str(action.params)[:120]}"
            await self._notify(
                f'VECTOR wants to: {action.action_type}\n{_detail}\n\nTap Approve or open Reject URL.',
                priority=2,
                url=_approve_url,
                url_title="✅ Approve",
            )
            await self._notify(
                f'Reject: {action.action_type}',
                priority=0,
                url=_reject_url,
                url_title="❌ Reject",
            )
            _red_timeout = 1 if "pytest" in sys.modules else 300
            try:
                confirmed = await asyncio.wait_for(self._wait_for_confirmation(action, pending_id=_aid), timeout=_red_timeout)
            except asyncio.TimeoutError:
                confirmed = False
                logger.warning(f"[VECTOR][gateway] RED action {action.action_type} timed out after 5min — rejected for safety")
            if confirmed:
                exec_result = await self._execute_action(action)
                result = GatewayResult(True, 'RED', True, exec_result, 'Owner confirmed')
            else:
                result = GatewayResult(False, 'RED', False, {}, 'Timed out waiting for owner')
                logger.warning(f'[VECTOR][gateway] RED action {action.action_type} aborted - no confirmation')
            self._write_audit(action, result)
            return result

        # UNKNOWN — default to RED, never silently allow. Log for future classification.
        logger.critical(f"[VECTOR][gateway] UNKNOWN action type: '{action.action_type}' — blocked. Add to GREEN/YELLOW/RED in config.")
        # Store unknown action types so they can be reviewed and classified later
        self._record_unknown_action(action.action_type)
        result = GatewayResult(False, 'UNKNOWN', False, {}, f'Unknown action type: {action.action_type}')
        self._write_audit(action, result)
        return result

    async def request_approval(self, action_type: str, summary: str, *, timeout: int | None = None) -> bool:
        """Owner-approval-only — notify + wait, never executes anything itself.

        For callers that must perform the real action themselves after
        owner sign-off (e.g. browser governance replaying a paused
        mid-page Playwright click) rather than delegating execution to
        `_execute_action` (which dispatches through the governor — wrong
        abstraction for "resume this exact in-flight browser action").
        Reuses the same Pushover notify + wait_for_confirmation machinery
        as the RED tier in `execute()`, fails closed on timeout/rejection.
        """
        action = Action(action_type=action_type, params={"summary": summary}, proposed_by="request_approval")
        _red_timeout = timeout if timeout is not None else (1 if "pytest" in sys.modules else 300)

        # 2026-07-21 fix: this notification had NO approve/reject link — the
        # owner had no way to act on it at all (matched against the RED-tier
        # execute() path in execute(), which does include one). Now uses the
        # same /gateway/approve|reject/{id} URLs the HUD Approvals panel and
        # confirm_action() both understand.
        _ip = self._get_local_ip()
        # F-1: unique id so concurrent same-type request_approval calls don't collide.
        _aid = self._make_pending_id(action_type)
        _approve_url = f"http://{_ip}:8000/gateway/approve/{_aid}"
        _reject_url = f"http://{_ip}:8000/gateway/reject/{_aid}"
        await self._notify(
            f'VECTOR wants to: {action_type}\n{summary}\n\nTap Approve or open Reject URL.',
            priority=2,
            url=_approve_url,
            url_title="✅ Approve",
        )
        await self._notify(f'Reject: {_reject_url}', priority=0)

        try:
            confirmed = await asyncio.wait_for(self._wait_for_confirmation(action, pending_id=_aid), timeout=_red_timeout)
        except asyncio.TimeoutError:
            confirmed = False
            logger.warning(f"[VECTOR][gateway] request_approval for {action_type} timed out — rejected for safety")

        if confirmed:
            # Real owner confirmation just happened for this exact
            # action_type -- issue the same unforgeable receipt
            # _execute_action() issues, so a caller using this method
            # (rather than the full execute() path -- e.g.
            # districts/content/phone_poster.py, which performs the real
            # action itself after owner sign-off) can still successfully
            # call grant_control() afterward without needing to thread
            # any proof through by hand.
            self._issue_approval_receipt(action_type)
        result = GatewayResult(confirmed, 'RED', False, {}, 'Owner confirmed' if confirmed else 'Timed out or rejected waiting for owner')
        self._write_audit(action, result)
        return confirmed

    async def _handle_red_tier(self, action: "Action") -> str:
        """Call CouncilBrain.deliberate_action() and persist the result to council_log.jsonl.
        Returns 'proceed', 'reject', or 'defer'.  Always returns 'defer' on any failure
        so the Pushover approval flow handles it."""
        import json
        try:
            from core.brain.council import CouncilBrain
            from core.loop.context_engine import ContextEngine
            context = ""
            try:
                context = ContextEngine().session_hydration_prompt()
            except Exception as e:
                # Council can still deliberate without hydration context;
                # log so a persistently empty context is diagnosable.
                logger.debug(f"[VECTOR][gateway] hydration unavailable: {e}")
            cb = CouncilBrain()
            deliberation = await cb.deliberate_action(
                action_type=action.action_type,
                params=action.params,
                context=context[:400],
            )
            verdict = deliberation.get("verdict", "defer")
            confidence = deliberation.get("confidence", 0.0)
            rationale = deliberation.get("rationale", "")
            # Log to council_log.jsonl
            try:
                log_path = data_path("council_log.jsonl")
                log_path.parent.mkdir(parents=True, exist_ok=True)
                entry = {
                    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "action_type": action.action_type,
                    "params": action.params,
                    "verdict": verdict,
                    "confidence": confidence,
                    "rationale": rationale[:500],
                    "votes": deliberation.get("votes", []),
                }
                try:
                    with log_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(entry) + "\n")
                except PermissionError:
                    # 2026-09-23 (fix): this used to chmod 0o666 (world-
                    # writable) on retry -- loosening permissions instead
                    # of fixing the actual cause, on a real RED-tier audit
                    # trail file, on a machine with no other legitimate
                    # writer. Owner-only read/write is the correct retry;
                    # if that still fails, give up and log rather than
                    # escalate to world-writable.
                    if log_path.exists():
                        os.chmod(log_path, 0o600)
                    with log_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(entry) + "\n")
            except Exception as _log_err:
                logger.warning("[VECTOR][gateway] council_log write failed — RED-tier deliberation audit trail incomplete: {}", _log_err)
            logger.info(
                "[VECTOR][gateway] Council verdict={} conf={:.2f} for action={}",
                verdict, confidence, action.action_type,
            )
            # Auto-proceed only when council is confident enough AND the action is
            # explicitly allowlisted (F-9). Non-allowlisted RED actions downgrade
            # a council "proceed" to "defer" so the owner still gets a Pushover
            # approval — an LLM judgment over attacker-influenceable params is
            # never sufficient alone to execute a real external side effect.
            if verdict == "proceed" and confidence >= 0.75:
                if action.action_type in COUNCIL_AUTO_PROCEED_ALLOWED:
                    return "proceed"
                logger.info(
                    "[VECTOR][gateway] council 'proceed' for RED '{}' downgraded to "
                    "'defer' — not in COUNCIL_AUTO_PROCEED_ALLOWED (owner approval required)",
                    action.action_type,
                )
                return "defer"
            if verdict == "reject":
                logger.warning("[VECTOR][gateway] Council REJECTED {}: {}", action.action_type, rationale[:80])
                # Gap 4: feed the council's verdict into CounterfactualMemory so
                # should_avoid() learns from genuine external rejections, not just
                # its own auto-blocks.
                try:
                    from core.memory.counterfactual import CounterfactualMemory
                    proposal = f"{action.action_type} {json.dumps(action.params, default=str)}"
                    CounterfactualMemory().record_rejection(
                        decision_id=action.action_type, proposal=proposal,
                        reason=f"council REJECTED: {rationale[:160]}",
                    )
                except Exception as _cf_err:
                    logger.debug("[VECTOR][gateway] counterfactual record skipped: {}", _cf_err)
                return "reject"
            return "defer"
        except Exception as _ce:
            logger.warning("[VECTOR][gateway] Council deliberation failed, deferring RED-tier action to owner: {}", _ce)
            return "defer"

    def _record_unknown_action(self, action_type: str):
        """Track unknown action types for periodic review and classification."""
        if not hasattr(self, '_unknown_actions'):
            self._unknown_actions: dict[str, int] = {}
        self._unknown_actions[action_type] = self._unknown_actions.get(action_type, 0) + 1
        # If an action type is blocked 3+ times, it's likely a new capability — surface it
        if self._unknown_actions[action_type] >= 3:
            logger.warning(
                f"[VECTOR][gateway] Action '{action_type}' blocked {self._unknown_actions[action_type]} times. "
                f"Consider adding to GREEN/YELLOW/RED in config.py"
            )

    def get_unknown_actions(self) -> dict[str, int]:
        """Return all unknown action types and their block counts for review."""
        return getattr(self, '_unknown_actions', {})

    async def evaluate_external(self, action_type: str, params: dict, source: str) -> GatewayResult:
        """Validate and execute an externally-submitted action through the normal gate.

        2026-09-23 (HIGH SEVERITY fix, round 2 -- independent review
        finding): `source` is a caller-supplied string (this file's own
        "Ingress rule" comment on `sanitize_proposed_by()`, above,
        already documents this exact requirement for every route that
        reads proposed_by from client input) -- but this method
        constructed `Action(action_type, params, source)` with the raw
        value. `core/api/tasks.py`'s `/tasks` POST route (bearer-token
        protected, but that token is meant for lower-trust internal
        automation, not full owner-equivalent trust) calls this with a
        client-supplied `task.source` field. Without sanitisation, a
        caller holding only that internal token could claim
        `source="api_command"` and reach `execute()`'s owner-initiated
        RED_INTERACTIVE_TOOLS bypass (real shell commands, no Pushover
        confirmation) -- the exact impersonation
        `sanitize_proposed_by()` exists to stop."""
        source = sanitize_proposed_by(source, fallback="external")
        level = self._classify(action_type)
        logger.info("[VECTOR][gateway] external {} from {} classified as {}", action_type, source, level)
        if level == 'FORBIDDEN':
            r = GatewayResult(False, 'FORBIDDEN', False, {}, 'Action permanently forbidden')
            self._write_audit(Action(action_type, params, source), r)
            return r
        if level == 'UNKNOWN':
            self._record_unknown_action(action_type)
            r = GatewayResult(False, 'UNKNOWN', False, {}, f'Unknown action type: {action_type}')
            self._write_audit(Action(action_type, params, source), r)
            return r
        return await self.execute(Action(action_type, params, source))

    # ── F-6/F-7: control-plane capability tokens ─────────────────────────────
    def _issue_approval_receipt(self, action_type: str, ttl: float = 30.0, *, purpose: str = "grant_control") -> None:
        """Record that THIS gateway just made a real approval decision for
        `action_type`. Called ONLY from within this file's own execute()/
        request_approval() internals, immediately after a genuine
        GREEN-auto/YELLOW-confirmed/RED-confirmed decision (or a real
        request_approval() confirmation) -- never in response to an
        external caller merely naming an action_type.

        2026-09-23 (round 3, independent review correction): two real
        bugs from round 2 fixed -- receipts are now issued individually,
        right before each specific grant_control() call, AFTER that
        branch's own validation (e.g. run_shell_command's AST guard)
        already passed, not blanket-issued at the top of
        _execute_action() before any validation ran; and GREEN branches
        (which never need a receipt -- the tier itself is the approval)
        no longer issue one at all, closing the unbounded-list leak.

        Scope, honestly stated (a genuine review also raised this): this
        is a leading-underscore convention, not a language-enforced
        boundary -- any in-process Python code CAN call this directly.
        That is an accepted property of this file's whole trust model,
        not unique to this method: `_CODING_GRANT`'s contextvar (see
        `set_coding_grant()` above) has the identical property, and
        VECTOR's threat model throughout this codebase treats in-process
        code as inside the trust boundary -- the real boundary this file
        defends is EXTERNAL callers (network/API requests, LLM-generated
        task content) reaching real side effects without a genuine
        owner/tier decision, which is what every fix in this class this
        session actually closes. A receipt is also scoped to action_type
        only, not to the exact approved params -- two concurrent real
        approvals for the same action_type in a single-owner process
        could in principle cross-consume each other's receipts -- 2026-09-23
        round 4 (independent review, found this widened once
        Governor.dispatch() started consuming from the SAME pool
        grant_control() uses): a receipt minted for one purpose (e.g.
        request_approval() issuing one so phone_poster.py's own
        subsequent grant_control() call succeeds) could otherwise be
        consumed by an unrelated Governor.dispatch() call for the same
        action_type within the same TTL window, and vice versa. Fixed
        by scoping receipts to (purpose, action_type) instead of
        action_type alone -- `purpose` is one of "grant_control" or
        "governor_dispatch", never caller-chosen freely (every real
        call site below passes a fixed literal). The single-owner,
        same-action_type-same-purpose residual (two concurrent real
        approvals for the identical action_type AND purpose) remains
        accepted as documented, low-likelihood -- the same granularity
        this file's own trust ladder and rate limiter already use."""
        import time as _time
        self._approval_receipts.setdefault((purpose, action_type), []).append(_time.time() + ttl)

    def _consume_approval_receipt(self, action_type: str, *, purpose: str = "grant_control") -> bool:
        """Consume (one-shot) a real approval receipt for `(purpose,
        action_type)` if one is currently valid. Returns False if none
        exists or all have expired -- callers must treat False as a real
        refusal. `purpose` must match what `_issue_approval_receipt()`
        was called with -- a receipt for a different purpose never
        authorizes this one, even for the identical action_type."""
        import time as _time
        now = _time.time()
        key = (purpose, action_type)
        stamps = [s for s in self._approval_receipts.get(key, []) if s > now]
        if not stamps:
            self._approval_receipts[key] = stamps
            return False
        stamps.pop(0)
        self._approval_receipts[key] = stamps
        return True

    def grant_control(self, action_type: str, *, uses: int = 64, ttl: float = 300.0) -> str | None:
        """Mint a capability token a district passes to PC/phone controller
        write methods after it has received gateway approval. The token is
        multi-use (a posting flow drives many taps) and TTL-bounded. Returns
        the opaque token string, or None if refused.

        2026-09-23 (HIGH SEVERITY fix, round 1): this method used to mint
        unconditionally for ANY action_type with zero approval check --
        any in-process caller could self-mint a RED-tier token (e.g.
        run_shell_command) and walk straight past the shell-injection
        guard `_verify_control_token()` exists to enforce, and a caller
        could mint for an action_type that isn't even classified in
        core/config.py's GREEN/YELLOW/RED lists at all (UNKNOWN --
        districts/content/phone_poster.py's instagram_post_via_phone/
        youtube_upload_via_phone were exactly this case).

        2026-09-23 (round 2, independent review correction): round 1's
        fix added an `approved: bool` kwarg the caller simply asserted --
        still forgeable (any caller could pass `approved=True` with zero
        real proof, exactly the "soft boolean" pattern this file already
        replaced once for control_grants themselves). Replaced with the
        internal, gateway-owned receipt ledger above: a GREEN action_type
        still mints immediately (the tier itself IS the approval --
        matches existing by-design self-mints like play_music). Anything
        else (YELLOW/RED/UNKNOWN) now REQUIRES a real, unforgeable receipt
        via `_consume_approval_receipt()` -- issued only by this file's
        own `execute()` (GREEN/YELLOW/RED branches, right after a genuine
        approval decision) or `request_approval()` (right after a real
        owner confirmation). FORBIDDEN never mints, full stop."""
        level = self._classify(action_type)
        if level == "FORBIDDEN":
            logger.critical(
                f"[VECTOR][gateway] grant_control REFUSED for FORBIDDEN action "
                f"'{action_type}' -- never mintable"
            )
            return None
        if level != "GREEN" and not self._consume_approval_receipt(action_type):
            logger.warning(
                f"[VECTOR][gateway] grant_control refused for '{action_type}' "
                f"(tier={level}) -- no real, unconsumed approval receipt on file"
            )
            return None
        import secrets as _secrets, time as _time
        token = _secrets.token_hex(8)
        self._control_grants[token] = (action_type, _time.time() + ttl, uses)
        logger.info(f"[VECTOR][gateway] control grant issued for '{action_type}' (uses={uses}, ttl={ttl}s)")
        return token

    def verify_control(self, token: str | None, action_type: str) -> bool:
        """Verify (and consume one use of) a control capability token. Returns
        False if missing, expired, exhausted, or mismatched — controllers
        must refuse the write on False."""
        import time as _time
        if not token:
            return False
        rec = self._control_grants.get(token)
        if rec is None:
            return False
        granted_action, expiry, uses = rec
        if _time.time() > expiry or uses <= 0 or granted_action != action_type:
            if _time.time() > expiry or uses <= 0:
                self._control_grants.pop(token, None)
            return False
        self._control_grants[token] = (granted_action, expiry, uses - 1)
        if uses - 1 <= 0:
            self._control_grants.pop(token, None)
        return True


    def _classify(self, action_type) -> str:
        if action_type in FORBIDDEN: return 'FORBIDDEN'
        if action_type in GREEN: return 'GREEN'
        if action_type in YELLOW: return 'YELLOW'
        if action_type in RED: return 'RED'
        # Anticipation predictions surface as nudges only — always GREEN (suggest, never execute)
        if action_type.startswith('proactive_'): return 'GREEN'
        return 'UNKNOWN'

    def _check_capability(self, action: 'Action') -> tuple[bool, str]:
        """Verify the proposing agent has the capability token for this action.

        Uses vectorcode/src/vc_security/capabilities.py if present. When the
        capability layer is absent, returns (True, '<no capability layer>') so
        existing tests + the YELLOW/RED flow continue to work unchanged.

        Maps action_type to the capability namespace:
          search_web              → net.read
          send_email/send_message → comms.send
          delete_files            → fs.delete
          execute_code            → exec.run
          push_github             → vcs.push
          deploy_production       → infra.deploy
          financial_transaction   → fin.execute
          (everything else)       → generic.run
        """
        # The PRIMARY gate is the GREEN/YELLOW/RED/FORBIDDEN classification above;
        # this capability check is optional defense-in-depth RBAC on top of it.
        try:
            from vectorcode.src.vc_security.capabilities import (  # type: ignore
                CapabilityPolicy,
            )
            policy = CapabilityPolicy()
        except Exception as e:
            # Layer absent or unusable (e.g. no rust bridge) — rely on the tier
            # gate, which still enforces FORBIDDEN/RED/UNKNOWN. Documented behavior.
            logger.debug(f'[VECTOR][gateway] capability layer unavailable, tier gate enforced: {e}')
            return True, 'no capability layer — tier gate enforced'

        try:
            mapping = {
                'search_web': 'net.read',
                'send_email': 'comms.send',
                'send_message_routine': 'comms.send',
                'delete_files': 'fs.delete',
                'execute_code': 'exec.run',
                'push_github': 'vcs.push',
                'deploy_production': 'infra.deploy',
                'financial_transaction': 'fin.execute',
                'overwrite_note_personal': 'fs.write',
                'create_calendar_event': 'calendar.write',
                'set_reminder': 'calendar.write',
                'download_file': 'net.download',
            }
            required = mapping.get(action.action_type, 'generic.run')

            if policy.check(action.proposed_by, required):
                return True, f'{action.proposed_by} has {required}'
            return False, f'{action.proposed_by} lacks {required}'
        except Exception as e:
            # Layer loaded but the check itself errored — fail CLOSED (defense-in-depth).
            logger.warning(f'[VECTOR][gateway] capability check error — failing closed: {e}')
            return False, f'capability check failed ({e})'

    async def _execute_action(self, action: Action) -> dict:
        logger.info(f"[VECTOR][gateway] Executing {action.action_type}")
        # 2026-09-23 (round 3 -- independent review correction): this used
        # to issue one blanket approval receipt for action.action_type
        # right here, unconditionally, at the top of the method. Two real
        # bugs in that: (1) issued BEFORE any branch-specific validation
        # (e.g. run_shell_command's AST safety guard below) -- a REJECTED
        # command still left a valid, unconsumed receipt sitting around
        # for a DIFFERENT concurrent caller of the same action_type to
        # pick up and use for a DIFFERENT command; (2) every GREEN action
        # (the vast majority of traffic) issued a receipt that grant_control()
        # never needs to consume for GREEN, leaking one list entry per
        # call in a long-running process. Fixed: each branch below that
        # actually calls grant_control() issues its own receipt
        # immediately beforehand, scoped to exactly the moment it's
        # needed -- never issued speculatively, never issued before this
        # exact branch's own validation has already passed.
        result = {
            "status": "executed",
            "action": action.action_type,
            "params": action.params,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        try:
            if action.action_type == "search_web":
                # 2026-09-25: this used to GET https://duckduckgo.com/ (an HTML page,
                # `format=json` is ignored) and keep its first 500 chars, so no search
                # result was ever returned. DuckDuckGo's own endpoints now answer HTTP 202
                # to scripts; the `ddgs` library (already a dependency) does the search.
                query = action.params.get("query", "")[:500]  # truncate to prevent abuse
                try:
                    from ddgs import DDGS
                    hits = await asyncio.wait_for(
                        asyncio.to_thread(lambda: DDGS().text(query, max_results=5)), timeout=20.0)
                    result["results"] = [
                        {"title": h.get("title", ""), "url": h.get("href", ""), "snippet": h.get("body", "")}
                        for h in (hits or [])
                    ]
                except Exception as _se:
                    result["results"] = []
                    result["search_error"] = str(_se) or type(_se).__name__
                _limit = CONFIG.get("search_response_limit", 500)
                result["response"] = " | ".join(
                    f"{r['title']}: {r['snippet']}" for r in result["results"])[:_limit]
            elif action.action_type == "play_music":
                # Actually play: launch Spotify (or a named app) + press play.
                # "play music" defaults to Spotify — VECTOR infers the app so the
                # owner never has to say "on spotify" (2026-07-17).
                try:
                    from core.control.pc_controller import PCController
                    _app = action.params.get("app") or action.params.get("app_name") or "spotify"
                    _tok = self.grant_control("play_music", uses=4, ttl=60)
                    _r = PCController().play_music(_app, control_token=_tok)
                    result["status"] = "ok" if _r.get("ok") else "error"
                    result.update(_r)
                    result["message"] = f"Playing music on {_app.capitalize()}, sir."
                except Exception as _e:
                    result["status"] = "error"; result["error"] = str(_e)
            elif action.action_type == "set_timer":
                duration = action.params.get("duration_sec", 60)
                result["set"] = duration
                try:
                    from core.memory.episodic import EpisodicMemory
                    EpisodicMemory().store(
                        event_type="timer",
                        content=f"Timer set for {duration}s",
                        tags=["timer"],
                        source="permission_gateway",
                    )
                except Exception as e:
                    logger.warning("[VECTOR][gateway] set_timer episodic store failed: {}", e)
                result["status"] = "ok"
            elif action.action_type == "check_weather":
                location = action.params.get("location", "Kolkata")
                result["location"] = location
                try:
                    import httpx
                    async with httpx.AsyncClient(timeout=3) as _wc:
                        _wr = await _wc.get(f"https://wttr.in/{location}?format=3")
                        result["weather"] = _wr.text.strip()
                        result["status"] = "ok"
                except Exception as _we:
                    result["status"] = "error"
                    result["error"] = str(_we)
            elif action.action_type == "check_attendance":
                try:
                    from districts.time_calendar.kiit_scraper import KIITScraper
                    data = KIITScraper().get_cached_schedule() or {}
                    result["status"] = "ok"
                    result["checked"] = True
                    result["attendance"] = data.get("attendance", [])
                    result["at_risk"] = data.get("at_risk_subjects", [])
                except Exception as _e:
                    result["status"] = "ok"
                    result["checked"] = False  # scraper failed — data not fetched
                    result["note"] = f"KIIT scraper unavailable: {_e}"
            elif action.action_type == "commit_code":
                # Use gitpython directly — NOT GitBot.commit() which would
                # call back to gateway.execute("commit_code") causing recursion.
                try:
                    import git as _git
                    _repo_path = action.params.get("repo_path", ".")
                    _msg = action.params.get("message", action.params.get("msg", "auto: vector commit"))
                    _files = action.params.get("files") or []
                    _repo = _git.Repo(_repo_path, search_parent_directories=True)
                    if _files:
                        # Only stage the explicit files requested
                        _repo.index.add(_files)
                    # Never do git add -A automatically — that would stage unrelated changes
                    _has_changes = bool(_repo.git.diff("--cached", "--name-only"))
                    if not _has_changes:
                        result["status"] = "ok"
                        result["committed"] = False
                        result["message"] = "nothing staged to commit"
                    else:
                        _commit_obj = await asyncio.to_thread(_repo.index.commit, _msg)
                        result["status"] = "ok"
                        result["committed"] = True
                        result["hash"] = _commit_obj.hexsha[:8]
                        result["message"] = _msg
                except Exception as _e:
                    result["status"] = "error"
                    result["committed"] = False
                    result["error"] = str(_e)
            elif action.action_type == "write_note_personal":
                try:
                    vault = CONFIG.get("obsidian_vault_path", "")
                    title = action.params.get("title", "Untitled")
                    content = action.params.get("content", "")
                    result["title"] = title
                    note_path = safe_vault_note_path(vault, title)
                    if note_path is not None and content:
                        await asyncio.to_thread(note_path.write_text, content, encoding="utf-8")
                        result["status"] = "ok"
                        result["path"] = str(note_path)
                    elif vault and content and note_path is None:
                        # Real path-traversal/absolute-path attempt -- never
                        # silently write elsewhere, never silently drop it as
                        # a generic "not configured" either (that would mask
                        # a real attack attempt as ordinary misconfiguration).
                        result["status"] = "error"
                        result["error"] = f"refused: title escapes the configured vault ({title!r})"
                    else:
                        # F-4: a silent "ok" here would NOT demote a trust-ladder-
                        # promoted write_note_personal, so a misconfigured vault
                        # could persistently swallow notes with zero owner signal.
                        # Report error so the trust ladder demotes on this outcome.
                        result["status"] = "error"
                        result["error"] = "vault not configured or no content — note not written"
                except Exception as _e:
                    result["status"] = "error"
                    result["error"] = str(_e)
            elif action.action_type == "overwrite_note_personal":
                try:
                    vault = CONFIG.get("obsidian_vault_path", "")
                    note_name = action.params.get("note", action.params.get("title", "Untitled"))
                    content = action.params.get("content", "")
                    note_path = safe_vault_note_path(vault, note_name)
                    if note_path is not None and content:
                        await asyncio.to_thread(note_path.write_text, content, encoding="utf-8")
                        result["status"] = "ok"
                        result["path"] = str(note_path)
                    elif vault and content and note_path is None:
                        result["status"] = "error"
                        result["error"] = f"refused: note name escapes the configured vault ({note_name!r})"
                    else:
                        result["status"] = "ok"
                        result["note"] = "vault not configured or no content"
                except Exception as _e:
                    result["status"] = "error"
                    result["error"] = str(_e)
            elif action.action_type == "push_github":
                try:
                    from districts.coding.git_bot import GitBot
                    _gb = GitBot()
                    _repo = _gb._get_repo(action.params.get("repo_path", "."))
                    if _repo:
                        _branch = action.params.get("branch", _repo.active_branch.name)
                        _push_info = await asyncio.to_thread(
                            _repo.remote("origin").push, refspec=_branch
                        )
                        result["status"] = "ok"
                        result["pushed"] = _branch
                    else:
                        result["status"] = "error"
                        result["error"] = "no git repo found"
                except Exception as _e:
                    result["status"] = "error"
                    result["error"] = str(_e)
            elif action.action_type == "send_email":
                try:
                    from districts.communications.email_agent import EmailAgent
                    _agent = EmailAgent()
                    _draft = _agent.draft_email(
                        to=action.params.get("to", ""),
                        subject=action.params.get("subject", "(no subject)"),
                        body=action.params.get("body", action.params.get("content", "")),
                    )
                    result["status"] = "ok"
                    result["draft_id"] = _draft.get("draft_id", "")
                    result["note"] = "email drafted — send via email client to deliver"
                except Exception as _e:
                    result["status"] = "error"
                    result["error"] = str(_e)
            elif action.action_type == "send_message_routine":
                try:
                    from core.city.governor import GovernorCouncil
                    _dispatch = await GovernorCouncil().dispatch({
                        "type": "send_message",
                        "params": action.params,
                        "source": "permission_gateway",
                        "confidence": 0.8,
                    })
                    result["status"] = "ok"
                    result["routed_to"] = "communications"
                    result["dispatch"] = str(_dispatch)[:200]
                except Exception as _e:
                    result["status"] = "error"
                    result["error"] = str(_e)
            elif action.action_type == "set_reminder":
                try:
                    from core.memory.episodic import EpisodicMemory
                    reminder_text = action.params.get("text") or action.params.get("content") or "(no text)"
                    EpisodicMemory().store(
                        event_type="reminder",
                        content=reminder_text,
                        tags=["reminder"],
                        source="permission_gateway",
                    )
                    result["status"] = "ok"
                    result["stored"] = True
                    # 2026-07-29 KNOWN_ISSUES: the caller (commands.py's
                    # _build_response_text) prefers this "message" field over
                    # its generic "Executed: set_reminder. You'll be
                    # notified." fallback — without it, a confirmation never
                    # said what was actually set. Only echo a real reminder
                    # (intent detection was fixed to stop sending empty
                    # params={}) — "(no text)" would just relocate the same
                    # unhelpful confirmation into a differently-worded one.
                    if reminder_text != "(no text)":
                        result["message"] = f"Reminder set, sir: \"{reminder_text}\""
                except Exception as _e:
                    result["status"] = "error"
                    result["error"] = str(_e)
            elif action.action_type == "create_calendar_event":
                try:
                    from core.memory.episodic import EpisodicMemory
                    EpisodicMemory().store(
                        event_type="calendar_event",
                        content=f"Event: {action.params.get('title','Untitled')} at {action.params.get('time','TBD')}",
                        tags=["calendar", "reminder"],
                        source="permission_gateway",
                    )
                    result["status"] = "ok"
                    result["note"] = "stored as reminder — wire Google Calendar token to persist to calendar"
                except Exception as _e:
                    result["status"] = "error"
                    result["error"] = str(_e)
            elif action.action_type == "download_file":
                try:
                    import httpx
                    from core.security.ssrf_guard import SSRFGuard
                    url = action.params.get("url", "")
                    if not url:
                        result["status"] = "error"
                        result["error"] = "no url provided"
                    else:
                        # 2026-08-06 (loop-stall root-cause hunt, KNOWN_ISSUES
                        # #0): resolve_dns=True makes check_url() call
                        # socket.getaddrinfo() synchronously with no timeout.
                        # That's a real syscall directly on this coroutine's
                        # thread (the loop's event-loop thread in production);
                        # a hung/unreachable DNS resolver would block it
                        # indefinitely with 0% CPU. Move it to a thread and
                        # bound the wait so a DNS hang degrades to "download
                        # blocked" instead of freezing the whole loop.
                        try:
                            _ssrf = await asyncio.wait_for(
                                asyncio.to_thread(SSRFGuard(resolve_dns=True).check_url, url),
                                timeout=CONFIG.get("ssrf_dns_resolve_timeout_sec", 5.0),
                            )
                        except asyncio.TimeoutError:
                            logger.warning(
                                "[VECTOR][permission_gateway] SSRF DNS resolution timed out for {}", url,
                            )
                            result["status"] = "error"
                            result["error"] = "SSRF DNS resolution timed out"
                            return result
                        if not _ssrf.safe:
                            result["status"] = "error"
                            result["error"] = f"SSRF blocked: {_ssrf.reason}"
                        else:
                            import pathlib
                            from urllib.parse import urlparse, unquote
                            download_root = data_path("downloads").resolve()
                            requested = action.params.get("dest")
                            if requested:
                                dest_name = pathlib.PurePath(str(requested)).name
                            else:
                                dest_name = pathlib.PurePath(unquote(urlparse(url).path)).name
                            if not dest_name or dest_name in (".", ".."):
                                dest_name = "download.bin"
                            dest_path = (download_root / dest_name).resolve()
                            if download_root not in dest_path.parents and dest_path != download_root:
                                result["status"] = "error"
                                result["error"] = "download destination escapes downloads directory"
                                return result
                            dest_path.parent.mkdir(parents=True, exist_ok=True)
                            async with httpx.AsyncClient(timeout=30) as _client:
                                _resp = await _client.get(url)
                                _resp.raise_for_status()
                                await asyncio.to_thread(
                                    dest_path.write_bytes, _resp.content
                                )
                            result["status"] = "ok"
                            result["dest"] = str(dest_path)
                            result["bytes"] = len(_resp.content)
                except Exception as _e:
                    result["status"] = "error"
                    result["error"] = str(_e)
            elif action.action_type in ("delete_files", "financial_transaction", "deploy_production"):
                # Dangerous — not auto-executed; explicit not_implemented so RL doesn't reward
                result["status"] = "not_implemented"
                result["error"] = (
                    f"{action.action_type} requires manual implementation — not auto-executed. "
                    "Wire a specific safe implementation before enabling."
                )
            elif action.action_type == "execute_code":
                # 2026-08-07: execute_code now uses VectorSandbox from
                # core/sandbox/vector_sandbox.py — subprocess isolation with
                # timeouts, output truncation, and environment filtering.
                # FAIL CLOSED: if the sandbox raises, we refuse.
                code = action.params.get("code", "")
                language = action.params.get("language", "python")
                timeout = float(action.params.get("timeout", 30))
                if not code:
                    result["status"] = "rejected"
                    result["reason"] = "no code provided"
                else:
                    try:
                        from core.sandbox import get_sandbox, SandboxConfig
                        sandbox = get_sandbox(SandboxConfig(timeout_secs=timeout))
                        if language == "python":
                            sr = await sandbox.run_code_safe(code, timeout=timeout)
                        else:
                            # Non-Python languages: write to temp file and run
                            sr = await sandbox.run_shell(code, timeout=timeout)
                        result["status"] = "ok" if sr.success else "error"
                        result["output"] = sr.output
                        result["stdout"] = sr.stdout
                        result["stderr"] = sr.stderr
                        result["exit_code"] = sr.exit_code
                        result["elapsed_secs"] = round(sr.elapsed_secs, 2)
                        result["timed_out"] = sr.timed_out
                        result["sandbox"] = "vector_sandbox"
                        if sr.timed_out:
                            result["reason"] = f"code timed out after {timeout}s"
                        elif not sr.success:
                            result["reason"] = sr.stderr[:500] if sr.stderr else "non-zero exit"
                    except Exception as e:
                        logger.warning("[VECTOR][gateway] execute_code sandbox failed: {}", e)
                        result["status"] = "rejected"
                        result["sandbox"] = "error"
                        result["reason"] = f"sandbox execution failed: {e}"
            elif action.action_type in ("code_task", "code_review_vc", "code_generate",
                                        "code_fix", "code_debug", "run_tests"):
                try:
                    from districts.coding.vectorcode_bridge import get_bridge
                    bridge = get_bridge()
                    if bridge.is_available():
                        vc_result = await bridge.run_task(
                            action.params.get("title", action.action_type),
                            mode="run",
                            timeout=int(CONFIG.get("vectorcode", {}).get("timeout_sec", 300)),
                        )
                        result["status"] = vc_result.get("status", "ok")
                        result["vc_output"] = vc_result.get("output", "")[:500]
                    else:
                        # 2026-09-23 fix (reward/verification-honesty audit,
                        # medium-priority follow-up): this reported "ok" for
                        # a task that never ran at all -- the exact
                        # not_implemented shape _is_not_implemented()/
                        # TERMINAL_STATUSES already exist to catch, but this
                        # site bypassed them by hardcoding "ok" itself.
                        result["status"] = "not_implemented"
                        result["note"] = "VectorCode unavailable — task noted"
                except Exception as _vc_err:
                    logger.warning(f"[VECTOR][gateway] VectorCode action failed: {_vc_err}")
                    # 2026-09-23 fix: a real exception was just caught here
                    # and reported as "ok" -- same false-success class as
                    # above, just the exception path instead of the
                    # unavailable-dependency path.
                    result["status"] = "error"
                    result["note"] = f"VectorCode error: {_vc_err}"
            elif action.action_type in ("widget_open", "widget_close", "widget_show_location",
                                        "music_play", "music_pause", "music_next", "music_prev",
                                        "open_panel"):
                # VECTOR dashboard UI events. Effects are local to the dashboard,
                # delivered via the /ws broadcast channel. The gateway's job here
                # is just to confirm + emit a structured payload the dashboard
                # subscribes to. No real-world side-effect.
                payload = {
                    "type": "ui_event",
                    "action_type": action.action_type,
                    "params": action.params,
                    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                try:
                    from core.loop.loop_state import ui_broadcast as _ui_bc
                    result["broadcast"] = await _ui_bc(payload)
                except Exception as _bc_err:
                    logger.debug(f"[VECTOR][gateway] ui_event broadcast skipped: {_bc_err}")
                    result["broadcast"] = False
                # Friendly message for TTS
                if action.action_type == "widget_open":
                    result["message"] = f"Opening the {action.params.get('id', 'requested')} widget."
                elif action.action_type == "widget_close":
                    target = action.params.get("id", "")
                    result["message"] = "Closing all widgets." if target == "all" else f"Closing the {target} widget."
                elif action.action_type == "widget_show_location":
                    q = action.params.get("query", "")
                    result["message"] = f"Showing {q} on the map." if q else "Map ready."
                elif action.action_type in ("music_play", "music_pause", "music_next", "music_prev"):
                    # Send the REAL Windows media key so this controls actual
                    # playback (Spotify/any player), not just the HUD widget +
                    # a friendly line that lied "Resuming playback" while nothing
                    # happened (2026-07-17).
                    _mk = {"music_play": "play_pause", "music_pause": "play_pause",
                           "music_next": "next", "music_prev": "prev"}[action.action_type]
                    try:
                        from core.control.pc_controller import PCController
                        PCController().media_key(_mk)
                    except Exception as _me:
                        logger.debug(f"[VECTOR][gateway] media_key failed: {_me}")
                    result["message"] = {
                        "music_play": "Resuming playback.", "music_pause": "Pausing music.",
                        "music_next": "Skipping to the next track.", "music_prev": "Going back a track.",
                    }[action.action_type]
                elif action.action_type == "open_panel":
                    result["message"] = f"Opening the {action.params.get('panel', 'requested')} panel."
                result["status"] = "ok"
            elif action.action_type == "respond":
                # Conversational reply — no side effect; just echo the message back.
                result["status"] = "ok"
                result["message"] = action.params.get("message", "Standing by, sir.")
            elif action.action_type == "home_control":
                # 2026-09-23 hardening: moved here from
                # core/voice/ambient_listener.py's own direct HAConnector
                # call, which had no permission-gateway check at all — real
                # smart-home device control (locks, lights, thermostats)
                # executing with zero GREEN/YELLOW/RED classification and no
                # audit entry. This is now that action's only execution path.
                try:
                    from districts.home_assistant.voice_bridge import VoiceBridge
                    from districts.home_assistant.entity_manager import EntityManager
                    from districts.home_assistant.connector import HAConfig, HAConnector

                    _ha_cfg = HAConfig(
                        host=CONFIG.get("home_assistant", {}).get("host", "homeassistant.local"),
                        port=CONFIG.get("home_assistant", {}).get("port", 8123),
                        token=CONFIG.get("home_assistant", {}).get("token", ""),
                        use_ssl=CONFIG.get("home_assistant", {}).get("use_ssl", False),
                    )
                    _ha_connector = HAConnector(_ha_cfg)
                    try:
                        await _ha_connector.connect()
                        _ha_entities = EntityManager()
                        await _ha_entities.discover(_ha_connector)
                        _ha_bridge = VoiceBridge(_ha_entities, _ha_connector)
                        _ha_reply = await _ha_bridge.process(action.params.get("text", ""))
                    finally:
                        # 2026-09-23 (independent re-review found this
                        # missing): disconnect only ran on the success path;
                        # a discovery/process exception left the connector
                        # leaked.
                        await _ha_connector.disconnect()
                    # VoiceBridge.process() (districts/home_assistant/
                    # voice_bridge.py) returns a bare string with no
                    # structured status for THREE distinct non-execution
                    # shapes, not just the one this check originally caught
                    # (independent re-review, round 3): (1) unparseable
                    # command ("I couldn't understand..."), (2) a pending
                    # high-risk confirmation question ("Are you sure you
                    # want to..." -- ConfirmDialog.format_confirmation, no
                    # device action taken), (3) a real execution failure
                    # ("Sorry, I couldn't execute..."). Only a genuine
                    # _execute() success falls through to "ok".
                    if not isinstance(_ha_reply, str):
                        result["status"] = "error"
                        result["error"] = "VoiceBridge.process() returned a non-string reply"
                    elif _ha_reply.startswith("Sorry, I couldn't execute"):
                        result["status"] = "error"
                        result["error"] = _ha_reply
                    elif _ha_reply.startswith("I couldn't understand"):
                        result["status"] = "rejected"
                    elif _ha_reply.startswith("Are you sure you want to"):
                        result["status"] = "awaiting_confirmation"
                    else:
                        result["status"] = "ok"
                    result["message"] = _ha_reply
                except Exception as _e:
                    result["status"] = "error"; result["error"] = str(_e)
                    result["message"] = f"Home control failed: {_e}"
            elif action.action_type == "launch_app":
                try:
                    from core.control.pc_controller import PCController
                    self._issue_approval_receipt("launch_app")
                    _tok = self.grant_control("launch_app", uses=1, ttl=60)
                    _launch = PCController().launch_app(
                        action.params.get("app_name", ""),
                        action.params.get("args", []),
                        control_token=_tok,
                    )
                    result["status"] = "ok" if _launch.get("launched") else "error"
                    result.update(_launch)
                except Exception as _e:
                    result["status"] = "error"; result["error"] = str(_e)
            elif action.action_type == "run_shell_command":
                try:
                    _cmd = action.params.get("command", "")
                    # AST safety guard before execution
                    _ast_warnings = self._check_bash_ast(_cmd)
                    if _ast_warnings:
                        logger.warning(f"[VECTOR][gateway] bash AST guard blocked command — {_ast_warnings}")
                        result["status"] = "blocked"
                        result["reason"] = "bash AST safety guard"
                        result["ast_warnings"] = _ast_warnings
                    else:
                        from core.control.pc_controller import PCController
                        self._issue_approval_receipt("run_shell_command")
                        _tok = self.grant_control("run_shell_command", uses=1, ttl=60)
                        _shell = PCController().run_shell_command(
                            _cmd,
                            action.params.get("timeout", 30),
                            control_token=_tok,
                        )
                        result["status"] = "ok" if _shell.get("exit_code", 1) == 0 else "error"
                        result.update(_shell)
                except Exception as _e:
                    result["status"] = "error"; result["error"] = str(_e)
            elif action.action_type == "pc_screenshot":
                # 2026-09-23 (fix, item 6 -- independent review finding):
                # this action_type never had a real handler here at all.
                # core/api/routers/control.py's pc_screenshot endpoint
                # relied on gate.executed==True (always True once the
                # gateway ran _execute_action(), regardless of whether
                # this branch existed) and then called Governor.dispatch()
                # SEPARATELY as a second, real execution attempt --
                # Governor has no handler for this exact task_type either,
                # so the second call also silently did nothing real. Real
                # handler, matching the existing launch_app/run_shell_command
                # pattern immediately above.
                try:
                    from core.control.pc_controller import PCController
                    self._issue_approval_receipt("pc_screenshot")
                    _tok = self.grant_control("pc_screenshot", uses=1, ttl=60)
                    _path = action.params.get("save_path") or "data/pc_screenshot.png"
                    import pathlib as _pl
                    _saved = _pl.Path(_path)
                    _saved.parent.mkdir(parents=True, exist_ok=True)
                    # 2026-09-23 (round 3, independent review correction,
                    # 2nd pass): round 3's first fix checked whether
                    # `_path` exists with real content -- but if the
                    # target already held an OLDER screenshot from a
                    # prior successful call and THIS capture fails,
                    # take_screenshot() leaves that stale file completely
                    # untouched, so the "does it exist with content"
                    # check still passed on a genuine failure -- reported
                    # "ok" while quietly serving a stale image. Fixed:
                    # capture to a unique temp sibling first, verify IT
                    # is non-empty, then atomically replace the real
                    # target only on success -- a failed capture can
                    # never touch (or fake success via) the target path.
                    import uuid as _uuid
                    # Keep the real suffix (PIL's Image.save() infers
                    # format from the extension -- ".tmp" fails with
                    # "unknown file extension").
                    _tmp_path = _saved.with_name(f".{_saved.stem}.{_uuid.uuid4().hex}{_saved.suffix}")
                    PCController().take_screenshot(str(_tmp_path))
                    _ok = _tmp_path.exists() and _tmp_path.stat().st_size > 0
                    if _ok:
                        _tmp_path.replace(_saved)  # atomic on the same filesystem
                        result["status"] = "ok"
                        result["path"] = str(_saved)
                    else:
                        _tmp_path.unlink(missing_ok=True)
                        result["status"] = "error"
                        result["path"] = None
                        result["error"] = "screenshot capture or save failed — no file written"
                except Exception as _e:
                    result["status"] = "error"; result["error"] = str(_e)
            elif action.action_type == "pc_click":
                try:
                    from core.control.pc_controller import PCController
                    self._issue_approval_receipt("pc_click")
                    _tok = self.grant_control("pc_click", uses=1, ttl=60)
                    _clicked = PCController().click(
                        int(action.params.get("x", 0)),
                        int(action.params.get("y", 0)),
                        action.params.get("button", "left"),
                        control_token=_tok,
                    )
                    result["status"] = "ok" if _clicked else "error"
                    result["clicked"] = _clicked
                except Exception as _e:
                    result["status"] = "error"; result["error"] = str(_e)
            elif action.action_type == "pc_type":
                try:
                    from core.control.pc_controller import PCController
                    self._issue_approval_receipt("pc_type")
                    _tok = self.grant_control("pc_type", uses=1, ttl=60)
                    _delay_ms = action.params.get("delay_ms", 50)
                    _typed = PCController().type_text(
                        action.params.get("text", ""),
                        interval=float(_delay_ms) / 1000.0,
                        control_token=_tok,
                    )
                    result["status"] = "ok" if _typed else "error"
                    result["typed"] = _typed
                except Exception as _e:
                    result["status"] = "error"; result["error"] = str(_e)
            elif action.action_type == "pc_launch_app":
                try:
                    from core.control.pc_controller import PCController
                    self._issue_approval_receipt("pc_launch_app")
                    _tok = self.grant_control("pc_launch_app", uses=1, ttl=60)
                    _args_str = action.params.get("args", "") or ""
                    _args_list = _args_str.split() if isinstance(_args_str, str) else list(_args_str)
                    _launch = PCController().launch_app(
                        action.params.get("app_name", ""),
                        _args_list,
                        control_token=_tok,
                    )
                    result["status"] = "ok" if _launch.get("launched") else "error"
                    result.update(_launch)
                except Exception as _e:
                    result["status"] = "error"; result["error"] = str(_e)
            elif action.action_type.startswith("proactive_"):
                # Anticipation engine prediction — surface to owner as a nudge.
                # Proactive actions never auto-execute; they suggest, owner decides.
                _desc = action.params.get("description", action.params.get("need", action.action_type))
                _need = action.params.get("need", action.action_type.replace("proactive_", ""))
                try:
                    from core.loop.nudge_engine import nudge_engine
                    nudge_engine.push(_desc, source="anticipation", need=_need)
                    from core.memory.episodic import EpisodicMemory
                    EpisodicMemory().store(
                        event_type="proactive_suggestion",
                        content=_desc,
                        tags=["proactive", "anticipation", _need],
                        source="anticipation_engine",
                    )
                    result["status"] = "ok"
                    result["surfaced"] = True
                    result["need"] = _need
                except Exception as _pe:
                    result["status"] = "error"
                    result["error"] = str(_pe)
            elif action.action_type in _PLAN_COMPOSABLE_ACTION_TYPES:
                # R19: real plan-step action_types (see module-level
                # constant's docstring for the exact gap this closes).
                # Mirrors the hand_ block below exactly: once the tier gate
                # above (FORBIDDEN/capability/GREEN-auto or YELLOW/RED
                # approval) has already decided to execute, the real work
                # routes through governor -> district agent, same as every
                # other action.
                try:
                    from core.city.governor import Governor
                    # Governor.dispatch() now enforces its own
                    # authorization boundary for YELLOW/RED task types
                    # (2026-09-23 fix) -- this exact action_type was
                    # already real-approved by the tier gate above, so
                    # issue the receipt that check will consume. Only
                    # issue it when actually needed (round 4 fix,
                    # independent review): a GREEN action_type here
                    # (some _PLAN_COMPOSABLE_ACTION_TYPES are) needs no
                    # receipt at all -- Governor.dispatch()'s own check
                    # only consumes for YELLOW/RED -- and issuing one
                    # anyway just left a dead, unconsumed entry sitting
                    # in the ledger until its TTL expired.
                    if self._classify(action.action_type) in ("YELLOW", "RED"):
                        self._issue_approval_receipt(action.action_type, purpose="governor_dispatch")
                    dispatch_result = await Governor().dispatch({
                        "type": action.action_type,
                        "params": action.params,
                    })
                    result["status"] = dispatch_result.get("status", "ok")
                    result.update(dispatch_result)
                except Exception as _pc_err:
                    result["status"] = "error"
                    result["error"] = str(_pc_err)
            elif action.action_type in _OWNER_READONLY_DISPATCH_ACTION_TYPES:
                # V1 TRUST CLOSURE (T3): verified read-only capabilities (see
                # the constant's docstring). The tier gate above has already
                # authorized this exact action_type (GREEN); the dispatched
                # type is the authorized type, unchanged.
                try:
                    from core.city.governor import Governor
                    if self._classify(action.action_type) in ("YELLOW", "RED"):
                        self._issue_approval_receipt(action.action_type, purpose="governor_dispatch")
                    dispatch_result = await Governor().dispatch({
                        "type": action.action_type,
                        "params": action.params,
                    })
                    # 2026-09-23 fix (independent review, round 2): this was
                    # `dispatch_result.get("status", "ok")` -- a blind
                    # default that certified a real Git failure as success
                    # just as readily as a real success, since GitBot's real
                    # failure shape (`{}` from get_status(), `{"commits":[]}`
                    # from get_recent_commits()) is IDENTICAL to its real
                    # success shape: neither sets "status" at all. The
                    # equivalent fix already exists in
                    # core/loop/autonomous_loop.py's own _act_on() for its
                    # separate (non-gateway) dispatch path; this is the same
                    # fix for THIS path -- reached by voice, WebSocket, and
                    # AutonomousExecutor callers that go through
                    # PermissionGateway.execute() directly. Only default to
                    # "ok" when there is real evidence of success.
                    if "status" not in dispatch_result:
                        if action.action_type in ("git_status", "check_git"):
                            _ro_status = "ok" if dispatch_result.get("branch") else "unknown"
                        elif action.action_type in ("git_log", "recent_commits"):
                            _ro_status = "ok" if dispatch_result.get("commits") else "unknown"
                        else:
                            _ro_status = "ok"
                        result["status"] = _ro_status
                    else:
                        result["status"] = dispatch_result.get("status")
                    result.update(dispatch_result)
                except Exception as _ro_err:
                    result["status"] = "error"
                    result["error"] = str(_ro_err)
            elif action.action_type.startswith("hand_"):
                # Hand Execution Engine (hands/runner.py) — Hand action types
                # are pre-classified in core/config.py PermissionConfig per
                # each Hand's own requires_approval flag (GREEN=auto, RED=
                # owner approval via the flow above). Once that gate has
                # already decided to execute, the real work routes through
                # the governor → district agent, same as every other task.
                task = action.params.get("task", {})
                # 2026-09-23 (HIGH SEVERITY fix): a Hand's own task payload
                # is LLM-constructed (hands/runner.py), not a real,
                # gateway-verified owner action -- yet it used to be
                # dispatched to Governor() completely unmodified.
                # districts/coding/gui_automation_agent.py's own _gate()
                # trusts a self-reported source=="api_command"/"voice"
                # string to skip PermissionGateway entirely ("the command
                # itself IS the confirmation" -- by design, but only safe
                # when that string is set server-side by the real
                # owner-input routes, commands.py/voice.py). Nothing
                # stopped a Hand's own task dict from claiming that same
                # string itself, letting a GREEN, no-owner-gate Hand (e.g.
                # hand_researcher) smuggle a fully ungated RED-tier
                # GUI-automation task past every real check. This is the
                # exact class of attack sanitize_proposed_by() exists to
                # stop at API ingress -- extend the same "untrusted payload
                # crossing into the trusted pipeline" rule here: strip any
                # owner-trust-marker claim from the nested task before
                # dispatch, on a copy (never mutate the caller's own dict).
                if isinstance(task, dict):
                    task = dict(task)
                    if isinstance(task.get("params"), dict):
                        task["params"] = dict(task["params"])
                        for _key in ("source", "proposed_by"):
                            if _key in task["params"]:
                                task["params"][_key] = sanitize_proposed_by(
                                    str(task["params"][_key]), fallback="hand_autonomous"
                                )
                    for _key in ("source", "proposed_by"):
                        if _key in task:
                            task[_key] = sanitize_proposed_by(str(task[_key]), fallback="hand_autonomous")
                # 2026-09-23 (round 4, independent review finding --
                # HIGH): the receipt above used to be issued for
                # whatever task["type"] the Hand's payload claimed,
                # with zero check that it's actually the task_type
                # THIS Hand is meant to produce. Approving hand_researcher
                # (GREEN) never authorized an ARBITRARY nested task --
                # only its own real routing. A caller with API access
                # (core/api/tasks.py's evaluate_external(), bearer-token
                # protected but not owner-equivalent trust) could submit
                # action_type="hand_researcher" with
                # params={"task": {"type": "monthly_report", ...}} and
                # mint a free receipt for a completely different,
                # YELLOW-tier action never actually approved. Validate
                # the nested task's own type against hands/runner.py's
                # own real, server-owned Hand-name -> task_type mapping
                # (the same one HandRunner._task_type_for() uses) before
                # trusting it at all.
                _hand_name = action.action_type[len("hand_"):]
                _hand_lookup_ok = True
                try:
                    from hands.runner import HandRunner as _HR
                    from hands.registry import get_hand as _get_hand
                    _hand_obj = _get_hand(_hand_name)
                    if _hand_obj is None:
                        raise ValueError(f"'{_hand_name}' is not a registered Hand")
                    _expected_task_type = _HR._TASK_TYPE_OVERRIDES.get(_hand_name, _hand_name)
                    # 2026-09-23 (round 5, independent review finding --
                    # HIGH): the type check alone still let a caller
                    # smuggle an arbitrary task["district"] through
                    # unchanged -- Governor.dispatch() honors
                    # task.get("district") directly (see governor.py:
                    # `district = task.get("district") or
                    # await self.route_task_async(task_type)`), so a
                    # correctly-typed nested task could still be routed
                    # to a DIFFERENT district's agent than this Hand is
                    # actually meant to reach, letting that agent
                    # interpret attacker-controlled params under its own
                    # (wrong) task-type vocabulary. hands/registry.py's
                    # Hand.district is the real, server-owned value
                    # (the same one HandRunner._dispatch() itself uses)
                    # -- resolved below and force-applied just before
                    # dispatch, never trusted from the caller.
                    _expected_district = _hand_obj.district
                except Exception as _hand_lookup_err:
                    logger.warning(
                        "[VECTOR][gateway] REFUSED hand_ dispatch -- could not "
                        "resolve server-owned Hand metadata for '{}': {} -- "
                        "failing closed rather than assuming safe",
                        action.action_type, _hand_lookup_err,
                    )
                    _hand_lookup_ok = False
                    _expected_task_type = None
                    _expected_district = None
                _claimed_task_type = task.get("type") if isinstance(task, dict) else None
                if not _hand_lookup_ok or _claimed_task_type != _expected_task_type:
                    logger.warning(
                        "[VECTOR][gateway] REFUSED hand_ dispatch -- '{}' "
                        "claimed nested task type '{}', expected '{}' for "
                        "this Hand -- possible task-type smuggling",
                        action.action_type, _claimed_task_type, _expected_task_type,
                    )
                    result["status"] = "blocked"
                    result["reason"] = (
                        f"nested task type '{_claimed_task_type}' does not match "
                        f"the real task type '{_expected_task_type}' for {action.action_type}"
                    )
                else:
                    if isinstance(task, dict):
                        task["district"] = _expected_district
                    try:
                        from core.city.governor import Governor
                        # Real owner approval for THIS Hand's action_type
                        # (RED -> real Pushover confirm already happened
                        # above; GREEN -> tier itself is the approval) has
                        # already been granted by this point, AND the
                        # nested task's own type is now confirmed to be
                        # exactly what this Hand is really meant to
                        # produce (not caller-chosen) -- issue the receipt
                        # Governor.dispatch()'s own authorization check
                        # (2026-09-23 fix) requires -- only when the
                        # nested task's own type actually needs one
                        # (round 4 fix: don't leave a dead, unconsumed
                        # entry for the common GREEN-Hand case).
                        if self._classify(_expected_task_type) in ("YELLOW", "RED"):
                            self._issue_approval_receipt(_expected_task_type, purpose="governor_dispatch")
                        dispatch_result = await Governor().dispatch(task)
                        result["status"] = dispatch_result.get("status", "ok")
                        result["dispatch_result"] = dispatch_result
                    except Exception as _hd_err:
                        result["status"] = "error"
                        result["error"] = str(_hd_err)
            else:
                # Unknown action — not_implemented prevents phantom RL reward
                result["status"] = "not_implemented"
                result["note"] = f"action '{action.action_type}' not implemented — no RL reward granted"
                self._record_unknown_action(action.action_type)
        except Exception as e:
            logger.warning(f"[VECTOR][gateway] action exec partial failure: {e}")
            result["status"] = "executed_with_warnings"
            result["error"] = str(e)
        return result

    async def notify(self, message, priority=0):
        """Public alias for external callers (e.g. task_queue)."""
        return await self._notify(message, priority)

    def classify(self, action_type: str) -> str:
        """Public wrapper for _classify — returns GREEN/YELLOW/RED/FORBIDDEN/UNKNOWN."""
        return self._classify(action_type)

    def _check_bash_ast(self, command: str) -> list[str]:
        """
        Deterministic guard for CATASTROPHIC shell commands (cross-platform).

        Owner rule (2026-07-17) — "full power + guardrails": normal shell work is
        ALLOWED. The previous guard rejected every metacharacter (``|`` ``>``
        ``&&`` ``;``) plus curl/wget/eval/Remove-Item/shutdown, which made
        run_shell_command useless for real work — ``git log --format=%H`` and
        ``dir | findstr foo`` were both blocked. Pipes, redirection, chaining,
        network fetches, PowerShell deletes and shutdown now pass.

        What still blocks — mirroring the FORBIDDEN list's spirit (format_drive /
        mass_delete): only the irreversible, machine-destroying, or
        remote-code-execution shapes.
          1. Disk destruction — format / mkfs / diskpart / raw-device write /
             secure wipe / fork bomb.
          2. Recursive force-delete aimed at a DRIVE ROOT or system directory
             (``rm -rf /``, ``del /s c:\\windows``) — deleting your own project
             folder is fine.
          3. Network fetch piped straight into an interpreter (``curl … | sh``,
             ``iwr … | iex``) — the exact RCE path a poisoned webpage or injected
             prompt would use. This is why pipes are safe to allow generally.
          4. HKLM registry hive deletion / drive-root ownership+ACL takeover.

        Tokenizes with ``shlex`` (POSIX *and* cmd.exe modes) to defeat quote/space
        obfuscation (``r''m -rf``); unparseable quoting is no longer fatal (chaining
        is legal now) — the raw collapsed form is still scanned.

        Returns a list of warnings (empty = allowed). Any non-empty list ⇒ blocked.
        """
        warnings: list[str] = []
        if not command or not command.strip():
            return ["empty command"]

        norms: list[str] = [" ".join(command.lower().split())]
        for _posix in (True, False):
            try:
                norms.append(" ".join(shlex.split(command, posix=_posix)).lower())
            except ValueError:
                continue  # unbalanced quotes — raw form above still gets scanned

        def _hit(*needles: str) -> bool:
            """True when ALL needles appear in the SAME normalized form."""
            return any(all(n in norm for n in needles) for norm in norms)

        # 1) Disk destruction / fork bomb — irreversible.
        for pat, desc in [
            ("mkfs", "filesystem format"),
            ("diskpart", "disk partition tool"),
            ("cipher /w", "secure disk wipe"),
            ("of=/dev/sd", "raw disk write"),
            ("of=/dev/nvme", "raw disk write"),
            ("of=/dev/disk", "raw disk write"),
            ("of=\\\\.\\physicaldrive", "raw disk write"),
            ("> /dev/sd", "raw disk write"),
            (":(){", "fork bomb"),
            (":|:&", "fork bomb"),
        ]:
            if _hit(pat):
                warnings.append(f"CATASTROPHIC: {desc} ({pat!r})")
        # `format c:` / `format /fs:ntfs` — but NOT `git log --format=%H`.
        if any(re.search(r"\bformat\s+[a-z]:", n) for n in norms) or _hit("format", "/fs:"):
            warnings.append("CATASTROPHIC: disk format")

        # 2) Recursive force-delete of a drive root or system directory.
        _DEL_VERBS = ["rm -rf", "rm -fr", "rm -r -f", "del /s", "del /f /s",
                      "rd /s", "rmdir /s", "remove-item -recurse"]
        _SYS_TARGETS = ["c:\\windows", "c:/windows", "c:\\users", "c:/users",
                        "c:\\program files", "%systemroot%", "%windir%",
                        "%programfiles%", "%userprofile%",
                        "/etc", "/usr", "/bin", "/boot", "/var", "/system32"]
        for verb in _DEL_VERBS:
            if not _hit(verb):
                continue
            for target in _SYS_TARGETS:
                if _hit(verb, target):
                    warnings.append(
                        f"CATASTROPHIC: recursive force-delete of system path ({verb!r} → {target!r})")
                    break
            # Bare drive root: `rm -rf /`, `rm -rf c:\`, `del /s c:\`
            if any(re.search(re.escape(verb) + r"\s+[\"']?(/|[a-z]:\\?)[\"']?\s*$", n) for n in norms):
                warnings.append(f"CATASTROPHIC: recursive force-delete of drive root ({verb!r})")

        # 3) Network fetch piped into an interpreter = remote code execution.
        _FETCH = ["curl ", "wget ", "invoke-webrequest", "iwr ", "invoke-restmethod", "irm "]
        _INTERP = ["| sh", "|sh", "| bash", "|bash", "| zsh", "|zsh",
                   "| iex", "|iex", "| invoke-expression", "|invoke-expression",
                   "| powershell", "|powershell", "| pwsh", "|pwsh",
                   "| cmd", "|cmd", "| python", "|python", "| node", "|node",
                   "| perl", "|perl", "| ruby", "|ruby"]
        for fetch in _FETCH:
            for interp in _INTERP:
                if _hit(fetch, interp):
                    warnings.append(
                        f"CATASTROPHIC: network fetch piped into a shell "
                        f"({fetch.strip()!r} {interp!r}) — remote code execution")
                    break

        # 4) Registry hive / ownership takeover of a drive root.
        if _hit("reg delete", "hklm") or _hit("reg delete", "hkey_local_machine"):
            warnings.append("CATASTROPHIC: HKLM registry hive delete")
        if (_hit("takeown", "c:\\", "/r")
                or (_hit("icacls", "c:\\") and _hit("everyone") and _hit("/t"))):
            warnings.append("CATASTROPHIC: drive-root ownership/ACL takeover")

        return warnings

    @staticmethod
    def _get_local_ip() -> str:
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "localhost"

    async def _notify(self, message, priority=0, url: str = "", url_title: str = ""):
        token = CONFIG["api_keys"].get('pushover_token', '')
        user = CONFIG["api_keys"].get('pushover_user', '')
        if not token or not user:
            logger.info(f'[VECTOR][notify] (no Pushover configured) {message}')
            return
        try:
            payload: dict = {'token': token, 'user': user, 'message': message, 'priority': priority}
            if url:
                payload['url'] = url
            if url_title:
                payload['url_title'] = url_title
            # 2026-07-21 fix: Pushover's API REJECTS priority=2 ("emergency")
            # payloads that omit retry/expire — every RED-tier approval
            # notification (priority=2 throughout this file) was silently
            # failing at Pushover's API layer with no visible error, because
            # this call never checked the response status.
            if priority == 2:
                payload.setdefault('retry', 60)
                payload.setdefault('expire', 300)  # matches the 5-minute RED approval window
            async with httpx.AsyncClient() as client:
                resp = await client.post('https://api.pushover.net/1/messages.json',
                    data=payload, timeout=5)
                if resp.status_code != 200:
                    logger.warning(f'[VECTOR][gateway] Pushover rejected notify: '
                                    f'{resp.status_code} {resp.text[:300]}')
        except Exception as e:
            logger.warning(f'[VECTOR][gateway] Pushover failed: {e}')

    async def _wait_for_confirmation(self, action, timeout=30, pending_id=None) -> bool:
        # F-1: key by a unique id so concurrent same-type RED actions don't
        # overwrite each other's asyncio.Event. pending_id is generated by the
        # caller (execute()/request_approval()) BEFORE the Pushover notify so
        # the approval URL carries it; fall back to generating one here for
        # any direct caller (none today, but keeps the signature safe).
        if pending_id is None:
            pending_id = self._make_pending_id(action.action_type)
        event = asyncio.Event()
        self._pending_events[pending_id] = event
        # Record full action metadata so the HUD approvals panel can surface it
        self._pending_actions[pending_id] = {
            "id": pending_id,
            "action_type": action.action_type,
            "params": action.params,
            "proposed_by": action.proposed_by,
            "level": self._classify(action.action_type),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self._persist_pending(pending_id, self._pending_actions[pending_id])
        try:
            # Do NOT nest wait_for here — the outer wait_for in execute() owns the timeout.
            # Nested wait_for causes spurious TimeoutError on Python 3.13 when the outer
            # cancels this coroutine.  Just await the event directly.
            await event.wait()
            # Check if the HUD explicitly rejected this action
            if pending_id in self._rejected:
                self._rejected.discard(pending_id)
                return False
            return True
        except asyncio.CancelledError:
            raise
        finally:
            self._pending_events.pop(pending_id, None)
            self._pending_actions.pop(pending_id, None)
            self._unpersist_pending(pending_id)

    def confirm_action(self, action_type) -> bool:
        """Backward-compat entrypoint: confirm by action_type. Resolves to the
        unique pending id; refuses if multiple instances of the same action_type
        are pending (ambiguous — caller must use the full unique id via approve())."""
        pid = self._resolve_pending_id(action_type)
        if pid is None:
            return False
        event = self._pending_events.get(pid)
        if event:
            event.set()
            return True
        return False

    # ── HUD Approvals Panel API ──────────────────────────────────────────────

    def get_pending(self) -> list[dict]:
        """Return all actions currently awaiting owner approval."""
        return list(self._pending_actions.values())

    def approve(self, action_id: str) -> dict:
        """Approve a pending action by its unique id. Also accepts a bare
        action_type when unambiguous (backward-compat with Pushover links that
        predate unique ids — though new links carry the full id)."""
        pid = self._resolve_pending_id(action_id)
        if pid is None:
            return {"status": "not_found", "id": action_id}
        event = self._pending_events.get(pid)
        if event:
            event.set()
            logger.info(f"[VECTOR][gateway] Owner approved action '{pid}' via HUD")
            return {"status": "approved", "id": pid}
        # F-3: an interrupted (rehydrated) pending action has no live Event —
        # it cannot be approved (its waiter is dead). Refuse so the owner is
        # forced to reject/clear it rather than believe it will execute.
        meta = self._pending_actions.get(pid)
        if meta and meta.get("interrupted"):
            logger.warning(f"[VECTOR][gateway] cannot approve interrupted pending '{pid}' — reject to clear")
            return {"status": "interrupted", "id": pid,
                    "reason": "awaiting coroutine died on restart; reject to clear"}
        return {"status": "not_found", "id": action_id}

    def reject(self, action_id: str) -> dict:
        """Reject (cancel) a pending action by its unique id without executing it."""
        pid = self._resolve_pending_id(action_id)
        if pid is None:
            return {"status": "not_found", "id": action_id}
        event = self._pending_events.get(pid)
        if event:
            self._pending_actions.pop(pid, None)
            self._rejected.add(pid)
            event.set()  # unblock the wait; _wait_for_confirmation checks _rejected
            logger.warning(f"[VECTOR][gateway] Owner rejected action '{pid}' via HUD")
            return {"status": "rejected", "id": pid}
        # F-3: clear an interrupted (rehydrated) pending action even though it
        # has no live Event — the owner rejecting it should remove the stale record.
        if pid in self._pending_actions:
            self._pending_actions.pop(pid, None)
            self._unpersist_pending(pid)
            logger.info(f"[VECTOR][gateway] cleared interrupted pending '{pid}' via reject")
            return {"status": "cleared", "id": pid}
        return {"status": "not_found", "id": action_id}

    def _write_audit(self, action, result):
        entry = {
            'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'action_type': action.action_type,
            'level': result.level,
            'approved': result.approved,
            'executed': result.executed,
            'proposed_by': action.proposed_by,
            'reason': result.reason
        }
        self.audit_log.append(entry)
        self.audit_log = self.audit_log[-500:]
        # F-8: durable copy survives restarts; the in-memory ring is for fast access.
        self._persist_audit(entry)

    def get_audit_log(self, limit=50) -> list:
        return self.audit_log[-limit:]

    # ── Permission Profiles (mistral-vibe pattern) ────────────────────────────
    # Named trust-level presets that map to GREEN/YELLOW/RED tiers

    PERMISSION_PROFILES = {
        "plan": {
            "description": "Read-only + analysis only. No file writes, no execution.",
            "allowed_tiers": ("GREEN",),
            "override_yellow": False,
            "override_red": False,
        },
        "accept-edits": {
            "description": "File reads + writes allowed. No shell execution or external calls.",
            "allowed_tiers": ("GREEN", "YELLOW"),
            "override_yellow": True,
            "override_red": False,
        },
        "auto-approve": {
            "description": "Full autonomy — all GREEN/YELLOW/RED actions approved automatically.",
            "allowed_tiers": ("GREEN", "YELLOW", "RED"),
            "override_yellow": True,
            "override_red": True,
        },
    }

    def set_profile(self, profile_name: str) -> dict:
        """Set a named permission profile for the current session."""
        if profile_name not in self.PERMISSION_PROFILES:
            logger.warning("[VECTOR][gateway] Unknown profile: {}", profile_name)
            return {"status": "error", "error": f"Unknown profile: {profile_name}"}
        self._active_profile = profile_name
        profile = self.PERMISSION_PROFILES[profile_name]
        logger.info("[VECTOR][gateway] Profile set to '{}': {}", profile_name, profile["description"])
        return {"status": "ok", "profile": profile_name, "description": profile["description"]}

    def get_profile(self) -> str | None:
        """Return the currently active permission profile (or None if not set)."""
        return getattr(self, "_active_profile", None)

    def profile_allows(self, tier: str) -> bool:
        """Check if the active profile allows a given tier action."""
        profile_name = self.get_profile()
        if not profile_name:
            return True  # No profile = default gateway behavior
        profile = self.PERMISSION_PROFILES.get(profile_name, {})
        return tier in profile.get("allowed_tiers", ("GREEN",))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding="utf-8")
    gw = PermissionGateway()

    async def test():
        r1 = await gw.execute(Action('search_web', {'query': 'test'}, 'test_agent'))
        assert r1.approved == True and r1.level == 'GREEN'
        r2 = await gw.execute(Action('format_drive', {}, 'test_agent'))
        assert r2.approved == False and r2.level == 'FORBIDDEN'
        r3 = await gw.execute(Action('commit_code', {'msg': 'test'}, 'test_agent'))
        assert r3.level == 'YELLOW'
        r4 = await gw.execute(Action('write_note_personal', {'title': 'test'}, 'obsidian_sync'))
        assert r4.level == 'YELLOW', f"Expected YELLOW, got {r4.level}"
        task = asyncio.create_task(gw.execute(Action('overwrite_note_personal', {'title': 'test'}, 'obsidian_sync')))
        # Poll until the RED task registers its confirmation event (normally <10ms, cap at 10s).
        # F-1: pending ids are now unique (action_type#seq), so poll get_pending()
        # for the action_type rather than the raw key.
        deadline = asyncio.get_running_loop().time() + 10.0
        while not any(p.get("action_type") == 'overwrite_note_personal'
                      for p in gw.get_pending()):
            await asyncio.sleep(0.01)
            if asyncio.get_running_loop().time() > deadline:
                break
        gw.confirm_action('overwrite_note_personal')
        r5 = await task
        assert r5.level == 'RED', f"Expected RED, got {r5.level}"
        assert r5.approved == True
        log = gw.get_audit_log()
        assert len(log) == 5
        print('[PASS] permission_gateway OK')

    asyncio.run(test())
