from __future__ import annotations

from core.coding_assistant.core.llm.backend.generic import GenericBackend
from core.coding_assistant.core.llm.backend.mistral import MistralBackend
from core.coding_assistant.core.types import Backend

BACKEND_FACTORY = {Backend.MISTRAL: MistralBackend, Backend.GENERIC: GenericBackend}
