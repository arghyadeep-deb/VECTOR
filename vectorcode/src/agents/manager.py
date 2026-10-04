"""Re-export from the real vc_agents implementation."""
from loguru import logger

try:
    from vectorcode.src.vc_agents.manager import AgentManager
except Exception as e:
    # Falls back to a stub that always returns None/[] with zero
    # indication anything went wrong -- same silent-swallow bug class
    # fixed 60+ times this cycle. Zero real callers today (confirmed via
    # repo-wide grep), fixed anyway per this cycle's established bar.
    logger.warning("[VECTOR][agents.manager] real vc_agents.manager unavailable, using empty stub: {}", e)

    class AgentManager:  # type: ignore[no-redef]
        def get_agent(self, name: str):
            return None

        def list_agents(self) -> list:
            return []

__all__ = ["AgentManager"]
