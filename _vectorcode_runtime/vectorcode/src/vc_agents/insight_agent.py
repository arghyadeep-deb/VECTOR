"""
InsightAgent — wraps vectorcode's InsightsEngine for session analytics.

Analyzes VECTOR's usage patterns: token consumption, cost estimates, tool usage,
session trends, model breakdowns. Surfaces /insights-style reports.
"""
from __future__ import annotations

import datetime


from loguru import logger


class InsightAgent:
    """
    Usage analytics and insight generation for vectorcode sessions.

    Wraps vectorcode's InsightsEngine (insights.py) with VECTOR's episodic
    memory to surface usage patterns, cost estimates, and optimization hints.
    """

    def __init__(self):
        self._engine = None
        self._episodic = None
        logger.info("[VECTOR][vc_insight] initialized")

    def _get_engine(self, db=None):
        if self._engine is None:
            try:
                from vectorcode.src.agent.insights import InsightsEngine
                self._engine = InsightsEngine(db)
            except Exception as e:
                logger.debug("[VECTOR][vc_insight] InsightsEngine unavailable: {}", e)
        return self._engine

    def _get_episodic(self):
        if self._episodic is None:
            from core.memory.episodic import EpisodicMemory
            self._episodic = EpisodicMemory()
        return self._episodic

    def generate_session_report(self, days: int = 7) -> dict:
        """Generate usage report from vectorcode's session database."""
        engine = self._get_engine()
        if engine:
            try:
                report = engine.generate(days=days)
                formatted = engine.format_terminal(report)
                logger.info("[VECTOR][vc_insight] report generated: {} days", days)
                return {"status": "ok", "report": report, "formatted": formatted, "days": days}
            except Exception as e:
                logger.warning("[VECTOR][vc_insight] engine failed: {}", e)

        # Fallback: read from VECTOR's episodic memory
        return self._episodic_insight(days)

    def _episodic_insight(self, days: int) -> dict:
        """Build insight from VECTOR's episodic memory when InsightsEngine unavailable."""
        try:
            events = self._get_episodic().recall("", limit=500)
            cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
            recent = []
            for e in events:
                ts_str = e.get("timestamp") or e.get("created_at", "")
                try:
                    ts = datetime.datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=datetime.timezone.utc)
                    if ts >= cutoff:
                        recent.append(e)
                except Exception:
                    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

            event_types: dict[str, int] = {}
            for e in recent:
                t = e.get("event_type", "unknown")
                event_types[t] = event_types.get(t, 0) + 1

            top_events = sorted(event_types.items(), key=lambda x: -x[1])[:10]
            return {
                "status": "ok",
                "days": days,
                "total_events": len(recent),
                "top_event_types": top_events,
                "source": "episodic_memory",
                "formatted": (
                    f"VECTOR Usage ({days}d): {len(recent)} events\n"
                    + "\n".join(f"  {t}: {c}" for t, c in top_events)
                ),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_optimization_hints(self) -> list[str]:
        """Return actionable hints for improving VECTOR's performance."""
        hints = []
        try:
            report = self.generate_session_report(days=7)
            events = report.get("total_events", 0)
            if events == 0:
                hints.append("No recent activity — start VECTOR's autonomous loop")
            elif events < 10:
                hints.append("Low activity — consider running more district tasks")
            top = report.get("top_event_types", [])
            if top and top[0][0] == "error":
                hints.append(f"High error rate ({top[0][1]} errors) — check logs")
        except Exception:
            logger.opt(exception=True).debug("[VECTOR] suppressed exception")
        hints.append("Run /insights for detailed session analytics")
        return hints


if __name__ == "__main__":
    agent = InsightAgent()
    report = agent.generate_session_report(days=7)
    print(f"[OK] report: status={report['status']} events={report.get('total_events', '?')}")
    hints = agent.get_optimization_hints()
    print(f"[OK] hints: {len(hints)} optimization hints")
    for h in hints:
        print(f"  - {h}")
    print("insight_agent.py OK")
