# DORMANT (2026-09-24, docs/design/core-module-triage.md): not imported by the running VECTOR.
# Superseded by Governor routing (core/city/governor.py). Kept on purpose (personal-use build); do not add a second live path --
# route through the existing mechanism so the Governor and PermissionGateway stay the only way in.
"""
V.E.C.T.O.R. BrainRouter.
Routes cognitive requests to the appropriate brain sub-system.
"""
from loguru import logger


class BrainRouter:
    """
    Routes incoming thoughts/requests to the right brain subsystem:
    - decision: DecisionEngine
    - council: LLM council deliberation
    - planning: GoalSystem
    - memory: Semantic/Episodic memory
    - evolution: EvolutionEngine
    """

    ROUTES = {
        "deliberate": "council",
        "decide": "decision",
        "plan": "planning",
        "remember": "memory",
        "learn": "evolution",
        "reflect": "synthesis",
        "analyze": "hypothesis",
        "audit": "epistemic",
        "challenge": "red_team",
    }

    def __init__(self):
        logger.info("[VECTOR][brain_router] BrainRouter initialized")

    def route(self, intent: str) -> str:
        """Return the brain subsystem for a given intent."""
        intent_lower = intent.lower()
        for keyword, subsystem in self.ROUTES.items():
            if keyword in intent_lower:
                logger.info(f"[VECTOR][brain_router] '{intent}' -> {subsystem}")
                return subsystem
        logger.info(f"[VECTOR][brain_router] '{intent}' -> decision (default)")
        return "decision"

    def route_action(self, action_type: str) -> str:
        """Map an action_type to its originating brain subsystem."""
        action_map = {
            "governance": "council",
            "code": "decision",
            "search_web": "memory",
            "reflect": "synthesis",
            "plan": "planning",
            "evolve": "evolution",
        }
        for key, val in action_map.items():
            if key in action_type.lower():
                return val
        return "decision"


if __name__ == "__main__":
    br = BrainRouter()
    print(br.route("I need to deliberate on deploying a new agent"))
    print(br.route("Help me plan my next week"))
    print(br.route("Remember what I was working on yesterday"))