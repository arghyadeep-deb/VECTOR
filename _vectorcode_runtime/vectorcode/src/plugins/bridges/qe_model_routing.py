"""QE Model Routing Adapter — 3-tier model routing."""

class QEModelRoutingAdapter:
    TIERS = {"tier1": "vector-focus", "tier2": "vector-focus", "tier3": "vector-reasoning"}

    async def route(self, task: str, complexity: str = "medium") -> str:
        if complexity == "low": return self.TIERS["tier1"]
        if complexity == "high": return self.TIERS["tier3"]
        return self.TIERS["tier2"]
