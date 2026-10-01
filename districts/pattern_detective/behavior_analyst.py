"""
Module: agents/pattern_detective/behavior_analyst.py
District: pattern_detective | Focus: Analyze behavior patterns, predict actions, suggest improvements
"""

import sys
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, datetime, collections
from typing import Optional


class BehaviorAnalyst(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="BehaviorAnalyst",
            district="pattern_detective",
            generation=1
        )
        self.capabilities = ["behavior", "pattern", "pattern_detective"]
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.behavior_profiles = {}
        logger.info("[VECTOR][pattern_detective] BehaviorAnalyst ready")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.vectorcode_llm import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
            district=self.district,
            sensitive=True,
            allow_cloud=False,  # behavioural logs about the owner: local Ollama only
        )

    _OWN_SOURCES = frozenset({"BehaviorAnalyst", "HabitFinder"})

    def _recent_activity(self, limit: int = 100) -> list[dict]:
        """Recent episodic events as an activity log, excluding this district's
        own derived events (they would otherwise be analysed as the owner's
        behaviour)."""
        events = self.memory.recall("", limit=limit) or []
        return [
            {"type": e.get("event_type", "unknown"), "timestamp": e.get("timestamp", "")}
            for e in events if e.get("source") not in self._OWN_SOURCES
        ]

    @staticmethod
    def _to_float(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def analyze_behavior(self, activity_log: list[dict]) -> dict:
        activity_log = [a for a in (activity_log or []) if isinstance(a, dict)]
        logger.info("[VECTOR][pattern_detective] Analyzing {} behavior records", len(activity_log))
        self.add_lesson({"action": "analyze_behavior", "records": len(activity_log)})

        if not activity_log:
            # Empty/failed data pull: not "no concerning behaviour".
            return {"status": "no_data", "total_activities": 0, "activity_types": 0,
                    "behavior_profile": {}, "insights": ""}

        type_counts = collections.Counter(a.get("type", "unknown") for a in activity_log)
        time_by_type = collections.defaultdict(list)
        duration_by_type = collections.defaultdict(list)
        bad_timestamps = 0

        for entry in activity_log:
            entry_type = entry.get("type", "unknown")
            duration = self._to_float(entry.get("duration", 0))
            timestamp = entry.get("timestamp", "")

            if timestamp:
                try:
                    dt = datetime.datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                    period = "morning" if 6 <= dt.hour < 12 else "afternoon" if 12 <= dt.hour < 18 else "evening" if 18 <= dt.hour < 22 else "night"
                    time_by_type[entry_type].append(period)
                except ValueError:
                    bad_timestamps += 1

            if duration:
                duration_by_type[entry_type].append(duration)

        behavior_profile = {}
        for btype, count in type_counts.items():
            durations = duration_by_type.get(btype, [])
            time_distribution = dict(collections.Counter(time_by_type.get(btype, [])))
            behavior_profile[btype] = {
                "frequency": count,
                "avg_duration": round(sum(durations) / max(len(durations), 1), 1) if durations else 0,
                "time_distribution": time_distribution,
                "total_duration": sum(durations),
            }

        self.behavior_profiles["default"] = behavior_profile

        if bad_timestamps:
            logger.warning("[VECTOR][pattern_detective] {} record(s) had unparseable timestamps; excluded from time distribution", bad_timestamps)

        prompt = f"""Analyze this behavior profile and provide insights:
{json.dumps(behavior_profile, indent=2)}
Total activities: {len(activity_log)}
Provide: 1) Behavioral pattern identification, 2) Productivity analysis, 3) Consistency score (1-10), 4) Key strengths and weaknesses."""
        insights = self._call_ollama(prompt)
        if not (insights or "").strip():
            logger.warning("[VECTOR][pattern_detective] Behavior analysis: LLM returned nothing")
            return {"status": "error", "error": "llm_unavailable", "total_activities": len(activity_log),
                    "activity_types": len(type_counts), "behavior_profile": behavior_profile, "insights": ""}

        result = {
            "status": "ok",
            "total_activities": len(activity_log),
            "activity_types": len(type_counts),
            "behavior_profile": behavior_profile,
            "insights": insights,
            "analyzed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="behavior_analyzed",
            content=f"Analyzed {len(activity_log)} behavior records across {len(type_counts)} types",
            tags=["pattern", "behavior", "analysis"],
            context=result,
            source="BehaviorAnalyst"
        )

        logger.info(f"[VECTOR][pattern_detective] Behavior analysis complete: {len(type_counts)} types identified")
        return result

    def predict_next_action(self, current_context: dict) -> dict:
        logger.info("[VECTOR][pattern_detective] Predicting next action")
        self.add_lesson({"action": "predict_next_action"})

        profile = self.behavior_profiles.get("default", {})
        if not profile:
            # KNOWN_ISSUES #21: don't close EpisodicMemory()'s shared singleton
            # connection from a local instance — see skill_mapper.py's note.
            activity_log = self._recent_activity(100)
            if activity_log:
                self.analyze_behavior(activity_log)
            profile = self.behavior_profiles.get("default", {})

        if not profile:
            # No history to extrapolate from: do not let the LLM invent a
            # "most likely next action" with a made-up confidence.
            return {"status": "no_data", "prediction": {}, "current_context": current_context,
                    "based_on_profiles": 0}

        sorted_activities = sorted(profile.items(), key=lambda x: x[1]["frequency"], reverse=True)
        top_activities = [a for a, d in sorted_activities[:5]]

        prompt = f"""Predict the next action based on:
Current context: {json.dumps(current_context, indent=2)}
Top recurring activities: {top_activities}
Based on time patterns, what is the most likely next action?
Return JSON: {{predicted_action: string, confidence: float, reasoning: string, alternative_actions: string[]}}"""
        prediction = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        if not (prediction or "").strip():
            logger.warning("[VECTOR][pattern_detective] Prediction: LLM returned nothing")
            return {"status": "error", "error": "llm_unavailable", "prediction": {},
                    "current_context": current_context, "based_on_profiles": len(profile)}

        try:
            import re
            json_match = re.search(r'\{.*\}', prediction, re.DOTALL)
            if json_match:
                pred_data = json.loads(json_match.group(0))
            else:
                pred_data = {"predicted_action": prediction[:100], "confidence": 0.5, "reasoning": "Based on pattern analysis"}
        except json.JSONDecodeError:
            pred_data = {"predicted_action": prediction[:100], "confidence": 0.5, "reasoning": "Based on pattern analysis"}

        result = {
            "status": "ok",
            "prediction": pred_data,
            "current_context": current_context,
            "based_on_profiles": len(profile),
            "predicted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="action_predicted",
            content=f"Predicted next action: {pred_data.get('predicted_action', 'unknown')[:50]}",
            tags=["pattern", "prediction", "behavior"],
            context=result,
            source="BehaviorAnalyst"
        )

        return result

    def suggest_improvements(self, behavior: dict) -> dict:
        logger.info("[VECTOR][pattern_detective] Suggesting behavior improvements")
        self.add_lesson({"action": "suggest_improvements"})

        if not behavior:
            return {"status": "no_data", "behavior_summary": {}, "improvements": {}}

        prompt = f"""Suggest improvements for this behavioral profile:
{json.dumps(behavior, indent=2)}
Focus on: 1) Time management improvements, 2) Habit formation suggestions, 3) Productivity boosts, 4) Balance recommendations.
Format: JSON with improvements (list), priority (high/medium/low), expected_impact, and rationale."""
        suggestions = self._call_ollama(prompt, model=CONFIG["models"]["reasoning"])
        if not (suggestions or "").strip():
            logger.warning("[VECTOR][pattern_detective] Improvements: LLM returned nothing")
            return {"status": "error", "error": "llm_unavailable", "behavior_summary": behavior,
                    "improvements": {}}

        try:
            import re
            json_match = re.search(r'\{.*\}', suggestions, re.DOTALL)
            if json_match:
                improvements = json.loads(json_match.group(0))
            else:
                improvements = {"improvements": [{"action": suggestions[:200], "priority": "medium", "expected_impact": "moderate"}]}
        except json.JSONDecodeError:
            improvements = {"improvements": [{"action": suggestions[:200], "priority": "medium", "expected_impact": "moderate"}]}

        result = {
            "status": "ok",
            "behavior_summary": behavior,
            "improvements": improvements,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

        self.memory.store(
            event_type="improvements_suggested",
            content=f"Suggested behavior improvements",
            tags=["pattern", "improvement", "suggestions"],
            context=result,
            source="BehaviorAnalyst"
        )

        return result


    async def run(self, task: dict) -> dict:
        p = (task or {}).get("params") or {}
        # Previously this called a non-existent analyse() and returned
        # status "ok" having done nothing.
        activity_log = p.get("activity_log") or self._recent_activity(100)
        result = self.analyze_behavior(activity_log)
        return {"status": result.get("status", "ok"), "analysis": result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    agent = BehaviorAnalyst()
    assert agent.district == "pattern_detective"

    activity_log = [
        {"type": "coding", "timestamp": "2026-05-01T10:00:00Z", "duration": 120},
        {"type": "coding", "timestamp": "2026-05-01T14:00:00Z", "duration": 90},
        {"type": "reading", "timestamp": "2026-05-01T20:00:00Z", "duration": 30},
        {"type": "coding", "timestamp": "2026-05-02T09:00:00Z", "duration": 150},
        {"type": "exercise", "timestamp": "2026-05-02T07:00:00Z", "duration": 45},
    ]
    analysis = agent.analyze_behavior(activity_log)
    assert "behavior_profile" in analysis
    assert "coding" in analysis["behavior_profile"]

    prediction = agent.predict_next_action({"time": "2026-05-03T09:00:00Z", "day": "Saturday"})
    assert "prediction" in prediction

    improvements = agent.suggest_improvements(analysis["behavior_profile"])
    assert "improvements" in improvements

    print("✅ behavior_analyst.py OK")