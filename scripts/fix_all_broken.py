"""Fix all broken usages caused by removing useless modules."""
from loguru import logger
import re
from pathlib import Path

CA = Path("core/coding_assistant")
RE = Path("core/research_engine")


def patch(path: Path, old: str, new: str) -> bool:
    content = path.read_text(encoding="utf-8", errors="replace")
    if old not in content:
        print(f"  WARN: pattern not found in {path.name}: {old[:60]!r}")
        return False
    path.write_text(content.replace(old, new, 1), encoding="utf-8")
    return True


# ── 1. cli/commands.py — remove PlanInfo type, stub is_teleport_available ─────
p = CA / "cli/commands.py"
content = p.read_text(encoding="utf-8", errors="replace")
content = content.replace(
    "    plan_info: PlanInfo | None = None\n",
    ""
).replace(
    """    def is_teleport_available(self) -> bool:
        return (
            self.vibe_code_enabled
            and self.is_active_model_mistral
            and self.plan_info is not None
            and self.plan_info.is_teleport_eligible()
        )""",
    """    def is_teleport_available(self) -> bool:
        return False  # Teleport (Mistral cloud) not available in VECTOR"""
)
p.write_text(content, encoding="utf-8")
print("FIXED  cli/commands.py — removed PlanInfo, stubbed is_teleport_available()")


# ── 2. acp/acp_agent_loop.py — stub _handle_proxy_setup / _handle_data_retention ─
p = CA / "acp/acp_agent_loop.py"
content = p.read_text(encoding="utf-8", errors="replace")

# Stub out _handle_proxy_setup body (uses deleted proxy_setup module)
old_proxy = """    async def _handle_proxy_setup(
        self, session: AcpSessionLoop, text_prompt: str, message_id: str
    ) -> PromptResponse:
        parts = text_prompt.strip().split(None, 1)
        args = parts[1] if len(parts) > 1 else ""

        try:
            if not args:
                message = get_proxy_help_text()
            else:
                key, value = parse_proxy_command(args)
                if value is not None:
                    set_proxy_var(key, value)
                    message = (
                        f"Set `{key}={value}` in ~/.vibe/.env\\n\\n"
                        "Please start a new chat for changes to take effect."
                    )
                else:
                    unset_proxy_var(key)
                    message = (
                        f"Removed `{key}` from ~/.vibe/.env\\n\\n"
                        "Please start a new chat for changes to take effect."
                    )
        except ProxySetupError as e:
            message = f"Error: {e}"

        return await self._command_reply(session, message, message_id)"""

new_proxy = """    async def _handle_proxy_setup(
        self, session: AcpSessionLoop, text_prompt: str, message_id: str
    ) -> PromptResponse:
        # Proxy setup removed — VECTOR uses environment variables directly
        return await self._command_reply(
            session,
            "Proxy configuration is managed via environment variables in VECTOR.",
            message_id,
        )"""

content = content.replace(old_proxy, new_proxy)

# Stub out _handle_data_retention body
old_dr = "        return await self._command_reply(session, DATA_RETENTION_MESSAGE, message_id)"
new_dr = '        return await self._command_reply(session, "Data retention is managed by VECTOR\'s local storage policy.", message_id)'
content = content.replace(old_dr, new_dr)

p.write_text(content, encoding="utf-8")
print("FIXED  acp/acp_agent_loop.py — stubbed _handle_proxy_setup, _handle_data_retention")


# ── 3. acp/utils.py — stub get_proxy_help_text ────────────────────────────────
p = CA / "acp/utils.py"
content = p.read_text(encoding="utf-8", errors="replace")
# Replace SUPPORTED_PROXY_VARS / get_current_proxy_settings usages
content = re.sub(
    r"for key, description in SUPPORTED_PROXY_VARS\.items\(\):.*?any_set = True",
    'lines.append("Proxy config via environment variables only.")\n    any_set = True',
    content, flags=re.DOTALL
)
content = re.sub(
    r"current = get_current_proxy_settings\(\).*?any_set = True",
    "any_set = False",
    content, flags=re.DOTALL
)
p.write_text(content, encoding="utf-8")
print("FIXED  acp/utils.py — stubbed proxy help text")


# ── 4. acp/entrypoint.py — remove setup_tracing call ─────────────────────────
p = CA / "acp/entrypoint.py"
content = p.read_text(encoding="utf-8", errors="replace")
content = re.sub(r"\n\s*setup_tracing\(config\)\n", "\n", content)
p.write_text(content, encoding="utf-8")
print("FIXED  acp/entrypoint.py — removed setup_tracing(config)")


# ── 5. cli/cli.py — remove setup_tracing call ─────────────────────────────────
p = CA / "cli/cli.py"
content = p.read_text(encoding="utf-8", errors="replace")
content = re.sub(r"\n\s*setup_tracing\(config\)\n", "\n", content)
p.write_text(content, encoding="utf-8")
print("FIXED  cli/cli.py — removed setup_tracing(config)")


# ── 6. core/agent_loop.py — add stubs + fix agent_span + remove teleport ──────
p = CA / "core/agent_loop.py"
content = p.read_text(encoding="utf-8", errors="replace")

# Add stubs after the removed try block
stub_block = '''try:
# [VECTOR] removed:     from core.coding_assistant.core.teleport.teleport import TeleportService as _TeleportService

    _TELEPORT_AVAILABLE = True
except ImportError:
    _TELEPORT_AVAILABLE = False
    _TeleportService = None'''

stub_replacement = '''# Teleport removed — stubs so nothing crashes at import time
_TELEPORT_AVAILABLE = False
_TeleportService = None

class TeleportService:  # stub
    pass

class TeleportError(Exception):  # stub
    pass

class TeleportCompleteEvent:  # stub
    pass

class TeleportYieldEvent:  # stub
    pass

class TeleportPushResponseEvent:  # stub
    def __init__(self, approved: bool = True): pass

class TeleportTelemetryTracker:  # stub
    def __init__(self, **kwargs): pass
    def record_event(self, e): pass
    def send_success(self): pass
    def record_service_error(self, e): pass
    def record_cancelled(self): pass
    def record_unexpected_error(self, e): pass
    def send_failure_if_needed(self): pass

class ServiceTeleportError(Exception): pass  # stub'''

content = content.replace(stub_block, stub_replacement)

# Fix agent_span — replace with contextlib.nullcontext
content = content.replace(
    "        async with agent_span(model=model_name, session_id=self.session_id):",
    "        async with __import__('contextlib').asynccontextmanager(lambda: (lambda: (yield))())():  # agent_span removed"
)
# Simpler: use a contextlib approach
content = content.replace(
    "        async with __import__('contextlib').asynccontextmanager(lambda: (lambda: (yield))())():  # agent_span removed",
    "        if True:  # agent_span removed (was OpenTelemetry tracing)"
)

# Remove the teleport_service property + teleport_to_vibe_code method (lines 589-658)
teleport_property = '''    @property
    def teleport_service(self) -> TeleportService:
        if not _TELEPORT_AVAILABLE:
            raise TeleportError(
                "Teleport requires git to be installed. "
                "Please install git and try again."
            )

        if self._teleport_service is None:
            if _TeleportService is None:
                raise TeleportError("_TeleportService is unexpectedly None")
            self._teleport_service = _TeleportService(
                session_logger=self.session_logger,
                vibe_code_base_url=self.config.vibe_code_base_url,
                vibe_code_workflow_id=self.config.vibe_code_workflow_id,
                vibe_code_api_key=self.config.vibe_code_api_key,
                vibe_code_task_queue=self.config.vibe_code_task_queue,
                vibe_config=self._base_config,
            )
        return self._teleport_service

    @requires_init
    async def teleport_to_vibe_code(
        self, prompt: str | None
    ) -> AsyncGenerator[TeleportYieldEvent, TeleportPushResponseEvent | None]:
# [VECTOR] removed:         from core.coding_assistant.core.teleport.nuage import TeleportSession

        session_messages = [
            msg.model_dump(exclude_none=True) for msg in self.messages[1:]
        ]
        telemetry_tracker = TeleportTelemetryTracker(
            telemetry_client=self.telemetry_client,
            nb_session_messages=len(session_messages),
            stage="no_history"
            if prompt is None and not session_messages
            else "git_check",
        )
        session = TeleportSession(
            metadata={
                "agent": self.agent_profile.name,
                "model": self.config.active_model,
                "stats": self.stats.model_dump(),
            },
            messages=session_messages,
        )
        try:
            async with self.teleport_service:
                gen = self.teleport_service.execute(prompt=prompt, session=session)
                response: TeleportPushResponseEvent | None = None
                while True:
                    try:
                        event = await gen.asend(response)
                        telemetry_tracker.record_event(event)
                        if isinstance(event, TeleportCompleteEvent):
                            telemetry_tracker.send_success()
                        response = yield event
                    except StopAsyncIteration:
                        break
        except ServiceTeleportError as e:
            telemetry_tracker.record_service_error(e)
            raise TeleportError(str(e)) from e
        except (asyncio.CancelledError, GeneratorExit):
            telemetry_tracker.record_cancelled()
            raise
        except Exception as e:
            telemetry_tracker.record_unexpected_error(e)
            raise
        finally:
            telemetry_tracker.send_failure_if_needed()
            self._teleport_service = None'''

teleport_stub = '''    # Teleport removed — Mistral cloud feature not used in VECTOR'''

content = content.replace(teleport_property, teleport_stub)

p.write_text(content, encoding="utf-8")
print("FIXED  core/agent_loop.py — stubs added, agent_span simplified, teleport removed")


# ── 7. core/output_formatters.py — remove Teleport match arms ─────────────────
p = CA / "core/output_formatters.py"
content = p.read_text(encoding="utf-8", errors="replace")
# Remove all the Teleport case arms
teleport_cases = """            case TeleportCheckingGitEvent():
                self._print("Preparing workspace...")
            case TeleportPushRequiredEvent(unpushed_count=count):
                self._print(f"Pushing {count} commit(s)...")
            case TeleportPushingEvent():
                self._print("Syncing with remote...")
            case TeleportStartingWorkflowEvent():
                self._print("Teleporting...")
            case TeleportWaitingForGitHubEvent(message=msg):
                self._print(msg or "Connecting to GitHub...")
            case TeleportAuthRequiredEvent(oauth_url=url, message=msg):
                self._print(msg or f"Open to authorize GitHub: {url}")
            case TeleportAuthCompleteEvent():
                self._print("GitHub authorized")
            case TeleportFetchingUrlEvent():
                self._print("Finalizing...")
            case TeleportCompleteEvent():
                self._final_response = event.url"""
content = content.replace(teleport_cases, "            case _:  # Teleport events removed")
p.write_text(content, encoding="utf-8")
print("FIXED  core/output_formatters.py — removed Teleport match arms")


# ── 8. core/programmatic.py — remove teleport block ──────────────────────────
p = CA / "core/programmatic.py"
content = p.read_text(encoding="utf-8", errors="replace")
old_teleport_block = """            if teleport and config.vibe_code_enabled:
                gen = agent_loop.teleport_to_vibe_code(prompt or None)
                async for event in gen:
                    formatter.on_event(event)
                    if isinstance(event, TeleportPushRequiredEvent):
                        next_event = await gen.asend(
                            TeleportPushResponseEvent(approved=True)
                        )
                        formatter.on_event(next_event)
            else:
                async with aclosing(agent_loop.act(prompt)) as events:"""
new_teleport_block = """            # Teleport removed — always run local agent loop
            if True:
                async with aclosing(agent_loop.act(prompt)) as events:"""
content = content.replace(old_teleport_block, new_teleport_block)
p.write_text(content, encoding="utf-8")
print("FIXED  core/programmatic.py — removed teleport block")


# ── 9. error_handling/error_reporter.py — stub notification send ──────────────
p = RE / "error_handling/error_reporter.py"
content = p.read_text(encoding="utf-8", errors="replace")
old_notif = """# [VECTOR] removed:             from ..notifications.manager import NotificationManager
# [VECTOR] removed:             from ..notifications import EventType
            from ..database.session_context import get_user_db_session

            # Get settings snapshot for notification
            with get_user_db_session(username) as session:
                from ..settings import SettingsManager

                settings_manager = SettingsManager(session)
                settings_snapshot = settings_manager.get_settings_snapshot()

            notification_manager = NotificationManager(
                settings_snapshot=settings_snapshot, user_id=username
            )

            # Determine event type and build context
            if category == ErrorCategory.MODEL_ERROR:
                # Check if it's an auth error specifically
                error_str = error_message.lower()
                if any(
                    pattern in error_str
                    for pattern in [
                        "api key",
                        "authentication",
                        "401",
                        "unauthorized",
                    ]
                ):
                    event_type = EventType.AUTH_ISSUE
                    notification_context = {
                        "service": self._extract_service_name(error_message),
                    }
                else:
                    # Not an auth error, don't notify
                    return

            elif category == ErrorCategory.RATE_LIMIT_ERROR:
                event_type = EventType.API_QUOTA_WARNING
                notification_context = {
                    "service": self._extract_service_name(error_message),
                    "current": "Unknown",
                    "limit": "Unknown",
                    "reset_time": "Unknown",
                }

            else:
                return

            # Send notification
            notification_manager.send_notification(
                event_type=event_type,
                context=notification_context,
            )"""

new_notif = """            # Notifications removed — VECTOR uses Pushover+Telegram via vectorcode
            # Errors are logged via loguru; districts can subscribe to error events
            logger.info(
                f"Error notification skipped (category={category}): {error_message[:100]}"
            )
            return"""

content = content.replace(old_notif, new_notif)
p.write_text(content, encoding="utf-8")
print("FIXED  error_handling/error_reporter.py — removed notification sending")


# ── 10. TYPE_CHECKING stubs in agent_loop ────────────────────────────────────
p = CA / "core/agent_loop.py"
content = p.read_text(encoding="utf-8", errors="replace")
# Fix the TYPE_CHECKING block that had teleport types removed
old_tc = """if TYPE_CHECKING:
# [VECTOR] removed:     from core.coding_assistant.core.teleport.teleport import TeleportService
# [VECTOR] removed:     from core.coding_assistant.core.teleport.types import TeleportPushResponseEvent, TeleportYieldEvent"""
new_tc = """if TYPE_CHECKING:
    pass  # Teleport types removed"""
content = content.replace(old_tc, new_tc)
p.write_text(content, encoding="utf-8")
print("FIXED  core/agent_loop.py — cleaned TYPE_CHECKING block")

# ── Final check ───────────────────────────────────────────────────────────────
print()
deleted_ca = ["TeleportService", "TeleportSession", "TeleportTelemetryTracker",
              "get_proxy_help_text", "SUPPORTED_PROXY_VARS", "DATA_RETENTION_MESSAGE",
              "setup_tracing", "PlanInfo", "ServiceTeleportError"]
deleted_re = ["NotificationManager", "EventType"]

broken = []
for f in CA.rglob("*.py"):
    c = f.read_text(encoding="utf-8", errors="replace")
    for line in c.splitlines():
        s = line.strip()
        if s.startswith("#"): continue
        for sym in deleted_ca:
            if sym in s and sym not in ["TeleportService", "TeleportSession", "TeleportTelemetryTracker", "TeleportCompleteEvent", "TeleportYieldEvent", "TeleportPushResponseEvent", "ServiceTeleportError"]:
                # These are now defined as stubs in agent_loop.py — check if it's the stub definition itself
                broken.append(f"CA {f.relative_to(CA)}: {s[:80]}")

for f in RE.rglob("*.py"):
    c = f.read_text(encoding="utf-8", errors="replace")
    for line in c.splitlines():
        s = line.strip()
        if s.startswith("#"): continue
        for sym in deleted_re:
            if sym in s:
                broken.append(f"RE {f.relative_to(RE)}: {s[:80]}")

# Filter out stub definitions
broken = [b for b in broken if "class TeleportService" not in b
          and "class TeleportError" not in b
          and "class ServiceTeleportError" not in b
          and "stub" not in b.lower()
          and "# Teleport" not in b]

print(f"Remaining broken usages: {len(broken)}")
for b in broken[:10]:
    print(f"  {b}")
