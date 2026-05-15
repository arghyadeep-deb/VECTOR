# VECTOR-INGESTED MODULE
# Source: github/open-jarvis/OpenJarvis/src/openjarvis/agents/__init__.py
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Agents primitive — multi-turn reasoning and tool use."""

from __future__ import annotations

import logging

from vectorcode.src.oj_agents._stubs import (
    AgentContext,
    AgentResult,
    BaseAgent,
    ToolUsingAgent,
)

logger = logging.getLogger(__name__)

# Import agent modules to trigger @AgentRegistry.register() decorators
try:
    import vector.agents.simple  # noqa: F401
except ImportError:
    pass

try:
    import vector.agents.orchestrator  # noqa: F401
except ImportError:
    pass

try:
    import vector.agents.native_react  # noqa: F401
except ImportError:
    pass

try:
    import vector.agents.native_openhands  # noqa: F401
except ImportError:
    pass

try:
    import vector.agents.react  # noqa: F401 -- backward-compat shim
except ImportError:
    pass

try:
    import vector.agents.openhands  # noqa: F401
except ImportError:
    pass

try:
    import vector.agents.rlm  # noqa: F401
except ImportError:
    pass

try:
    import vector.agents.claude_code  # noqa: F401
except ImportError:
    pass

try:
    import vector.agents.operative  # noqa: F401
except ImportError:
    pass

try:
    import vector.agents.monitor  # noqa: F401
except ImportError:
    pass

try:
    import vector.agents.monitor_operative  # noqa: F401
except ImportError:
    pass

try:
    import vector.agents.deep_research  # noqa: F401
except ImportError:
    pass

try:
    import vector.agents.morning_digest  # noqa: F401
except ImportError:
    pass

# Registry alias: "react" -> NativeReActAgent (for backward compat)
try:
    from vector.core.registry import AgentRegistry

    if AgentRegistry.contains("native_react") and not AgentRegistry.contains("react"):
        AgentRegistry.register_value("react", AgentRegistry.get("native_react"))
except Exception as exc:
    logger.debug("Registry alias 'react' creation skipped: %s", exc)

__all__ = ["AgentContext", "AgentResult", "BaseAgent", "ToolUsingAgent"]
