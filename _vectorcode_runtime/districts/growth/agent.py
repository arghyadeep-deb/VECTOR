from __future__ import annotations

import datetime

from core.city.agent_base import AgentBase
from core.config import CONFIG


class GrowthAgent(AgentBase):
    """Front door for the growth district (2026-07-30 audit fix).

    GrowthOrchestrator.run_forever() already runs for real in the background
    (started from core/loop/autonomous_loop.py, gated on
    CONFIG["growth"]["enabled"]) but had zero chat/API reachability: no
    manifest entry, and the literal string "growth" as a task_type routed to
    the *marketing* district instead, so even an owner who explicitly asked
    about "growth" by name couldn't reach it. This gives the district a real,
    honest status/reporting entry point.

    Scope note: ARM A (content_arm.py) is real and running. ARM B
    (software_arm.py) is gated behind
    GrowthOrchestrator._next_validated_issue(), which is intentionally still
    a placeholder ("wired to real scan/validate output as the loop matures",
    per its own comment) — this agent reports that honestly rather than
    claiming ARM B does something it doesn't yet do.
    """

    def __init__(self):
        super().__init__(agent_id="growth_agent", name="growth_agent", district="growth")
        self.capabilities = ["general"]

    async def run(self, task: dict) -> dict:
        self.last_active = datetime.datetime.utcnow().isoformat()
        enabled = bool(CONFIG.get("growth", {}).get("enabled", False))
        response = (
            f"Growth engine is {'enabled and running' if enabled else 'disabled'} "
            f"in the background.\n"
            f"- ARM A (content/brand, daily cadence): real — generates and reviews "
            f"content on a truthful-content-only basis, publishes only with "
            f"human-in-the-loop approval unless auto_publish is explicitly set.\n"
            f"- ARM B (software factory, 30-min poll): still a placeholder — "
            f"market-scan-to-validated-issue wiring isn't built yet, so this arm "
            f"currently never actually runs a build."
        )
        return {"status": "ok", "agent": self.name, "response": response}
