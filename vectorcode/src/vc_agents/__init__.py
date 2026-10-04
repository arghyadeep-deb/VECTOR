# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Agents primitive — multi-turn reasoning and tool use."""

from __future__ import annotations

from loguru import logger

from vectorcode.src.vc_agents._abc import (
    AgentContext,
    AgentResult,
    BaseAgent,
    ToolUsingAgent,
)

# Import agent modules to trigger @AgentRegistry.register() decorators
try:
    import vectorcode.src.vc_agents.simple  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_agents.orchestrator  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_agents.native_react  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_agents.native_openhands  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_agents.react  # noqa: F401 -- backward-compat shim
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_agents.openhands  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_agents.rlm  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_agents.claude_code  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_agents.operative  # noqa: F401
except ImportError:
    logger.opt(exception=True).warning("optional dep import failed")
# NOTE (2026-07-19): vc_agents.monitor does not exist in this codebase (only
# monitor_operative.py). The old WARNING-with-traceback spammed every startup
# with a scary ModuleNotFoundError; downgraded to debug like the other
# optional imports above.
try:
    import vectorcode.src.vc_agents.monitor  # noqa: F401
except ImportError:
    logger.debug("[VECTOR] optional vc_agents.monitor not present")
try:
    import vectorcode.src.vc_agents.monitor_operative  # noqa: F401
except ImportError:
    logger.opt(exception=True).warning("optional dep import failed")
try:
    import vectorcode.src.vc_agents.deep_research  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_agents.morning_digest  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

# Registry alias: "react" -> NativeReActAgent (for backward compat)
try:
    from vectorcode.src.vc_core.registry import AgentRegistry

    if AgentRegistry.contains("native_react") and not AgentRegistry.contains("react"):
        AgentRegistry.register_value("react", AgentRegistry.get("native_react"))
except Exception as exc:
    logger.debug("Registry alias 'react' creation skipped: {}", exc)

__all__ = ["AgentContext", "AgentResult", "BaseAgent", "ToolUsingAgent"]
