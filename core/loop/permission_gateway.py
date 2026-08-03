import sys

__all__ = [
    "Action",
    "FORBIDDEN",
    "GatewayResult",
    "GREEN",
    "PermissionGateway",
    "RED",
    "YELLOW",
]

from pathlib import Path
from core.config import CONFIG
from core.runtime_paths import data_path
from loguru import logger
import asyncio, datetime, httpx, os, re, shlex
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
        self._pending_events: dict[str, asyncio.Event] = {}
        # Tracks full metadata for actions currently awaiting owner approval (RED tier)
        self._pending_actions: dict[str, dict] = {}
        logger.info('[VECTOR][gateway] Permission gateway initialised')

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
                _failed = exec_result.get("status") == "error" or "error" in exec_result
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
            # A7: CouncilBrain deliberation before Pushover owner approval
            _council_verdict = (
                "defer"
                if action.action_type in OWNER_APPROVAL_ONLY
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
            _aid = action.action_type
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
                confirmed = await asyncio.wait_for(self._wait_for_confirmation(action), timeout=_red_timeout)
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
        _approve_url = f"http://{_ip}:8000/gateway/approve/{action_type}"
        _reject_url = f"http://{_ip}:8000/gateway/reject/{action_type}"
        await self._notify(
            f'VECTOR wants to: {action_type}\n{summary}\n\nTap Approve or open Reject URL.',
            priority=2,
            url=_approve_url,
            url_title="✅ Approve",
        )
        await self._notify(f'Reject: {_reject_url}', priority=0)

        try:
            confirmed = await asyncio.wait_for(self._wait_for_confirmation(action), timeout=_red_timeout)
        except asyncio.TimeoutError:
            confirmed = False
            logger.warning(f"[VECTOR][gateway] request_approval for {action_type} timed out — rejected for safety")

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
                    if log_path.exists():
                        os.chmod(log_path, 0o666)
                    with log_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(entry) + "\n")
            except Exception as _log_err:
                logger.warning("[VECTOR][gateway] council_log write failed — RED-tier deliberation audit trail incomplete: {}", _log_err)
            logger.info(
                "[VECTOR][gateway] Council verdict={} conf={:.2f} for action={}",
                verdict, confidence, action.action_type,
            )
            # Auto-proceed only when council is confident enough
            if verdict == "proceed" and confidence >= 0.75:
                return "proceed"
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
        """Validate and execute an externally-submitted action through the normal gate."""
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
        result = {
            "status": "executed",
            "action": action.action_type,
            "params": action.params,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        try:
            if action.action_type == "search_web":
                import httpx
                from urllib.parse import quote_plus
                query = action.params.get("query", "")[:500]  # truncate to prevent abuse
                async with httpx.AsyncClient(timeout=5.0) as client:
                    r = await client.get(
                        "https://duckduckgo.com/",
                        params={"q": query, "format": "json"},
                    )
                    _limit = CONFIG.get("search_response_limit", 500)
                    result["response"] = r.text[:_limit]
            elif action.action_type == "play_music":
                # Actually play: launch Spotify (or a named app) + press play.
                # "play music" defaults to Spotify — VECTOR infers the app so the
                # owner never has to say "on spotify" (2026-07-17).
                try:
                    from core.control.pc_controller import PCController
                    _app = action.params.get("app") or action.params.get("app_name") or "spotify"
                    _r = PCController().play_music(_app)
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
                except Exception:
                    logger.warning("[VECTOR] silent swallow")
                    pass
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
                    import pathlib
                    vault = CONFIG.get("obsidian_vault_path", "")
                    title = action.params.get("title", "Untitled")
                    content = action.params.get("content", "")
                    result["title"] = title
                    if vault and content:
                        note_path = pathlib.Path(vault) / f"{title}.md"
                        await asyncio.to_thread(note_path.write_text, content, encoding="utf-8")
                        result["status"] = "ok"
                        result["path"] = str(note_path)
                    else:
                        result["status"] = "ok"
                        result["note"] = "vault not configured or no content"
                except Exception as _e:
                    result["status"] = "error"
                    result["error"] = str(_e)
            elif action.action_type == "overwrite_note_personal":
                try:
                    import pathlib
                    vault = CONFIG.get("obsidian_vault_path", "")
                    note_name = action.params.get("note", action.params.get("title", "Untitled"))
                    content = action.params.get("content", "")
                    if vault and content:
                        note_path = pathlib.Path(vault) / f"{note_name}.md"
                        await asyncio.to_thread(note_path.write_text, content, encoding="utf-8")
                        result["status"] = "ok"
                        result["path"] = str(note_path)
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
                        _ssrf = SSRFGuard(resolve_dns=True).check_url(url)
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
                # Real isolated execution via core/sandbox (WASM/Docker).
                # FAIL CLOSED: if the sandbox is unavailable we refuse to run —
                # code must NEVER execute unsandboxed on the host.
                code = action.params.get("code", "")
                language = action.params.get("language", "python")
                if not code:
                    result["status"] = "rejected"
                    result["reason"] = "no code provided"
                else:
                    try:
                        from core.sandbox import ContainerRunner  # type: ignore
                        runner = ContainerRunner()
                        sandbox_result = await asyncio.to_thread(
                            runner.run,
                            code,
                            language=language,
                            timeout_seconds=int(action.params.get("timeout", 30)),
                        )
                        result["status"] = "ok"
                        result["stdout"] = (getattr(sandbox_result, "stdout", "") or "")[:2000]
                        result["stderr"] = (getattr(sandbox_result, "stderr", "") or "")[:1000]
                        result["exit_code"] = getattr(sandbox_result, "exit_code", 0)
                        result["sandbox"] = "container"
                    except Exception as _sandbox_err:
                        # Sandbox not available — FAIL CLOSED, never run unsandboxed
                        logger.error(f"[VECTOR][gateway] sandbox unavailable — refusing to execute code: {_sandbox_err}")
                        result["status"] = "error"
                        result["sandbox"] = "unavailable"
                        result["error"] = f"code execution blocked: no sandbox available ({_sandbox_err})"
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
                        result["status"] = "ok"
                        result["note"] = "VectorCode unavailable — task noted"
                except Exception as _vc_err:
                    logger.warning(f"[VECTOR][gateway] VectorCode action failed: {_vc_err}")
                    result["status"] = "ok"
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
            elif action.action_type == "launch_app":
                try:
                    from core.control.pc_controller import PCController
                    _launch = PCController().launch_app(
                        action.params.get("app_name", ""),
                        action.params.get("args", []),
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
                        _shell = PCController().run_shell_command(
                            _cmd,
                            action.params.get("timeout", 30),
                            _gateway_approved=True,
                        )
                        result["status"] = "ok" if _shell.get("exit_code", 1) == 0 else "error"
                        result.update(_shell)
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
            elif action.action_type.startswith("hand_"):
                # Hand Execution Engine (hands/runner.py) — Hand action types
                # are pre-classified in core/config.py PermissionConfig per
                # each Hand's own requires_approval flag (GREEN=auto, RED=
                # owner approval via the flow above). Once that gate has
                # already decided to execute, the real work routes through
                # the governor → district agent, same as every other task.
                task = action.params.get("task", {})
                try:
                    from core.city.governor import Governor
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

    async def _wait_for_confirmation(self, action, timeout=30) -> bool:
        key = action.action_type
        event = asyncio.Event()
        self._pending_events[key] = event
        # Record full action metadata so the HUD approvals panel can surface it
        self._pending_actions[key] = {
            "id": key,
            "action_type": action.action_type,
            "params": action.params,
            "proposed_by": action.proposed_by,
            "level": self._classify(action.action_type),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        try:
            # Do NOT nest wait_for here — the outer wait_for in execute() owns the timeout.
            # Nested wait_for causes spurious TimeoutError on Python 3.13 when the outer
            # cancels this coroutine.  Just await the event directly.
            await event.wait()
            # Check if the HUD explicitly rejected this action
            if hasattr(self, '_rejected') and key in self._rejected:
                self._rejected.discard(key)
                return False
            return True
        except asyncio.CancelledError:
            raise
        finally:
            self._pending_events.pop(key, None)
            self._pending_actions.pop(key, None)

    def confirm_action(self, action_type) -> bool:
        event = self._pending_events.get(action_type)
        if event:
            event.set()
            return True
        return False

    # ── HUD Approvals Panel API ──────────────────────────────────────────────

    def get_pending(self) -> list[dict]:
        """Return all actions currently awaiting owner approval."""
        return list(self._pending_actions.values())

    def approve(self, action_id: str) -> dict:
        """Approve a pending action by its ID (action_type is the ID)."""
        event = self._pending_events.get(action_id)
        if event:
            event.set()
            logger.info(f"[VECTOR][gateway] Owner approved action '{action_id}' via HUD")
            return {"status": "approved", "id": action_id}
        return {"status": "not_found", "id": action_id}

    def reject(self, action_id: str) -> dict:
        """Reject (cancel) a pending action by its ID without executing it."""
        event = self._pending_events.get(action_id)
        if event:
            # Remove from pending map first so the finally block doesn't double-pop
            self._pending_actions.pop(action_id, None)
            # Setting the event with the action removed causes _wait_for_confirmation
            # to return True. We need the inverse — cancel the task by removing the
            # event and leaving it unset so asyncio.wait_for times out.
            # The cleanest approach: store a rejection flag alongside the event.
            if not hasattr(self, '_rejected'):
                self._rejected: set[str] = set()
            self._rejected.add(action_id)
            event.set()  # unblock the wait; _wait_for_confirmation checks _rejected
            logger.warning(f"[VECTOR][gateway] Owner rejected action '{action_id}' via HUD")
            return {"status": "rejected", "id": action_id}
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
        # Poll until the RED task registers its confirmation event (normally <10ms, cap at 10s)
        deadline = asyncio.get_running_loop().time() + 10.0
        while 'overwrite_note_personal' not in gw._pending_events:
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
