"""Re-export from the real vc_agents implementation."""
from loguru import logger

try:
    from vectorcode.src.vc_agents.manager import AgentManager
except Exception as e:
    # Preserve importability for diagnostics, but fail calls explicitly rather
    # than making an unavailable manager look like a valid empty registry.
    logger.warning("[VECTOR][agents.manager] real vc_agents.manager unavailable: {}", e)
    _IMPORT_ERROR = str(e)

    class AgentManager:  # type: ignore[no-redef]
        def get_agent(self, name: str):
            raise RuntimeError(
                f"canonical vc_agents.manager is unavailable: {_IMPORT_ERROR}"
            )

        def list_agents(self) -> list:
            raise RuntimeError(
                f"canonical vc_agents.manager is unavailable: {_IMPORT_ERROR}"
            )

__all__ = ["AgentManager"]
