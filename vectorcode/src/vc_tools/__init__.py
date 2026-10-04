# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Tools primitive — tool system with ABC interface and built-in tools."""

from __future__ import annotations
from loguru import logger

from vectorcode.src.vc_tools._abc import BaseTool, ToolExecutor, ToolSpec

# Import built-in tools to trigger @ToolRegistry.register() decorators.
# Each is wrapped in try/except so the package loads even before the
# individual tool modules are created.
try:
    import vectorcode.src.vc_tools.calculator  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.think  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.retrieval  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.llm_tool  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.file_read  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.web_search  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.code_interpreter  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.code_interpreter_docker  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.repl  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.storage_tools  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.mcp_adapter  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.channel_tools  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.http_request  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.shell_exec  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.memory_manage  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")
try:
    import vectorcode.src.vc_tools.user_profile_manage  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.skill_manage  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.file_write  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.apply_patch  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.git_tool  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.db_query  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.pdf_tool  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.image_tool  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.audio_tool  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.knowledge_tools  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.text_to_speech  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

try:
    import vectorcode.src.vc_tools.digest_collect  # noqa: F401
except ImportError:
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

__all__ = ["BaseTool", "ToolExecutor", "ToolSpec"]
