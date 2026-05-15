# VECTOR-INGESTED MODULE
# Source: github/open-jarvis/OpenJarvis/src/openjarvis/tools/__init__.py
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Tools primitive — tool system with ABC interface and built-in tools."""

from __future__ import annotations

from vectorcode.src.oj_tools._stubs import BaseTool, ToolExecutor, ToolSpec

# Import built-in tools to trigger @ToolRegistry.register() decorators.
# Each is wrapped in try/except so the package loads even before the
# individual tool modules are created.
try:
    import vector.tools.calculator  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.think  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.retrieval  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.llm_tool  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.file_read  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.web_search  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.code_interpreter  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.code_interpreter_docker  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.repl  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.storage_tools  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.mcp_adapter  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.channel_tools  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.http_request  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.shell_exec  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.memory_manage  # noqa: F401
except ImportError:
    pass
try:
    import vector.tools.user_profile_manage  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.skill_manage  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.file_write  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.apply_patch  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.git_tool  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.db_query  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.pdf_tool  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.image_tool  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.audio_tool  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.knowledge_tools  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.text_to_speech  # noqa: F401
except ImportError:
    pass

try:
    import vector.tools.digest_collect  # noqa: F401
except ImportError:
    pass

__all__ = ["BaseTool", "ToolExecutor", "ToolSpec"]
