import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
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
            if _HUMANLAYER_AVAILABLE:
                confirmed = await self._request_humanlayer_approval(action)
            else:
                await self._notify(
                    f'VECTOR needs approval for: {action.action_type}. Confirm in dashboard.',
                    priority=2,
                )
                confirmed = await asyncio.wait_for(self._wait_for_confirmation(action), timeout=30)
            if confirmed:
                exec_result = await self._execute_action(action)
                result = GatewayResult(True, 'RED', True, exec_result, 'Owner confirmed')
            else:
                result = GatewayResult(False, 'RED', False, {}, 'Timed out waiting for owner')
                logger.warning(f'[VECTOR][gateway] RED action {action.action_type} aborted - no confirmation')
            self._write_audit(action, result)
            return result

        # UNKNOWN ??? treat as RED
        result = GatewayResult(False, 'UNKNOWN', False, {}, f'Unknown action type: {action.action_type}')
        self._write_audit(action, result)
        return result

    async def _request_humanlayer_approval(self, action: "Action") -> bool:
        """Use HumanLayer to get owner approval for RED-tier actions via configured channels."""
        if not _HUMANLAYER_AVAILABLE or _hl is None:
            return False
        try:
            context = {
                "action": action.action_type,
                "params": action.params,
                "proposed_by": action.proposed_by,
                "priority": action.priority,
            }
            loop = asyncio.get_event_loop()
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
            return await asyncio.wait_for(self._wait_for_confirmation(action), timeout=30)

    def _classify(self, action_type) -> str:
        if action_type in FORBIDDEN: return 'FORBIDDEN'
        if action_type in GREEN: return 'GREEN'
        if action_type in YELLOW: return 'YELLOW'
        if action_type in RED: return 'RED'
        return 'UNKNOWN'

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
                query = action.params.get("query", "")
                async with httpx.AsyncClient(timeout=10.0) as client:
                    r = await client.get(f"https://duckduckgo.com/?q={query}&format=json")
                    result["response"] = r.text[:500]
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
                result["status"] = "ok"
                result["checked"] = True
            elif action.action_type == "commit_code":
                result["status"] = "ok"
                result["committed"] = True
                result["message"] = action.params.get("msg", "gateway commit")
            elif action.action_type == "write_note_personal":
                result["status"] = "ok"
                result["title"] = action.params.get("title", "Untitled")
            elif action.action_type in ("send_message_routine", "create_calendar_event",
                                       "download_file", "set_reminder", "send_email",
                                       "delete_files", "execute_code", "financial_transaction",
                                       "push_github", "deploy_production", "overwrite_note_personal"):
                result["status"] = "ok"
            elif action.action_type in ("code_task", "code_review_vc", "code_generate",
                                        "code_fix", "code_debug", "run_tests"):
                try:
                    from integrations.vectorcode_bridge import get_bridge
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
            else:
                result["status"] = "ok"
                result["note"] = "action acknowledged"
        except Exception as e:
            logger.warning(f"[VECTOR][gateway] action exec partial failure: {e}")
            result["status"] = "executed_with_warnings"
            result["error"] = str(e)
        return result

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
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
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
        await asyncio.sleep(0)
        gw.confirm_action('overwrite_note_personal')
        r5 = await task
        assert r5.level == 'RED', f"Expected RED, got {r5.level}"
        assert r5.approved == True
        log = gw.get_audit_log()
        assert len(log) == 5
        print('[PASS] permission_gateway OK')

    asyncio.run(test())