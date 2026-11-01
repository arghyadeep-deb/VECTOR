"""
AvatarCore — the single unified face VECTOR presents to its owner.
Implements the observe/think/act/reflect lifecycle spec §1.2.

Integration:
  - governor.py ~L893: route result through AvatarCore.on_act()
  - autonomous_loop.py run_forever(): instantiate once, call hooks
  - _reflect_tick(): call on_reflect() to advance relationship state

Reuse policy (never duplicate):
  - Stress/fatigue → core/sensing/health_monitor.py + districts/health/fatigue_monitor.py
  - Relationship/trust → core/brain/person_model.py (NOT a new store)
  - Causal → core/memory/causal_graph.py (already wired in decision_engine)
"""

import asyncio
from typing import Any

from loguru import logger
from core.config import CONFIG
from core.avatar.avatar_state import AvatarState
from core.avatar.avatar_voice import AvatarVoice


class AvatarCore:
    """
    Keystone of the Avatar layer. Singleton-friendly (instantiate once in loop).
    All four lifecycle hooks are fire-and-forget safe — never raise.
    """

    _instance: "AvatarCore | None" = None

    @classmethod
    def get_instance(cls) -> "AvatarCore":
        """Return the shared singleton, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._state = AvatarState.load()
        self._voice = AvatarVoice()
        self._person_model = None
        self._health_monitor = None
        self._fatigue_monitor = None
        logger.info("[VECTOR][avatar] AvatarCore ready — mood={}", self._state.mood_label)

    # ── lazy accessors ───────────────────────────────────────────────────────
    def _get_person_model(self):
        if self._person_model is None:
            try:
                from core.brain.person_model import PersonModel
                self._person_model = PersonModel()
            except Exception as e:
                logger.debug("[VECTOR][avatar] person_model unavailable: {}", e)
        return self._person_model

    def _get_health_monitor(self):
        if self._health_monitor is None:
            try:
                from core.sensing.health_monitor import HealthMonitor
                self._health_monitor = HealthMonitor()
            except Exception as e:
                logger.debug("[VECTOR][avatar] health_monitor unavailable: {}", e)
        return self._health_monitor

    def _get_fatigue_monitor(self):
        if self._fatigue_monitor is None:
            try:
                from districts.health.fatigue_monitor import FatigueMonitor
                self._fatigue_monitor = FatigueMonitor()
            except Exception as e:
                logger.debug("[VECTOR][avatar] fatigue_monitor unavailable: {}", e)
        return self._fatigue_monitor

    # ── lifecycle hooks ──────────────────────────────────────────────────────
    def on_observe(self, sensor_data: dict | None = None) -> dict:
        """
        Pull stress/fatigue signals from existing health stack.
        Returns an enriched observation dict. Never raises.
        """
        obs: dict[str, Any] = dict(sensor_data or {})
        try:
            hm = self._get_health_monitor()
            if hm is not None:
                status = hm.get_status() if hasattr(hm, "get_status") else {}
                if isinstance(status, dict):
                    obs["cpu_percent"]    = status.get("cpu_percent", 0)
                    obs["memory_percent"] = status.get("memory_percent", 0)
        except Exception as e:
            logger.debug("[VECTOR][avatar] health_monitor observe failed: {}", e)

        try:
            fm = self._get_fatigue_monitor()
            if fm is not None:
                fatigue = fm.get_fatigue_score() if hasattr(fm, "get_fatigue_score") else None
                if fatigue is not None:
                    obs["fatigue_score"] = fatigue
                    if fatigue > 0.7:
                        logger.info("[VECTOR][avatar] high fatigue detected ({:.2f})", fatigue)
        except Exception as e:
            logger.debug("[VECTOR][avatar] fatigue_monitor observe failed: {}", e)

        # Decay presence when idle
        self._state.decay_presence(delta=0.01)

        # If voice/text present, run SentimentAnalyzer and absorb VAD into state
        text = obs.get("text", obs.get("intent", ""))
        if text:
            try:
                from core.personality.sentiment import SentimentAnalyzer
                analyzer = SentimentAnalyzer()
                sentiment = analyzer.analyze(text)
                if sentiment:
                    self._state.absorb_sentiment(sentiment.emotion, sentiment.intensity)
                    logger.debug("[VECTOR][avatar] absorbed sentiment: {} ({:.2f})", sentiment.emotion, sentiment.intensity)
            except Exception as e:
                logger.debug("[VECTOR][avatar] sentiment analysis failed: {}", e)

        return obs

    def on_think(self, candidates: list[dict]) -> list[dict]:
        """
        Apply a small persona nudge to candidate scoring (5% blend, mirrors causal_score).
        Prefers candidates that align with current mood (e.g. calmer tasks when tense).
        Never raises; returns candidates unchanged on failure.
        """
        if not candidates:
            return candidates
        try:
            for c in candidates:
                action = c.get("action_type", "")
                base   = c.get("score", 0.5)
                # calm mood → slightly prefer non-confrontational action types
                if self._state.mood_label in ("tense", "subdued"):
                    if any(kw in action for kw in ("review", "report", "research", "reflect")):
                        c["score"] = min(1.0, base + 0.05)
                        c.setdefault("reasoning_steps", []).append(
                            f"avatar mood={self._state.mood_label} nudge +0.05"
                        )
        except Exception as e:
            logger.debug("[VECTOR][avatar] on_think nudge failed: {}", e)
        return candidates

    def on_act(
        self,
        raw_result: Any,
        task_context: dict | None = None,
        user_message: str = "",
    ) -> Any:
        """
        The single wrap point: format governor's raw district output via AvatarVoice.
        Returns a dict with 'response' key containing the formatted text, plus
        all original keys preserved.
        Never raises — falls back to raw_result on any error.
        """
        try:
            formatted = self._voice.format(
                raw_result,
                self._state,
                task_context=task_context,
                user_message=user_message,
            )
            self._state.boost_presence(delta=0.05)
            # Merge formatted response back into result dict
            if isinstance(raw_result, dict):
                return {**raw_result, "response": formatted, "_avatar_formatted": True}
            return {"response": formatted, "raw": raw_result, "_avatar_formatted": True}
        except Exception as e:
            logger.warning("[VECTOR][avatar] on_act failed ({}), returning raw", e)
            return raw_result

    def on_reflect(self, interaction_summary: str = "", outcome: str = "ok") -> None:
        """
        Advance relationship state via PersonModel (not a new store).
        Save AvatarState after each reflect cycle. Never raises.
        """
        try:
            pm = self._get_person_model()
            if pm is not None and interaction_summary:
                owner_id = "owner"
                # Ensure owner record exists
                existing = pm.get_person(owner_id) if hasattr(pm, "get_person") else None
                if existing is None and hasattr(pm, "add_person"):
                    pm.add_person(
                        person_id=owner_id,
                        name=CONFIG.get("owner_name", "Arghyadeep"),
                        relationship_type="owner",
                    )
                # Update trust score: positive outcome → small trust gain
                if hasattr(pm, "update_trust"):
                    delta = 0.01 if outcome == "ok" else -0.005
                    pm.update_trust(owner_id, delta)
                # Log interaction
                if hasattr(pm, "add_interaction"):
                    pm.add_interaction(
                        person_id=owner_id,
                        summary=interaction_summary[:200],
                        sentiment=self._state.mood_label,
                        channel="avatar",
                    )
        except Exception as e:
            logger.debug("[VECTOR][avatar] person_model reflect failed: {}", e)

        try:
            self._state.save()
        except Exception as e:
            logger.warning("[VECTOR][avatar] state save failed: {}", e)

    # ── convenience ──────────────────────────────────────────────────────────
    @property
    def state(self) -> AvatarState:
        return self._state

    def reload_state(self) -> None:
        """Hot-reload state from DB (call after external update)."""
        self._state = AvatarState.load()


if __name__ == "__main__":
    import asyncio

    core = AvatarCore()

    # on_observe — should not raise even with no sensors
    obs = core.on_observe({"test": True})
    assert isinstance(obs, dict), "on_observe must return dict"

    # on_think — nudge should not crash
    candidates = [
        {"action_type": "review_code", "score": 0.7},
        {"action_type": "deploy",      "score": 0.8},
    ]
    ranked = core.on_think(candidates)
    assert len(ranked) == 2, "on_think must return same number of candidates"

    # on_act — internal names must be stripped
    raw = {"status": "ok", "response": "CodingBot reviewed your code."}
    result = core.on_act(raw, user_message="review my code")
    assert "_avatar_formatted" in result, "on_act must set _avatar_formatted"
    assert "CodingBot" not in result.get("response", ""), "CodingBot must be stripped"

    # on_reflect — must not raise
    core.on_reflect("Reviewed code for the owner", outcome="ok")

    loaded = AvatarState.load()
    print(
        f"OK avatar_core -- mood={loaded.mood_label} "
        f"presence={loaded.presence_score:.2f} "
        f"response={result['response'][:60]!r}"
    )
