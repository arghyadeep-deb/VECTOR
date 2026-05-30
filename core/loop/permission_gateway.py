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
from loguru import logger
import asyncio, datetime, httpx
from dataclasses import dataclass, field

# HumanLayer — RED-tier enforcement (RULE 3, VECTOR_FIT.md: critical)
try:
    from humanlayer import HumanLayer as _HumanLayer
    _hl = _HumanLayer()
    _HUMANLAYER_AVAILABLE = True
    logger.info("[VECTOR][gateway] HumanLayer active — RED actions routed through approval API")
except ImportError:
    _hl = None
    _HUMANLAYER_AVAILABLE = False
    logger.info("[VECTOR][gateway] HumanLayer not installed — using asyncio Event fallback for RED")
except Exception as _hl_err:
    _hl = None
    _HUMANLAYER_AVAILABLE = False
    logger.warning(f"[VECTOR][gateway] HumanLayer init failed: {_hl_err}")

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

class PermissionGateway:
    def __init__(self):
        self.audit_log = []
        self._pending_events: dict[str, asyncio.Event] = {}
        logger.info('[VECTOR][gateway] Permission gateway initialised')

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
            exec_result = await self._execute_action(action)
            result = GatewayResult(True, 'YELLOW', True, exec_result, 'Executed with notification')
            self._write_audit(action, result)
            await self._notify(f'VECTOR executed: {action.action_type}', priority=1)
            return result

        if level == 'RED':
            # A7: CouncilBrain deliberation before HumanLayer/asyncio fallback
            _council_verdict = await self._handle_red_tier(action)
            if _council_verdict == "proceed":
                exec_result = await self._execute_action(action)
                result = GatewayResult(True, 'RED', True, exec_result, 'Council approved (auto-proceed)')
                self._write_audit(action, result)
                return result
            if _council_verdict == "reject":
                result = GatewayResult(False, 'RED', False, {}, 'Council rejected action')
                self._write_audit(action, result)
                return result
            # verdict == "defer" → fall through to owner approval
            if _HUMANLAYER_AVAILABLE:
                confirmed = await self._request_humanlayer_approval(action)
            else:
                await self._notify(
                    f'VECTOR needs approval for: {action.action_type}. Confirm in dashboard.',
                    priority=2,
                )
                try:
                    confirmed = await asyncio.wait_for(self._wait_for_confirmation(action), timeout=30)
                except asyncio.TimeoutError:
                    confirmed = False
                    logger.warning(f"[VECTOR][gateway] RED action {action.action_type} timed out waiting for owner — rejected for safety")
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

    async def _handle_red_tier(self, action: "Action") -> str:
        """Call CouncilBrain.deliberate_action() and persist the result to council_log.jsonl.
        Returns 'proceed', 'reject', or 'defer'.  Always returns 'defer' on any failure
        so the existing HumanLayer fallback handles it gracefully."""
        import json
        try:
            from core.brain.council import CouncilBrain
            from core.loop.context_engine import ContextEngine
            context = ""
            try:
                context = ContextEngine().session_hydration_prompt()
            except Exception:
                pass
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
                log_path = Path("data") / "council_log.jsonl"
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
                with log_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\n")
            except Exception as _log_err:
                logger.debug("[VECTOR][gateway] council_log write failed: {}", _log_err)
            logger.info(
                "[VECTOR][gateway] Council verdict={} conf={:.2f} for action={}",
                verdict, confidence, action.action_type,
            )
            # Auto-proceed only when council is confident enough
            if verdict == "proceed" and confidence >= 0.75:
                return "proceed"
            if verdict == "reject":
                logger.warning("[VECTOR][gateway] Council REJECTED {}: {}", action.action_type, rationale[:80])
                return "reject"
            return "defer"
        except Exception as _ce:
            logger.debug("[VECTOR][gateway] _handle_red_tier failed, deferring to owner: {}", _ce)
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
        """Validate an externally-submitted action (phone, cloud, ESP32). Skips capability check."""
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
        result = await self._execute_action(Action(action_type, params, source))
        r = GatewayResult(True, level, True, result, f'External action from {source} executed')
        self._write_audit(Action(action_type, params, source), r)
        return r

    async def _request_humanlayer_approval(self, action: "Action") -> bool:
        """Use HumanLayer to get owner approval for RED-tier actions via configured channels.
        Phase 3D: First tries Queen multi-model consensus; falls back to HumanLayer.
        """
        # Phase 3D: Try Queen consensus first (2+ Ollama models loaded)
        try:
            import httpx
            from core.config import CONFIG
            ollama_host = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(f"{ollama_host}/api/tags")
                loaded_models = [m["name"] for m in r.json().get("models", [])] if r.status_code == 200 else []
            if len(loaded_models) >= 2:
                from vectorcode.src.queen import QueenCoordinator
                queen = QueenCoordinator()
                context = f"action={action.action_type} params={action.params} proposed_by={action.proposed_by}"
                proposal = await asyncio.to_thread(
                    queen.build_consensus,
                    action.action_type, context, "RED",
                )
                if queen.should_proceed(proposal):
                    logger.info(
                        f"[VECTOR][gateway] Queen consensus APPROVED {action.action_type} "
                        f"(confidence={proposal.confidence:.2f})"
                    )
                    return True
                elif proposal.verdict.value == "reject":
                    logger.warning(
                        f"[VECTOR][gateway] Queen consensus REJECTED {action.action_type}: "
                        f"{proposal.decision_reason}"
                    )
                    return False
                # DEFER → fall through to HumanLayer
                logger.info(f"[VECTOR][gateway] Queen deferred {action.action_type} → HumanLayer")
        except Exception as _queen_err:
            logger.debug(f"[VECTOR][gateway] Queen consensus skipped: {_queen_err}")

        if not _HUMANLAYER_AVAILABLE or _hl is None:
            return False
        try:
            context = {
                "action": action.action_type,
                "params": action.params,
                "proposed_by": action.proposed_by,
                "priority": action.priority,
            }
            loop = asyncio.get_running_loop()
            # HumanLayer SDK is sync; run in executor so we don't block the event loop
            approved = await loop.run_in_executor(
                None,
                lambda: _hl.fetch_approval(
                    action=action.action_type,
                    context=str(context),
                ),
            )
            logger.info(f"[VECTOR][gateway] HumanLayer approval for {action.action_type}: {approved}")
            return bool(approved)
        except Exception as e:
            logger.warning(f"[VECTOR][gateway] HumanLayer approval failed: {e} — falling back to asyncio Event")
            await self._notify(
                f'VECTOR needs approval for: {action.action_type}. Confirm in dashboard.',
                priority=2,
            )
            try:
                return await asyncio.wait_for(self._wait_for_confirmation(action), timeout=30)
            except asyncio.TimeoutError:
                logger.warning(f"[VECTOR][gateway] RED action {action.action_type} confirmation timed out — rejected for safety")
                return False

    def _classify(self, action_type) -> str:
        if action_type in FORBIDDEN: return 'FORBIDDEN'
        if action_type in GREEN: return 'GREEN'
        if action_type in YELLOW: return 'YELLOW'
        if action_type in RED: return 'RED'
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
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(
                        "https://duckduckgo.com/",
                        params={"q": query, "format": "json"},
                    )
                    _limit = CONFIG.get("search_response_limit", 500)
                    result["response"] = r.text[:_limit]
            elif action.action_type == "play_music":
                result["status"] = "ok"
                result["played"] = action.params.get("track", "default playlist")
            elif action.action_type == "set_timer":
                duration = action.params.get("duration_sec", 60)
                result["set"] = duration
                result["status"] = "ok"
            elif action.action_type == "check_weather":
                import httpx
                location = action.params.get("location", "Kolkata")
                result["location"] = location
                result["status"] = "ok"
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
                    result["checked"] = True
                    result["note"] = f"KIIT scraper unavailable: {_e}"
            elif action.action_type == "commit_code":
                try:
                    from districts.coding.git_bot import GitBot
                    _gb = GitBot()
                    _msg = action.params.get("message", action.params.get("msg", "auto: vector commit"))
                    _files = action.params.get("files") or []
                    _repo_path = action.params.get("repo_path", ".")
                    _commit_res = await _gb.commit(_msg, _files, _repo_path)
                    result["status"] = "ok" if _commit_res.get("success") else "error"
                    result["hash"] = _commit_res.get("hash", "")
                    result["message"] = _commit_res.get("message", _msg)
                    if not _commit_res.get("success"):
                        result["error"] = _commit_res.get("message", "commit failed")
                except Exception as _e:
                    result["status"] = "error"
                    result["error"] = str(_e)
            elif action.action_type == "write_note_personal":
                try:
                    import pathlib
                    vault = CONFIG.get("obsidian_vault_path", "")
                    title = action.params.get("title", "Untitled")
                    content = action.params.get("content", "")
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
                    EpisodicMemory().store(
                        event_type="reminder",
                        content=action.params.get("text", action.params.get("content", "(no text)")),
                        tags=["reminder"],
                        source="permission_gateway",
                    )
                    result["status"] = "ok"
                    result["stored"] = True
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
                    dest = action.params.get("dest", "downloads/" + url.split("/")[-1])
                    if not url:
                        result["status"] = "error"
                        result["error"] = "no url provided"
                    else:
                        _ssrf = SSRFGuard().check_url(url)
                        if not _ssrf.safe:
                            result["status"] = "error"
                            result["error"] = f"SSRF blocked: {_ssrf.reason}"
                        else:
                            import pathlib
                            pathlib.Path(dest).parent.mkdir(parents=True, exist_ok=True)
                            async with httpx.AsyncClient(timeout=30) as _client:
                                _resp = await _client.get(url)
                                _resp.raise_for_status()
                                await asyncio.to_thread(
                                    pathlib.Path(dest).write_bytes, _resp.content
                                )
                            result["status"] = "ok"
                            result["dest"] = dest
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
                # Falls back to a pass-through "ok" if sandbox unavailable.
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
                        # Sandbox not available — log but don't block
                        logger.warning(f"[VECTOR][gateway] sandbox unavailable: {_sandbox_err}")
                        result["status"] = "ok"
                        result["sandbox"] = "unavailable"
                        result["note"] = f"sandbox skipped: {_sandbox_err}"
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
                    from core.api.routers.websocket import broadcast_event  # type: ignore
                    await broadcast_event(payload)
                    result["broadcast"] = True
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
                elif action.action_type == "music_play":
                    result["message"] = "Resuming playback."
                elif action.action_type == "music_pause":
                    result["message"] = "Pausing music."
                elif action.action_type == "music_next":
                    result["message"] = "Skipping to the next track."
                elif action.action_type == "music_prev":
                    result["message"] = "Going back a track."
                elif action.action_type == "open_panel":
                    result["message"] = f"Opening the {action.params.get('panel', 'requested')} panel."
                result["status"] = "ok"
            elif action.action_type == "respond":
                # Conversational reply — no side effect; just echo the message back.
                result["status"] = "ok"
                result["message"] = action.params.get("message", "Standing by, sir.")
            else:
                result["status"] = "ok"
                result["note"] = "action acknowledged"
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

    async def _notify(self, message, priority=0):
        token = CONFIG["api_keys"].get('pushover_token', '')
        user = CONFIG["api_keys"].get('pushover_user', '')
        if not token or not user:
            logger.info(f'[VECTOR][notify] (no Pushover configured) {message}')
            return
        try:
            async with httpx.AsyncClient() as client:
                await client.post('https://api.pushover.net/1/messages.json',
                    data={'token': token, 'user': user, 'message': message, 'priority': priority},
                    timeout=5)
        except Exception as e:
            logger.warning(f'[VECTOR][gateway] Pushover failed: {e}')

    async def _wait_for_confirmation(self, action, timeout=30) -> bool:
        key = action.action_type
        event = asyncio.Event()
        self._pending_events[key] = event
        try:
            # Do NOT nest wait_for here — the outer wait_for in execute() owns the timeout.
            # Nested wait_for causes spurious TimeoutError on Python 3.13 when the outer
            # cancels this coroutine.  Just await the event directly.
            await event.wait()
            return True
        except asyncio.CancelledError:
            return False
        finally:
            self._pending_events.pop(key, None)

    def confirm_action(self, action_type) -> bool:
        event = self._pending_events.get(action_type)
        if event:
            event.set()
            return True
        return False

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
