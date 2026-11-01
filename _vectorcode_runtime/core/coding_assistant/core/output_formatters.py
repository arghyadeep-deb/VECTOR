from __future__ import annotations

__all__ = [
    "create_formatter",
    "JsonOutputFormatter",
    "OutputFormatter",
    "StreamingJsonOutputFormatter",
    "TextOutputFormatter",
]


from abc import ABC, abstractmethod
import json
import sys
from typing import TextIO

# [VECTOR] removed: from core.coding_assistant.core.teleport.types import (
# [VECTOR] removed:     TeleportAuthCompleteEvent,
# [VECTOR] removed:     TeleportAuthRequiredEvent,
# [VECTOR] removed:     TeleportCheckingGitEvent,
# [VECTOR] removed:     TeleportCompleteEvent,
# [VECTOR] removed:     TeleportFetchingUrlEvent,
# [VECTOR] removed:     TeleportPushingEvent,
# [VECTOR] removed:     TeleportPushRequiredEvent,
# [VECTOR] removed:     TeleportStartingWorkflowEvent,
# [VECTOR] removed:     TeleportWaitingForGitHubEvent,
# [VECTOR] removed: )
from core.coding_assistant.core.types import AssistantEvent, BaseEvent, LLMMessage, OutputFormat
from loguru import logger


class OutputFormatter(ABC):
    def __init__(self, stream: TextIO = sys.stdout) -> None:
        self.stream = stream
        self._messages: list[LLMMessage] = []
        self._final_response: str | None = None

    @abstractmethod
    def on_message_added(self, message: LLMMessage) -> None:
        raise NotImplementedError("OutputFormatter.on_message_added must be implemented by subclass")

    @abstractmethod
    def on_event(self, event: BaseEvent) -> None:
        raise NotImplementedError("OutputFormatter.on_event must be implemented by subclass")

    @abstractmethod
    def finalize(self) -> str | None:
        """Finalize output and return any final text to be printed.

        Returns:
            String to print, or None if formatter handles its own output
        """
        raise NotImplementedError("OutputFormatter.finalize must be implemented by subclass")


class TextOutputFormatter(OutputFormatter):
    def on_message_added(self, message: LLMMessage) -> None:
        self._messages.append(message)

    def _print(self, text: str) -> None:
        logger.info(text, file=self.stream)


    def on_event(self, event: BaseEvent) -> None:
        match event:
            case AssistantEvent():
                self._final_response = event.content
            case _:
                pass  # Teleport events removed

    def finalize(self) -> str | None:
        return self._final_response


class JsonOutputFormatter(OutputFormatter):
    def on_message_added(self, message: LLMMessage) -> None:
        self._messages.append(message)

    def on_event(self, event: BaseEvent) -> None:
        raise NotImplementedError("JsonOutputFormatter.on_event must be implemented by subclass")

    def finalize(self) -> str | None:
        messages_data = [msg.model_dump(mode="json") for msg in self._messages]
        json.dump(messages_data, self.stream, indent=2, ensure_ascii=False)
        self.stream.write("\n")
        self.stream.flush()
        return None


class StreamingJsonOutputFormatter(OutputFormatter):
    def on_message_added(self, message: LLMMessage) -> None:
        json.dump(message.model_dump(mode="json"), self.stream, ensure_ascii=False)
        self.stream.write("\n")
        self.stream.flush()

    def on_event(self, event: BaseEvent) -> None:
        raise NotImplementedError("StreamingJsonOutputFormatter.on_event must be implemented by subclass")

    def finalize(self) -> str | None:
        return None


def create_formatter(
    format_type: OutputFormat, stream: TextIO = sys.stdout
) -> OutputFormatter:
    formatters = {
        OutputFormat.TEXT: TextOutputFormatter,
        OutputFormat.JSON: JsonOutputFormatter,
        OutputFormat.STREAMING: StreamingJsonOutputFormatter,
    }

    formatter_class = formatters.get(format_type, TextOutputFormatter)
    return formatter_class(stream)
