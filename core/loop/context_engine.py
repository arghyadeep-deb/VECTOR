import sys
import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG


class ContextEngine:
    """
    Builds VECTOR's world state. session_hydration_prompt() MUST be called before every LLM call.
    RULE 1 Ã¢â‚¬â€ Skip this = VECTOR has amnesia every session. Never skip.
    """

    def __init__(self):
        self._memory = None
        self._goals = None
        self._health = None
        self._screen = None
        self._obsidian = None
        self._deadline_mgr = None
        self._expense_tracker = None
        self._kiit_scraper = None
        self._comms_hub = None
        self._personality = None
        logger.info("[VECTOR][context_engine] initialized")

    def _get_memory(self):
        if self._memory is None:
            from core.memory.episodic import EpisodicMemory
            self._memory = EpisodicMemory()
        return self._memory

    def _get_goals(self):
        if self._goals is None:
            from core.brain.goal_system import GoalSystem
            self._goals = GoalSystem()
        return self._goals

    def _get_health(self):
        if self._health is None:
            try:
                from core.sensing.health_monitor import HealthMonitor
                self._health = HealthMonitor()
            except Exception: logger.debug("[VECTOR][context] exception suppressed")
        return self._health

    def _get_screen(self):
        if self._screen is None:
            try:
                from core.sensing.screen_observer import ScreenObserver
                self._screen = ScreenObserver()
            except Exception:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        return self._screen

    def _get_obsidian(self):
        if self._obsidian is None:
            try:
                from core.memory.obsidian_sync import ObsidianSync
                self._obsidian = ObsidianSync()
            except Exception as e:
                logger.warning(f"[VECTOR][context_engine] ObsidianSync init failed: {e}")
        return self._obsidian

    def _get_deadline_mgr(self):
        if self._deadline_mgr is None:
            try:
                from districts.time_calendar.deadline_manager import DeadlineManager
                self._deadline_mgr = DeadlineManager()
            except Exception:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        return self._deadline_mgr

    def _get_expense_tracker(self):
        if self._expense_tracker is None:
            try:
                from districts.finance.expense_tracker import ExpenseTracker
                self._expense_tracker = ExpenseTracker()
            except Exception:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        return self._expense_tracker

    def _get_kiit_scraper(self):
        if self._kiit_scraper is None:
            try:
                from districts.time_calendar.kiit_scraper import KIITScraper
                self._kiit_scraper = KIITScraper()
            except Exception:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        return self._kiit_scraper

    def _get_comms_hub(self):
        if self._comms_hub is None:
            try:
                from districts.communications.communications_adapter import CommunicationsAdapter as _VCCommsHub
                self._comms_hub = _VCCommsHub()
            except Exception:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
        return self._comms_hub

    def _get_personality(self):
        if self._personality is None and CONFIG.get("personality", {}).get("enabled", True):
            try:
                from core.personality import PersonalityEngine
                self._personality = PersonalityEngine()
            except Exception as e:
                logger.warning(f"[VECTOR][context_engine] PersonalityEngine init failed: {e}")
        return self._personality

    async def get_vault_context(self, query: str) -> str:
        """LightRAG hybrid query over Obsidian vault. Returns '' if not ready."""
        try:
            obs = self._get_obsidian()
            if obs is None:
                return ""
            return await obs.query(query, mode="hybrid")
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] vault context failed: {e}")
            return ""

    def get_world_state(self) -> dict:
        """Gather current world state across 14 domains."""
        now = datetime.datetime.now(datetime.timezone.utc)
        mem = self._get_memory()

        recent_episodes = []
        try:
            recent_episodes = mem.recall("", limit=5)
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] episode recall failed: {e}")

        goal_summary = ""
        try:
            goal_summary = self._get_goals().get_goal_summary()
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] goal summary failed: {e}")

        mem_stats = {}
        try:
            mem_stats = mem.get_stats()
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] mem stats failed: {e}")

        health_snapshot = {}
        try:
            h = self._get_health()
            if h:
                health_snapshot = h.get_health_snapshot()
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] health snapshot failed: {e}")

        screen_activity = "unknown"
        try:
            s = self._get_screen()
            if s:
                result = s.observe()
                screen_activity = result.get("activity", "unknown")
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] screen observe failed: {e}")

        # Ã¢â€â‚¬Ã¢â€â‚¬ Extended domain fields Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        calendar_upcoming: list = []
        try:
            dm = self._get_deadline_mgr()
            if dm and hasattr(dm, "get_upcoming_deadlines"):
                calendar_upcoming = dm.get_upcoming_deadlines(days=7) or []
            elif dm and hasattr(dm, "list_deadlines"):
                calendar_upcoming = dm.list_deadlines() or []
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] calendar fetch failed: {e}")

        finance_summary: dict = {}
        try:
            et = self._get_expense_tracker()
            if et and hasattr(et, "get_monthly_summary"):
                finance_summary = et.get_monthly_summary() or {}
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] finance fetch failed: {e}")

        academic_info: dict = {}
        try:
            ks = self._get_kiit_scraper()
            if ks:
                # Only call sync methods Ã¢â‚¬â€ get_schedule() is async and cannot be called here
                if hasattr(ks, "get_cached_schedule"):
                    academic_info = ks.get_cached_schedule() or {}
                elif hasattr(ks, "schedule_cache") and ks.schedule_cache:
                    academic_info = ks.schedule_cache
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] academic fetch failed: {e}")

        comms_status: dict = {"urgent": 0, "unread": 0, "pending": 0}
        try:
            ha = self._get_comms_hub()
            if ha:
                if hasattr(ha, "get_comms_status"):
                    comms_status = ha.get_comms_status()
                else:
                    n = ha.get_pending_count()
                    comms_status = {"urgent": 0, "unread": n, "pending": n}
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] comms fetch failed: {e}")

        personality = {}
        try:
            pe = self._get_personality()
            if pe:
                personality = {
                    "enabled": True,
                    "active_traits": dict(pe.card.traits),
                    "traits_summary": pe.card.get_traits_summary(),
                    "tone_profiles": list(pe.card.tone_mapping.keys()),
                }
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] personality data failed: {e}")

        predictions = {}
        try:
            from districts.predictive_analytics.prediction_store import PredictionStore
            ps = PredictionStore()
            predictions = {
                "recent_forecasts": len(ps.get_recent_forecasts(limit=5)),
                "active_anomalies": len(ps.get_recent_anomalies(limit=20)),
                "pending_recommendations": len(ps.get_pending_recommendations()),
                "recent_simulations": len(ps.get_recent_simulations(limit=5)),
            }
        except Exception as e:
            logger.debug(f"[VECTOR][context_engine] predictions fetch failed: {e}")

        return {
            "timestamp": now.isoformat(),
            "time_of_day": self._time_of_day(now),
            "day_of_week": now.strftime("%A"),
            "owner": CONFIG["owner_name"],
            "env": CONFIG["env"],
            "version": CONFIG["version"],
            "active_model": CONFIG["models"].get(
                CONFIG["model_router"]["conversation"], "vector-focus"
            ),
            "recent_episodes": [ep.get("content", "")[:80] for ep in recent_episodes[:3]],
            "goal_summary": goal_summary,
            "memory_stats": mem_stats,
            "loop_status": "running",
            "health": health_snapshot,
            "screen_activity": screen_activity,
            # Extended fields
            "location": CONFIG.get("location", "home"),
            "calendar": calendar_upcoming,
            "finance": finance_summary,
            "academic": academic_info,
            "comms": comms_status,
            "personality": personality,
            "predictions": predictions,
            "home_assistant": self._get_ha_snapshot(),
        }

    def _get_ha_snapshot(self) -> dict:
        if not CONFIG.get("home_assistant", {}).get("enabled", False):
            return {"enabled": False}
        try:
            from districts.home_assistant.entity_manager import EntityManager
            mgr = EntityManager()
            from districts.home_assistant.connector import HAConfig, HAConnector
            cfg = HAConfig(
                host=CONFIG["home_assistant"]["host"],
                port=CONFIG["home_assistant"]["port"],
                token=CONFIG["home_assistant"]["token"],
            )
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    asyncio.ensure_future(self._async_ha_snapshot(mgr, cfg))
                    return {"enabled": True, "status": "pending"}
            except RuntimeError:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
            return {"enabled": True}
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] HA snapshot failed: {e}")
            return {"enabled": False, "error": str(e)}

    async def _async_ha_snapshot(self, mgr, cfg):
        try:
            from districts.home_assistant.connector import HAConnector
            connector = HAConnector(cfg)
            await connector.connect()
            count = await mgr.discover(connector)
            await connector.disconnect()
            lights = [{"id": e.entity_id, "state": e.state} for e in mgr.get_by_domain("light")[:5]]
            sensors = [{"id": e.entity_id, "state": e.state} for e in mgr.get_by_domain("sensor")[:5]]
            logger.info("[VECTOR][context_engine] HA snapshot: {} entities, {} lights, {} sensors",
                        count, len(lights), len(sensors))
        except Exception as e:
            logger.warning(f"[VECTOR][context_engine] async HA snapshot failed: {e}")

    def session_hydration_prompt(self, extra_context: dict | None = None) -> str:
        """
        RULE 1 Ã¢â‚¬â€ Call this before EVERY LLM call.
        Returns a context block to prepend to the LLM message.
        """
        try:
            state = self.get_world_state()
        except Exception as e:
            logger.error(f"[VECTOR][context_engine] world state failed: {e}")
            state = {
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "owner": CONFIG["owner_name"],
                "env": CONFIG["env"],
                "version": CONFIG["version"],
                "time_of_day": "unknown",
                "day_of_week": "unknown",
                "goal_summary": "",
                "recent_episodes": [],
            }

        lines = [
            f"[SESSION CONTEXT Ã¢â‚¬â€ {state['timestamp']}]",
            f"Owner: {state['owner']} | Env: {state['env']} | VECTOR v{state['version']}",
            f"Time: {state['time_of_day']} ({state['day_of_week']})",
        ]

        if state.get("location"):
            lines.append(f"Location: {state['location']}")

        if state.get("health"):
            h = state["health"]
            lines.append(
                f"Owner health: energy={h.get('energy_level','?')} fatigue={h.get('fatigue_score','?')} "
                f"cpu={h.get('cpu_percent','?')}% ram={h.get('ram_percent','?')}%"
            )
        if state.get("screen_activity") and state["screen_activity"] != "unknown":
            lines.append(f"Current activity: {state['screen_activity']}")

        if state.get("goal_summary"):
            lines.append(f"Active goals: {state['goal_summary']}")

        if state.get("calendar"):
            lines.append(f"Upcoming deadlines: {len(state['calendar'])} in next 7 days")

        if state.get("finance"):
            spent = state["finance"].get("total_spent", state["finance"].get("total", ""))
            if spent:
                lines.append(f"Finance: monthly spend={spent}")

        if state.get("academic"):
            acad = str(state["academic"])[:80]
            if acad and acad != "{}":
                lines.append(f"Academic: {acad}")

        comms = state.get("comms", {})
        urgent = comms.get("urgent", 0)
        unread = comms.get("unread", 0)
        if urgent or unread:
            lines.append(f"Comms: {urgent} urgent, {unread} unread")

        if state.get("personality", {}).get("enabled"):
            p = state["personality"]
            lines.append(f"Personality: {p.get('traits_summary', 'active')}")
            if p.get("tone_profiles"):
                lines.append(f"Tone profiles: {', '.join(p['tone_profiles'])}")

        if state.get("recent_episodes"):
            episodes_str = " | ".join(
                e for e in state["recent_episodes"] if e
            )[:200]
            if episodes_str:
                lines.append(f"Recent context: {episodes_str}")

        if extra_context:
            for k, v in extra_context.items():
                lines.append(f"{k}: {v}")

        lines.append("[END SESSION CONTEXT]")
        raw = "\n".join(lines)

        # Ã¢â€â‚¬Ã¢â€â‚¬ TokenJuice compression Ã¢â‚¬â€ strip noise before injecting into LLM Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬
        try:
            from core.engine.token_juice.compressor import reduce_text
            compressed = reduce_text(
                raw,
                strip_boilerplate=True,
                strip_log_noise=True,
                compress_repeated_lines=True,
                max_chars=2000,
            )
            if len(compressed) < len(raw):
                logger.debug(
                    "[VECTOR][context_engine] TokenJuice: {} Ã¢â€ â€™ {} chars ({:.0f}% reduction)",
                    len(raw), len(compressed),
                    (1 - len(compressed) / len(raw)) * 100,
                )
                return compressed
        except Exception:
            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

        return raw

    def _time_of_day(self, now: datetime.datetime) -> str:
        h = now.hour
        if 5 <= h < 9:
            return "early morning"
        elif 9 <= h < 12:
            return "morning"
        elif 12 <= h < 14:
            return "midday"
        elif 14 <= h < 18:
            return "afternoon"
        elif 18 <= h < 22:
            return "evening"
        elif 22 <= h or h < 1:
            return "night"
        else:
            return "late night"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    engine = ContextEngine()
    state = engine.get_world_state()
    prompt = engine.session_hydration_prompt({"task": "smoke test"})
    comms = state.get("comms", {})
    personality = state.get("personality", {})
    ok = (
        "SESSION CONTEXT" in prompt
        and "Arghyadeep" in prompt
        and "[END SESSION CONTEXT]" in prompt
        and len(state) >= 15
        and "location" in state
        and "calendar" in state
        and "finance" in state
        and "academic" in state
        and "comms" in state
        and "urgent" in comms
        and "unread" in comms
        and "pending" in comms
        and "personality" in state
        and ("enabled" in personality or personality == {})
    )
    print(
        f"Ã¢Å“â€¦ context_engine OK Ã¢â‚¬â€ {len(state)} domains, prompt={len(prompt)} chars"
        if ok else "Ã¢ÂÅ’ FAILED"
    )
