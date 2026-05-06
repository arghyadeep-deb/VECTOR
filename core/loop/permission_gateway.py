import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.config import CONFIG
from loguru import logger
import asyncio, datetime, httpx
from dataclasses import dataclass, field

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
            await self._notify(f'VECTOR needs approval for: {action.action_type}. Confirm in dashboard.', priority=2)
            confirmed = await self._wait_for_confirmation(action)
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

    def _classify(self, action_type) -> str:
        if action_type in FORBIDDEN: return 'FORBIDDEN'
        if action_type in GREEN: return 'GREEN'
        if action_type in YELLOW: return 'YELLOW'
        if action_type in RED: return 'RED'
        return 'UNKNOWN'

    async def _execute_action(self, action) -> dict:
        logger.info(f'[VECTOR][gateway] Executing {action.action_type}')
        return {'status': 'executed', 'action': action.action_type, 'params': action.params, 'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat()}

    async def _notify(self, message, priority=0):
        token = CONFIG.get('pushover_token', '')
        user = CONFIG.get('pushover_user', '')
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
        log = gw.get_audit_log()
        assert len(log) == 3
        print('✅ permission_gateway.py OK')

    asyncio.run(test())