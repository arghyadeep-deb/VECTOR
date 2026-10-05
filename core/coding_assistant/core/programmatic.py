from __future__ import annotations

import asyncio
from contextlib import aclosing

from core.coding_assistant import __version__
from core.coding_assistant.core.agent_loop import AgentLoop
from core.coding_assistant.core.agents.models import BuiltinAgentName
from core.coding_assistant.core.config import VectorCAConfig
from core.coding_assistant.core.hooks.models import HookConfigResult
from core.coding_assistant.core.logger import logger
from core.coding_assistant.core.output_formatters import create_formatter
# Telemetry removed — stubs
def build_entrypoint_metadata(*args, **kwargs) -> dict:  # type: ignore[misc]
    return {}

class ClientMetadata:  # stub -- telemetry removed, fields intentionally unused
    def __init__(self, name: str = "", version: str = ""):
        pass
# [VECTOR] removed: from core.coding_assistant.core.teleport.types import (
# [VECTOR] removed:     TeleportPushRequiredEvent,
# [VECTOR] removed:     TeleportPushResponseEvent,
# [VECTOR] removed: )
from core.coding_assistant.core.types import AssistantEvent, LLMMessage, OutputFormat, Role
from core.coding_assistant.core.utils import ConversationLimitException

__all__ = ["run_programmatic"]

_DEFAULT_CLIENT_METADATA = ClientMetadata(name="vibe_programmatic", version=__version__)


def run_programmatic(  # noqa: PLR0913, PLR0917
    config: VectorCAConfig,
    prompt: str,
    max_turns: int | None = None,
    max_price: float | None = None,
    output_format: OutputFormat = OutputFormat.TEXT,
    previous_messages: list[LLMMessage] | None = None,
    agent_name: str = BuiltinAgentName.AUTO_APPROVE,
    client_metadata: ClientMetadata = _DEFAULT_CLIENT_METADATA,
    headless: bool = False,
    hook_config_result: HookConfigResult | None = None,
) -> str | None:
    formatter = create_formatter(output_format)

    agent_loop = AgentLoop(
        config,
        agent_name=agent_name,
        message_observer=formatter.on_message_added,
        max_turns=max_turns,
        max_price=max_price,
        enable_streaming=False,
        headless=headless,
        entrypoint_metadata=build_entrypoint_metadata(
            agent_entrypoint="programmatic",
            agent_version=__version__,
            client_name=client_metadata.name,
            client_version=client_metadata.version,
        ),
        hook_config_result=hook_config_result,
    )
    logger.info("USER: %s", prompt)

    async def _async_run() -> str | None:
        try:
            if previous_messages:
                non_system_messages = [
                    msg for msg in previous_messages if not (msg.role == Role.system)
                ]
                agent_loop.messages.extend(non_system_messages)
                logger.info(
                    "Loaded %d messages from previous session", len(non_system_messages)
                )
            else:
                agent_loop.emit_new_session_telemetry()

            # Teleport removed — always run local agent loop
            if True:
                async with aclosing(agent_loop.act(prompt)) as events:
                    async for event in events:
                        formatter.on_event(event)
                        if (
                            isinstance(event, AssistantEvent)
                            and event.stopped_by_middleware
                        ):
                            raise ConversationLimitException(event.content)

            return formatter.finalize()
        finally:
            agent_loop.emit_session_closed_telemetry()
            await agent_loop.aclose()
            await agent_loop.telemetry_client.aclose()

    return asyncio.run(_async_run())
