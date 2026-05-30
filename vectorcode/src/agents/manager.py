"""Re-export from the real vc_agents implementation."""
try:
    from vectorcode.src.vc_agents.manager import AgentManager
except Exception:
    class AgentManager:  # type: ignore[no-redef]
        def get_agent(self, name: str):
            return None

        def list_agents(self) -> list:
            return []

__all__ = ["AgentManager"]
