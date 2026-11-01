"""CRUD operations for V.E.C.T.O.R. API."""

import sys

__all__ = [
    "award_agent",
    "get_agent",
    "get_agents",
    "get_goals",
    "get_immediate_actions",
    "get_memory_stats",
    "get_policy_score",
    "get_training_data",
    "recall_episodes",
    "store_episode",
    "store_reasoning_chain",
    "update_policy",
]


from loguru import logger
from typing import List, Dict, Any, Optional

def get_memory_stats() -> Dict[str, Any]:
    """Get memory statistics."""
    try:
        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        return mem.get_stats()
    except Exception as e:
        logger.error(f"[VECTOR][api] get_memory_stats failed: {e}")
        return {"error": str(e)}

def recall_episodes(query: str, limit: int = 10, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Recall episodes from memory."""
    try:
        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        return mem.recall(query, limit=limit, event_type=event_type)
    except Exception as e:
        logger.error(f"[VECTOR][api] recall_episodes failed: {e}")
        return []

def store_episode(event_type: str, content: str, tags: Optional[List[str]] = None,
                  context: Optional[Dict[str, Any]] = None, source: str = "api") -> str:
    """Store an episode in memory."""
    try:
        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        return mem.store(event_type, content, tags=tags, context=context, source=source)
    except Exception as e:
        logger.error(f"[VECTOR][api] store_episode failed: {e}")
        return ""

def get_policy_score(action_type: str, situation_hash: str) -> float:
    """Get policy score for an action."""
    try:
        from core.memory.policy import PolicyMemory
        pm = PolicyMemory()
        return pm.get_score(action_type, situation_hash)
    except Exception as e:
        logger.error(f"[VECTOR][api] get_policy_score failed: {e}")
        return 0.5

def update_policy(action_type: str, situation_hash: str, reward: float) -> None:
    """Update policy memory."""
    try:
        from core.memory.policy import PolicyMemory
        pm = PolicyMemory()
        pm.update_from_outcome(action_type, situation_hash, reward)
    except Exception as e:
        logger.error(f"[VECTOR][api] update_policy failed: {e}")

def store_reasoning_chain(situation: str, goal_ids: List[str], steps: List[str],
                          action: str, outcome: str, reward: float) -> str:
    """Store a reasoning chain."""
    try:
        from core.memory.reasoning_memory import ReasoningMemory
        rm = ReasoningMemory()
        return rm.store_chain(situation, goal_ids, steps, action, outcome, reward)
    except Exception as e:
        logger.error(f"[VECTOR][api] store_reasoning_chain failed: {e}")
        return ""

def get_training_data(limit: int = 100) -> List[Dict[str, Any]]:
    """Get training data from reasoning chains."""
    try:
        from core.memory.reasoning_memory import ReasoningMemory
        rm = ReasoningMemory()
        return rm.get_training_data(limit=limit)
    except Exception as e:
        logger.error(f"[VECTOR][api] get_training_data failed: {e}")
        return []

def get_agents() -> List[Dict[str, Any]]:
    """Get all agents from registry."""
    try:
        from core.city.agent_registry import get_registry
        reg = get_registry()
        return reg.list_all()
    except Exception as e:
        logger.error(f"[VECTOR][api] get_agents failed: {e}")
        return []

def get_agent(agent_id: str) -> Optional[Dict[str, Any]]:
    """Get a specific agent."""
    try:
        from core.city.agent_registry import get_registry
        reg = get_registry()
        agent = reg.get(agent_id)
        if agent and hasattr(agent, "to_dict"):
            return agent.to_dict()
        return None
    except Exception as e:
        logger.error(f"[VECTOR][api] get_agent failed: {e}")
        return None

def award_agent(agent_id: str, points: int, reason: str) -> Dict[str, Any]:
    """Award points to an agent."""
    try:
        from core.city.agent_registry import get_registry
        reg = get_registry()
        agent = reg.get(agent_id)
        if not agent:
            return {"status": "not_found", "error": f"Agent {agent_id} not found"}
        result = agent.award_points(points, reason)
        return {"status": "ok", "agent": agent.to_dict(), "award": result}
    except Exception as e:
        logger.error(f"[VECTOR][api] award_agent failed: {e}")
        return {"status": "error", "error": str(e)}

def get_goals() -> List[Dict[str, Any]]:
    """Get current goals."""
    try:
        from core.brain.goal_system import GoalSystem
        gs = GoalSystem()
        return gs.get_active_goals()
    except Exception as e:
        logger.error(f"[VECTOR][api] get_goals failed: {e}")
        return []

def get_immediate_actions(limit: int = 5) -> List[Dict[str, Any]]:
    """Get immediate actions from goal system."""
    try:
        from core.brain.goal_system import GoalSystem
        gs = GoalSystem()
        return gs.generate_immediate_actions(limit=limit)
    except Exception as e:
        logger.error(f"[VECTOR][api] get_immediate_actions failed: {e}")
        return []

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("✅ crud.py OK")
