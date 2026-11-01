import sys
import uuid
import json
import asyncio
import datetime

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory, get_temp_cursor

_FOCUS = CONFIG["models"]["focus"]

# Arghyadeep's core goal areas — used to personalise nudges
_GOAL_AREAS = [
    "KIIT attendance and academics",
    "VECTOR autonomous AI system build",
    "Karpathy 30-minute daily deep-learning track",
    "placement preparation (DSA, system design, ML)",
    "physical health and consistent sleep",
]

# Hours defined as waking blocks for procrastination detection
_WAKING_START = 7    # 07:00
_WAKING_END   = 24   # up to midnight

# No activity for this many minutes during waking hours = possible procrastination
_IDLE_THRESHOLD_MINUTES = 120


class BehavioralNudgeEngine(AgentBase):
    """
    Adapts VECTOR's interaction style to maximise Arghyadeep's motivation.
    Detects procrastination from episodic activity gaps, generates personalised
    nudges via local LLM, and logs every motivational event.
    Runs on VECTOR's main tick — gently nudges without interrupting flow.
    RULE 11: local models only — never Claude API at runtime.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="BehavioralNudgeEngine",
            district="personal_growth",
            generation=generation,
        )
        self.capabilities = ["behavior", "high", "nudge", "personal_growth"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._last_nudge_time: datetime.datetime | None = None
        self._last_nudge_source = ""
        # Minimum gap between nudges (avoid spamming)
        self._nudge_cooldown_minutes = 45
        logger.info(f"[VECTOR][behavioral_nudge_engine] ready gen={generation}")

    # ── Time context ──────────────────────────────────────────────────────────────

    def get_time_context(self) -> dict:
        """
        Map current local hour to an energy level and session type.
        Returns a dict with: hour, energy_level, session_type, greeting_tone.
        """
        now = datetime.datetime.now()
        hour = now.hour

        if 5 <= hour < 9:
            energy = "high"
            session = "morning_focus"
            tone = "crisp and energising"
        elif 9 <= hour < 13:
            energy = "high"
            session = "deep_work"
            tone = "direct and motivating"
        elif 13 <= hour < 16:
            energy = "medium"
            session = "afternoon_grind"
            tone = "practical and steady"
        elif 16 <= hour < 20:
            energy = "medium"
            session = "evening_push"
            tone = "encouraging and focused"
        elif 20 <= hour < 24:
            energy = "creative"
            session = "night_creative"
            tone = "thoughtful and curious"
        else:  # midnight–5
            energy = "low"
            session = "late_night"
            tone = "gentle and brief"

        return {
            "hour": hour,
            "datetime": now.isoformat(),
            "energy_level": energy,
            "session_type": session,
            "greeting_tone": tone,
        }

    # ── Activity analysis ─────────────────────────────────────────────────────────

    def analyze_recent_activity(self, hours: int = 24) -> dict:
        """
        Fetch last N hours of episodic events and summarise:
        - What was accomplished (event types and count)
        - Any mood signals from tags
        - Last activity timestamp
        """
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=hours)
        ).isoformat()

        try:
            with get_temp_cursor() as cur:
                cur.execute(
                    "SELECT event_type, tags, timestamp FROM episodic_memory "
                    "WHERE timestamp > ? ORDER BY timestamp DESC",
                    (cutoff,),
                )
                rows = cur.fetchall()
        except Exception as e:
            logger.warning(
                f"[VECTOR][behavioral_nudge_engine] analyze_recent_activity failed: {e}"
            )
            return {"events": [], "last_timestamp": None, "mood_signals": [], "error": str(e)}

        events = []
        mood_signals = []
        last_ts: str | None = None

        for row in rows:
            event_type = row[0]
            # row = (event_type, tags, timestamp)
            tags = []
            try:
                tags = json.loads(row[1]) if row[1] else []
            except Exception as exc:
                logger.debug("[VECTOR][behavioral_nudge_engine] bad tags json: {}", exc)
            ts = row[2]
            if last_ts is None:
                last_ts = ts
            events.append({"event_type": event_type, "tags": tags, "timestamp": ts})

            # Mood inference from tags
            mood_words = {"fatigue", "tired", "stressed", "blocked", "failed", "error"}
            positive_words = {"completed", "success", "shipped", "learned", "karpathy"}
            for tag in tags:
                if isinstance(tag, str):
                    if any(m in tag.lower() for m in mood_words):
                        mood_signals.append("negative")
                    if any(p in tag.lower() for p in positive_words):
                        mood_signals.append("positive")

        # Summarise event types
        type_counts: dict[str, int] = {}
        for ev in events:
            type_counts[ev["event_type"]] = type_counts.get(ev["event_type"], 0) + 1

        coding_count = type_counts.get("code_committed", 0) + type_counts.get("git_commit", 0)
        learning_count = type_counts.get("karpathy_session", 0) + type_counts.get("learning", 0)

        return {
            "total_events": len(events),
            "type_counts": type_counts,
            "coding_activity": coding_count,
            "learning_activity": learning_count,
            "mood_signals": mood_signals,
            "last_timestamp": last_ts,
        }

    # ── Procrastination detection ─────────────────────────────────────────────────

    def detect_procrastination_pattern(self) -> dict:
        """
        If no coding or learning activity for >IDLE_THRESHOLD_MINUTES during
        waking hours, flag as possible procrastination.
        Returns: {detected: bool, idle_minutes: float, reason: str}
        """
        now = datetime.datetime.now()
        hour = now.hour

        # Outside waking hours — don't flag
        if not (_WAKING_START <= hour < _WAKING_END):
            return {"detected": False, "idle_minutes": 0.0, "reason": "outside_waking_hours"}

        try:
            with get_temp_cursor() as cur:
                cur.execute(
                    "SELECT timestamp FROM episodic_memory "
                    "WHERE event_type IN ('code_committed','git_commit','karpathy_session','learning','task_completed') "
                    "ORDER BY timestamp DESC LIMIT 1"
                )
                row = cur.fetchone()
        except Exception as e:
            logger.warning(
                f"[VECTOR][behavioral_nudge_engine] procrastination query failed: {e}"
            )
            return {"detected": False, "idle_minutes": 0.0, "reason": f"query_error: {e}"}

        if row is None:
            return {
                "detected": True,
                "idle_minutes": float(_IDLE_THRESHOLD_MINUTES + 1),
                "reason": "no_productive_events_ever",
            }

        try:
            last_dt = datetime.datetime.fromisoformat(row[0])
            # Make both timezone-aware for comparison
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=datetime.timezone.utc)
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            idle_minutes = (now_utc - last_dt).total_seconds() / 60
        except Exception as e:
            logger.warning(
                f"[VECTOR][behavioral_nudge_engine] timestamp parse failed: {e}"
            )
            return {"detected": False, "idle_minutes": 0.0, "reason": f"parse_error: {e}"}

        if idle_minutes >= _IDLE_THRESHOLD_MINUTES:
            return {
                "detected": True,
                "idle_minutes": round(idle_minutes, 1),
                "reason": f"no_productive_activity_for_{idle_minutes:.0f}min",
            }

        return {"detected": False, "idle_minutes": round(idle_minutes, 1), "reason": "active"}

    # ── Nudge generation ──────────────────────────────────────────────────────────

    def generate_nudge(self, context: dict) -> str:
        """
        Use ollama_safe to produce a personalised, goal-aware nudge.
        Falls back to a canned context-sensitive message on LLM failure.
        """
        energy = context.get("energy_level", "medium")
        session = context.get("session_type", "work")
        tone = context.get("greeting_tone", "direct")
        idle_min = context.get("idle_minutes", 0)
        procrastinating = context.get("procrastination_detected", False)

        try:
            from core.inference.vectorcode_llm import chat
            from core.loop.context_engine import ContextEngine

            hydration = ContextEngine().session_hydration_prompt()
            proc_note = (
                f"Arghyadeep hasn't done any coding or learning in {idle_min:.0f} minutes."
                if procrastinating
                else "Arghyadeep is currently active."
            )
            goals_str = "\n".join(f"  - {g}" for g in _GOAL_AREAS)
            prompt = (
                f"You are VECTOR, Arghyadeep's AI system. Generate one short, specific, "
                f"motivational nudge (2-3 sentences max). Tone: {tone}. "
                f"Session type: {session}. Energy level: {energy}.\n"
                f"{proc_note}\n"
                f"His goals:\n{goals_str}\n\n"
                f"Be blunt and personal — no generic motivational fluff. "
                f"Reference a specific goal if relevant. Never start with 'Certainly!'."
            )
            from core.prompt_library import get_library as _gl
            _sys = _gl().get_for_agent("behavioral_nudge_engine") or hydration
            response = chat(
                model=_FOCUS,
                messages=[
                    {"role": "system", "content": _sys},
                    {"role": "user", "content": prompt},
                ],
                timeout=30.0,
            )
            if response and response.strip():
                self._last_nudge_source = "llm"
                return response.strip()
        except Exception as e:
            logger.warning(
                f"[VECTOR][behavioral_nudge_engine] LLM nudge failed, using fallback: {e}"
            )

        self._last_nudge_source = "fallback"
        # Fallback nudge mapping
        fallbacks = {
            "high": "Time to grind. Pick one VECTOR district and ship something before lunch.",
            "medium": "Keep the momentum going. 25 minutes of focused work beats 2 hours of browsing.",
            "creative": "Night sessions are gold for deep thinking. What's one thing you want to understand better?",
            "low": "Rest is work too. If you're pushing through exhaustion, the output quality will suffer.",
        }
        return fallbacks.get(energy, "Stay focused. One task at a time.")

    # ── Style adapter ─────────────────────────────────────────────────────────────

    def adapt_response_style(self, energy_level: str) -> dict:
        """
        Return a style hint dict that downstream VECTOR components can use
        when generating responses during this session.
        """
        styles = {
            "high": {
                "verbosity": "terse",
                "tone": "energetic",
                "emoji_ok": False,
                "use_bullet_points": True,
            },
            "medium": {
                "verbosity": "normal",
                "tone": "steady",
                "emoji_ok": False,
                "use_bullet_points": True,
            },
            "creative": {
                "verbosity": "expanded",
                "tone": "thoughtful",
                "emoji_ok": False,
                "use_bullet_points": False,
            },
            "low": {
                "verbosity": "minimal",
                "tone": "gentle",
                "emoji_ok": False,
                "use_bullet_points": False,
            },
        }
        return styles.get(energy_level, styles["medium"])

    # ── Event logging ─────────────────────────────────────────────────────────────

    def log_motivation_event(self, event_type: str, details: str) -> str:
        """Store a motivation-tagged event in episodic memory."""
        event_id = self._memory.store(
            event_type=event_type,
            content=details,
            tags=["motivation", "personal_growth", event_type],
            source="behavioral_nudge_engine",
        )
        logger.debug(
            f"[VECTOR][behavioral_nudge_engine] logged motivation event: {event_type}"
        )
        return event_id

    # ── Main tick ─────────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        """
        Detect context, check procrastination, generate nudge if warranted,
        store in memory. Respects cooldown to avoid spamming.
        """
        self.last_active = datetime.datetime.now(datetime.timezone.utc).isoformat()

        try:
            time_ctx = self.get_time_context()
            activity = self.analyze_recent_activity(hours=24)
            proc = self.detect_procrastination_pattern()

            detect_err = str(proc.get("reason", ""))
            if detect_err.startswith(("query_error", "parse_error")) or activity.get("error"):
                # Cannot tell idle from active when the activity store is unreadable.
                logger.error("[VECTOR][behavioral_nudge_engine] activity unreadable: {}", detect_err or activity.get("error"))
                return {
                    "status": "error",
                    "error": f"activity unreadable: {detect_err or activity.get('error')}",
                    "nudge_sent": False,
                    "hp": self.health_points,
                }

            context = {
                **time_ctx,
                "procrastination_detected": proc["detected"],
                "idle_minutes": proc["idle_minutes"],
                "recent_coding": activity.get("coding_activity", 0),
                "recent_learning": activity.get("learning_activity", 0),
                "mood_signals": activity.get("mood_signals", []),
            }

            # Respect cooldown
            now = datetime.datetime.now(datetime.timezone.utc)
            cooldown_ok = (
                self._last_nudge_time is None
                or (now - self._last_nudge_time).total_seconds()
                >= self._nudge_cooldown_minutes * 60
            )

            nudge_sent = False
            nudge_text = ""
            style_hints = self.adapt_response_style(time_ctx["energy_level"])

            if proc["detected"] and cooldown_ok:
                nudge_text = self.generate_nudge(context)
                logger.info(
                    f"[VECTOR][behavioral_nudge_engine] nudge: {nudge_text[:80]}"
                )
                self.log_motivation_event(
                    "nudge_sent",
                    f"idle={proc['idle_minutes']}min | energy={time_ctx['energy_level']} | {nudge_text[:100]}",
                )
                self._last_nudge_time = now
                nudge_sent = True
                self.award_points(5, "nudge dispatched")
            else:
                reason = (
                    "cooldown"
                    if not cooldown_ok
                    else f"active (idle={proc['idle_minutes']}min)"
                )
                logger.debug(
                    f"[VECTOR][behavioral_nudge_engine] no nudge needed — {reason}"
                )

            return {
                "status": "ok",
                "energy_level": time_ctx["energy_level"],
                "session_type": time_ctx["session_type"],
                "procrastination_detected": proc["detected"],
                "idle_minutes": proc["idle_minutes"],
                "nudge_sent": nudge_sent,
                "nudge_text": nudge_text,
                "nudge_source": self._last_nudge_source if nudge_sent else "",
                "style_hints": style_hints,
                "hp": self.health_points,
            }

        except Exception as e:
            logger.error(
                f"[VECTOR][behavioral_nudge_engine] run failed: {e}"
            )
            self.deduct_points(10, f"run exception: {e}")
            return {"status": "error", "error": str(e), "hp": self.health_points}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = BehavioralNudgeEngine()
        assert agent.health_points == 500

        time_ctx = agent.get_time_context()
        assert "energy_level" in time_ctx
        assert time_ctx["energy_level"] in ("high", "medium", "creative", "low")

        activity = agent.analyze_recent_activity(hours=24)
        assert "total_events" in activity

        proc = agent.detect_procrastination_pattern()
        assert "detected" in proc
        assert isinstance(proc["detected"], bool)

        style = agent.adapt_response_style(time_ctx["energy_level"])
        assert "verbosity" in style

        event_id = agent.log_motivation_event("smoke_test", "behavioral nudge engine OK")
        assert isinstance(event_id, str)

        result = await agent.run({"type": "nudge_check"})
        assert result["status"] == "ok"
        print(
            f"OK behavioral_nudge_engine.py HP={agent.health_points} "
            f"energy={time_ctx['energy_level']} procrastination={proc['detected']}"
        )

    asyncio.run(_smoke())
