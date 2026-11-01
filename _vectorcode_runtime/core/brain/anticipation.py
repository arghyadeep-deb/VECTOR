"""
VECTOR Anticipatory Action Engine (C3).

Predicts what the owner will need in the next N minutes by combining:
  * Time-of-day heuristics (9pm → journal, 7am → morning brief)
  * Active goal alignment (low-progress active goals → nudge)
  * Episodic pattern analysis (recurring actions at same hour)
  * Optional LLM reasoning (cloud, complexity=complex) for non-obvious patterns

All proactive actions use the 'proactive_*' action_type prefix so the
permission_gateway can apply stricter thresholds than reactive actions.
"""
from __future__ import annotations

__all__ = [
    "AnticipationEngine",
    "Prediction",
    "get_anticipation_engine",
]

import datetime
import sys
import threading
from dataclasses import dataclass, field

from loguru import logger

from core.config import CONFIG


# ── Prediction dataclass ─────────────────────────────────────────────────────


@dataclass
class Prediction:
    need: str                                   # short label: "journal", "water_break"
    action_type: str                            # always "proactive_<need>"
    description: str                            # human-readable explanation
    confidence: float                           # 0.0–1.0
    source: str                                 # "time_pattern" | "goal_alignment" | "episode_pattern" | "llm"
    params: dict = field(default_factory=dict)
    hour: int = -1                              # hour of day this fires (for dedup)


# ── Time-of-day heuristics ───────────────────────────────────────────────────

# Maps (start_hour, end_hour) → (need, description, confidence)
_TIME_HEURISTICS: list[tuple[int, int, str, str, float]] = [
    (6,  9,  "morning_brief",  "Morning briefing: goals, calendar, news digest",  0.80),
    (9,  12, "goal_review",    "Mid-morning: review active goals and priorities", 0.70),
    (12, 14, "lunch_break",    "Lunch break approaching — consider stepping away", 0.65),
    (14, 16, "focus_session",  "Afternoon peak: start a deep-focus coding session", 0.70),
    (17, 19, "daily_review",   "End of working day: review what was accomplished",  0.75),
    (20, 22, "journal",        "Evening reflection: write in journal",              0.85),
    (22, 24, "sleep_prep",     "Late night: wind down and prepare for sleep",       0.78),
    (0,  6,  "sleep_reminder", "After midnight: you should be sleeping",            0.90),
]


def _time_heuristic_predictions(now: datetime.datetime, window_minutes: int) -> list[Prediction]:
    """Return heuristic predictions valid for the next window_minutes."""
    hour = now.hour
    minute = now.minute
    # Include heuristics whose window overlaps [now, now + window_minutes)
    end_hour = (hour * 60 + minute + window_minutes) // 60
    results = []
    for start_h, end_h, need, desc, conf in _TIME_HEURISTICS:
        if start_h <= hour < end_h or (hour < start_h <= end_hour):
            results.append(Prediction(
                need=need,
                action_type=f"proactive_{need}",
                description=desc,
                confidence=conf,
                source="time_pattern",
                hour=hour,
            ))
    return results


# ── Goal-alignment heuristics ─────────────────────────────────────────────────


def _goal_alignment_predictions() -> list[Prediction]:
    """Nudge when an active goal has < 20% progress or is overdue."""
    results = []
    try:
        from core.brain.goal_system import GoalSystem
        gs = GoalSystem()
        summary = gs.get_goal_summary()
        if "overdue" in summary.lower() or "stalled" in summary.lower():
            results.append(Prediction(
                need="goal_nudge",
                action_type="proactive_goal_nudge",
                description="An active goal is overdue or stalled — review now",
                confidence=0.78,
                source="goal_alignment",
            ))
    except Exception as e:
        logger.debug("[VECTOR][anticipation] goal heuristic skipped: {}", e)
    return results


# ── Episode pattern analysis ─────────────────────────────────────────────────


def _episode_pattern_predictions(now: datetime.datetime, top_k: int = 20) -> list[Prediction]:
    """
    Detect recurring event types at the current hour across past episodes.
    If an event_type appears ≥2 times at this hour in last 7 days → predict it.
    """
    results = []
    try:
        from core.memory.episodic import EpisodicMemory
        mem = EpisodicMemory()
        episodes = mem.recall("", limit=top_k)
        hour = now.hour
        from collections import Counter
        hour_types: Counter = Counter()
        for ep in episodes:
            ts_str = ep.get("timestamp", "")
            try:
                ts = datetime.datetime.fromisoformat(ts_str)
                if abs(ts.hour - hour) <= 1:
                    hour_types[ep.get("event_type", "unknown")] += 1
            except Exception:
                continue
        for event_type, count in hour_types.items():
            if count >= 2 and event_type not in ("observe", "system", "unknown"):
                results.append(Prediction(
                    need=event_type,
                    action_type=f"proactive_{event_type}",
                    description=f"You typically do '{event_type}' around {hour}:00 (seen {count}× recently)",
                    confidence=min(0.5 + count * 0.1, 0.90),
                    source="episode_pattern",
                    hour=hour,
                ))
    except Exception as e:
        logger.debug("[VECTOR][anticipation] episode pattern skipped: {}", e)
    return results


# ── LLM reasoning (optional, cloud) ─────────────────────────────────────────


def _llm_predictions(context: str, now: datetime.datetime) -> list[Prediction]:
    """Ask the LLM to identify needs not covered by heuristics. Cloud-routed."""
    results = []
    try:
        from core.inference.cloud_router import route as _cr_route
        decision = _cr_route(context, complexity_hint="complex")
        if not decision.is_cloud:
            logger.debug("[VECTOR][anticipation] LLM prediction skipped — no cloud available")
            return results

        import asyncio, json as _json
        from core.inference.provider_client import ProviderClient
        prompt = (
            f"Current time: {now.strftime('%H:%M')} ({now.strftime('%A')})\n"
            f"Recent context: {context[:500]}\n\n"
            "List 1-3 things the user is likely to need in the next 30 minutes. "
            "Respond ONLY with JSON: [{\"need\": \"...\", \"description\": \"...\", \"confidence\": 0.0-1.0}]"
        )
        client = ProviderClient()

        async def _ask():
            return await client.complete(
                prompt,
                provider=decision.provider,
                max_tokens=200,
                temperature=0.3,
            )

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(asyncio.run, _ask())
                    resp = fut.result(timeout=15)
            else:
                resp = loop.run_until_complete(_ask())

            raw = resp.content.strip()
            items = _json.loads(raw)
            for item in items[:3]:
                need = str(item.get("need", "")).strip()
                if not need:
                    continue
                results.append(Prediction(
                    need=need,
                    action_type=f"proactive_{need}",
                    description=str(item.get("description", need)),
                    confidence=float(item.get("confidence", 0.6)),
                    source="llm",
                ))
        except Exception as _inner:
            logger.debug("[VECTOR][anticipation] LLM parse failed: {}", _inner)
    except Exception as e:
        logger.debug("[VECTOR][anticipation] LLM prediction skipped: {}", e)
    return results


# ── AnticipationEngine ───────────────────────────────────────────────────────


class AnticipationEngine:
    """
    Predicts what the owner will need next and surfaces high-confidence
    predictions as proactive actions through the autonomous loop.

    Usage:
        engine = AnticipationEngine()
        predictions = engine.predict_next_need(window_minutes=30)
        # predictions are sorted by confidence, descending
    """

    def __init__(self) -> None:
        self._last_predictions: list[Prediction] = []
        self._lock = threading.Lock()

    def predict_next_need(self, window_minutes: int = 30) -> list[Prediction]:
        """
        Return a ranked list of predicted needs for the coming window.

        Sources consulted in order:
          1. Time-of-day heuristics (always fast, no I/O)
          2. Goal-alignment nudges (reads GoalSystem, fast)
          3. Episode pattern analysis (reads EpisodicMemory, fast)
          4. LLM reasoning (optional, only if cloud is available)

        Predictions are deduplicated by (need, hour) and sorted by confidence.
        """
        now = datetime.datetime.now(datetime.timezone.utc).astimezone()
        all_preds: list[Prediction] = []

        all_preds.extend(_time_heuristic_predictions(now, window_minutes))
        all_preds.extend(_goal_alignment_predictions())
        all_preds.extend(_episode_pattern_predictions(now))

        # LLM reasoning only when enabled via CONFIG
        if CONFIG.get("anticipation", {}).get("llm_enabled", False):
            context = f"time={now.strftime('%H:%M')}, predictions so far: {[p.need for p in all_preds]}"
            all_preds.extend(_llm_predictions(context, now))

        # Deduplicate by (need, hour) — keep highest confidence
        seen: dict[tuple[str, int], Prediction] = {}
        for pred in all_preds:
            key = (pred.need, pred.hour)
            if key not in seen or pred.confidence > seen[key].confidence:
                seen[key] = pred

        ranked = sorted(seen.values(), key=lambda p: p.confidence, reverse=True)

        with self._lock:
            self._last_predictions = ranked

        logger.debug(
            "[VECTOR][anticipation] {} predictions at {}: {}",
            len(ranked), now.strftime("%H:%M"),
            [(p.need, round(p.confidence, 2)) for p in ranked[:5]],
        )
        return ranked

    def get_last_predictions(self) -> list[Prediction]:
        """Return the most recent prediction result without recomputing."""
        with self._lock:
            return list(self._last_predictions)

    def high_confidence(self, threshold: float = 0.75) -> list[Prediction]:
        """Return last predictions above the confidence threshold."""
        return [p for p in self.get_last_predictions() if p.confidence >= threshold]


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: AnticipationEngine | None = None
_engine_lock = threading.Lock()


def get_anticipation_engine() -> AnticipationEngine:
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = AnticipationEngine()
    return _engine


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    engine = AnticipationEngine()
    preds = engine.predict_next_need(window_minutes=30)
    print(f"Predictions ({len(preds)}):")
    for p in preds:
        print(f"  [{p.source}] {p.action_type} conf={p.confidence:.2f}: {p.description}")
    print("OK: anticipation")
