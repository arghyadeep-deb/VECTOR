"""
V.E.C.T.O.R. EvolutionEngine.
Handles agent evolution across generations — dead agents spawn improved successors.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger
from datetime import datetime
from core.config import CONFIG


class EvolutionEngine:
    """
    Evolves agents across generations based on performance data.
    Dead agents (HP=0) spawn improved successors with inherited ghost memory.
    RULE 11: all evolution via Ollama (no external API at runtime).
    """

    def __init__(self):
        self._generations: dict[str, int] = {}
        self._evolution_log: list[dict] = []
        logger.info("[VECTOR][evolution] EvolutionEngine initialized")

    def spawn_successor(self, dead_agent: dict) -> dict:
        """
        Create an improved successor from a dead agent's ghost.
        Increases generation, preserves lessons, improves HP.
        """
        agent_name = dead_agent.get("name", "Unknown")
        prev_gen = dead_agent.get("generation", 1)
        lessons = dead_agent.get("lessons_learned", [])
        decisions = dead_agent.get("best_decisions", [])
        traits = dead_agent.get("personality_traits", {})

        new_gen = prev_gen + 1
        if agent_name in self._generations:
            self._generations[agent_name] = max(self._generations[agent_name], new_gen)
        else:
            self._generations[agent_name] = new_gen

        successor = {
            "name": agent_name,
            "generation": new_gen,
            "starting_hp": min(500 + (new_gen * 50), 800),
            "lessons_inherited": len(lessons),
            "decisions_inherited": len(decisions),
            "personality_traits": traits,
            "spawned_at": datetime.utcnow().isoformat(),
            "death_reason": dead_agent.get("died_at", "unknown"),
        }
        self._evolution_log.append(successor)
        logger.info(f"[VECTOR][evolution] {agent_name} gen{prev_gen} died -> gen{new_gen} spawned (HP={successor['starting_hp']})")
        return successor

    def get_evolution_stats(self, agent_name: str) -> dict:
        """Get evolution statistics for an agent."""
        generations = [e for e in self._evolution_log if e["name"] == agent_name]
        return {
            "total_generations": len(generations),
            "current_gen": generations[-1]["generation"] if generations else 1,
            "total_deaths": len(generations),
            "lessons_preserved": sum(e["lessons_inherited"] for e in generations),
        }

    def get_best_practices(self, agent_name: str) -> list[str]:
        """Extract best practices from all generations of an agent."""
        practices = []
        for e in self._evolution_log:
            if e["name"] == agent_name:
                for d in e.get("decisions", []):
                    if d.get("reward", 0) > 0.8:
                        practices.append(d.get("description", ""))
        return list(set(practices))


if __name__ == "__main__":
    ee = EvolutionEngine()
    ghost = {"name": "BugHunter", "generation": 2, "lessons_learned": ["check edge cases", "test boundary"], "best_decisions": []}
    print(ee.spawn_successor(ghost))
    print(ee.get_evolution_stats("BugHunter"))