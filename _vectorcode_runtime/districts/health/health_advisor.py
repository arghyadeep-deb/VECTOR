from __future__ import annotations

import datetime
import asyncio
from typing import Any

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger

from core.config import CONFIG
from core.city.agent_base import AgentBase

class HealthAdvisor(AgentBase):
    def __init__(self) -> None:
        super().__init__(
            agent_id=f"health_advisor_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}",
            name="health_advisor",
            district="health",
        )
        self.capabilities = ["advice", "health", "health_check", "health_recommendations"]
        self._use_llm: bool = CONFIG.get("health", {}).get("advisor_use_llm", False)
        self._max_recs: int = CONFIG.get("health", {}).get("advisor_max_recommendations", 5)

    def _run_or_schedule(self, coro: Any, label: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                asyncio.run(coro)
            except Exception as exc:
                logger.warning(f"[VECTOR][health_advisor] {label} failed: {exc}")
            return

        try:
            loop.create_task(coro)
        except Exception as exc:
            logger.warning(f"[VECTOR][health_advisor] {label} schedule failed: {exc}")

    def _send_pushover(self, title: str, message: str) -> None:
        # Sends via Telegram now (2026-10-30, owner decision — Pushover is a
        # paid service). Method name kept as-is, just an identifier.
        try:
            from core.notify import send_telegram
            token = CONFIG.get("telegram_bot_token", "")
            chat_id = CONFIG.get("telegram_chat_id", "")
            if token and chat_id:
                self._run_or_schedule(send_telegram(f"{title}\n{message}", priority=1), "telegram send")
        except Exception as exc:
            logger.warning(f"[VECTOR][health_advisor] telegram failed: {exc}")

    def generate_recommendations(self, metrics: dict[str, Any], trends: dict[str, Any]) -> list[dict[str, Any]]:
        recommendations: list[dict[str, Any]] = []
        hr_metrics = metrics.get("heart_rate", {})
        hrv_val = metrics.get("hrv")
        sleep_val = metrics.get("sleep_hours")
        steps_val = metrics.get("steps")
        stress_val = metrics.get("stress_level")
        spo2_val = metrics.get("spo2")
        temp_val = metrics.get("skin_temperature")
        exercise_val = metrics.get("exercise_minutes")

        recommendations.extend(self._rec_sleep_hygiene(sleep_val, trends))
        recommendations.extend(self._rec_activity_exercise(steps_val, exercise_val, trends))
        recommendations.extend(self._rec_stress_management(hrv_val, stress_val))
        recommendations.extend(self._rec_hydration_nutrition(temp_val, trends))
        recommendations.extend(self._rec_ergonomics(hr_metrics, trends))
        recommendations.extend(self._rec_medical_attention(hr_metrics, spo2_val, hrv_val))
        recommendations.extend(self._rec_lifestyle_balance(sleep_val, stress_val, steps_val))
        recommendations.extend(self._rec_routine_optimization(trends))

        recommendations.sort(key=lambda r: r.get("priority", 5))

        if self._use_llm:
            insight = self._llm_insight(metrics, trends)
            if insight:
                recommendations.append({
                    "type": "LIFESTYLE_BALANCE", "title": "AI Health Insight",
                    "description": insight, "priority": 2, "metric_source": "llm", "actionable": False,
                })

        top = recommendations[:self._max_recs]
        for r in top:
            if r.get("priority", 5) <= 2 and r.get("actionable", True):
                self._send_pushover(f"Health: {r['title']}", r.get("description", ""))

        return top

    def _rec_sleep_hygiene(self, sleep_val: float | None, trends: dict[str, Any]) -> list[dict[str, Any]]:
        recs: list[dict[str, Any]] = []
        if sleep_val is not None:
            if sleep_val < 5:
                recs.append({"type": "SLEEP_HYGIENE", "title": "Severe sleep deprivation", "description": f"Only {sleep_val:.1f}h sleep. Prioritize 7-9h. Avoid caffeine after 4pm.", "priority": 5, "metric_source": "sleep_hours", "actionable": True})
            elif sleep_val < 6:
                recs.append({"type": "SLEEP_HYGIENE", "title": "Insufficient sleep", "description": f"Only {sleep_val:.1f}h sleep. Target 7-9h. Limit screens 1h before bed.", "priority": 4, "metric_source": "sleep_hours", "actionable": True})
            elif sleep_val < 7:
                recs.append({"type": "SLEEP_HYGIENE", "title": "Suboptimal sleep", "description": f"Got {sleep_val:.1f}h. Try a consistent bedtime routine for better quality.", "priority": 2, "metric_source": "sleep_hours", "actionable": True})
        sleep_trend = trends.get("sleep_hours", trends.get("sleep"))
        if sleep_trend and isinstance(sleep_trend, dict):
            direction = sleep_trend.get("direction", "stable")
            if direction == "declining":
                recs.append({"type": "SLEEP_HYGIENE", "title": "Sleep declining trend", "description": "Your sleep duration is trending downward. Consider a wind-down routine.", "priority": 3, "metric_source": "sleep_hours", "actionable": True})
        return recs

    def _rec_activity_exercise(self, steps_val: int | None, exercise_val: float | None, trends: dict[str, Any]) -> list[dict[str, Any]]:
        recs: list[dict[str, Any]] = []
        if steps_val is not None:
            if steps_val < 3000:
                recs.append({"type": "ACTIVITY_EXERCISE", "title": "Very low activity", "description": f"Only {steps_val} steps today. A 10-min walk can improve focus.", "priority": 4, "metric_source": "steps", "actionable": True})
            elif steps_val < 6000:
                recs.append({"type": "ACTIVITY_EXERCISE", "title": "Low step count", "description": f"{steps_val} steps today. Aim for 8k. Take stairs when possible.", "priority": 3, "metric_source": "steps", "actionable": True})
            elif steps_val < 8000:
                recs.append({"type": "ACTIVITY_EXERCISE", "title": "Moderate activity", "description": f"{steps_val} steps. Close to 8k goal! An evening walk can push you there.", "priority": 1, "metric_source": "steps", "actionable": True})
        if exercise_val is not None and exercise_val < 10:
            recs.append({"type": "ACTIVITY_EXERCISE", "title": "No dedicated exercise", "description": "Less than 10min of exercise today. Even 15min bodyweight routine helps.", "priority": 3, "metric_source": "exercise_minutes", "actionable": True})
        step_trend = trends.get("steps")
        if step_trend and isinstance(step_trend, dict) and step_trend.get("direction") == "declining":
            recs.append({"type": "ACTIVITY_EXERCISE", "title": "Activity declining trend", "description": "Your step count is trending down. Schedule a walk break.", "priority": 2, "metric_source": "steps", "actionable": True})
        return recs

    def _rec_stress_management(self, hrv_val: float | None, stress_val: float | None) -> list[dict[str, Any]]:
        recs: list[dict[str, Any]] = []
        if hrv_val is not None and hrv_val < 20:
            recs.append({"type": "STRESS_MANAGEMENT", "title": "Critical HRV — overtraining risk", "description": f"HRV at {hrv_val}ms indicates high stress. Take a rest day. Try box breathing.", "priority": 5, "metric_source": "hrv", "actionable": True})
        elif hrv_val is not None and hrv_val < 30:
            recs.append({"type": "STRESS_MANAGEMENT", "title": "Low HRV — elevated stress", "description": f"HRV at {hrv_val}ms. Try 5-min meditation or a short walk.", "priority": 3, "metric_source": "hrv", "actionable": True})
        if stress_val is not None and stress_val > 0.7:
            recs.append({"type": "STRESS_MANAGEMENT", "title": "High stress detected", "description": f"Stress level at {stress_val:.2f}. Deep breathing (4-7-8) or stepping away helps.", "priority": 4, "metric_source": "stress_level", "actionable": True})
        elif stress_val is not None and stress_val > 0.5:
            recs.append({"type": "STRESS_MANAGEMENT", "title": "Moderate stress", "description": f"Stress at {stress_val:.2f}. Take 5 deep breaths or stretch.", "priority": 2, "metric_source": "stress_level", "actionable": True})
        return recs

    def _rec_hydration_nutrition(self, temp_val: float | None, trends: dict[str, Any]) -> list[dict[str, Any]]:
        recs: list[dict[str, Any]] = []
        if temp_val is not None and temp_val > 37.5:
            recs.append({"type": "HYDRATION_NUTRITION", "title": "Elevated temperature — hydrate", "description": f"Skin temp {temp_val:.1f}C. Increase water intake and monitor for fever.", "priority": 3, "metric_source": "skin_temperature", "actionable": True})
        recs.append({"type": "HYDRATION_NUTRITION", "title": "Stay hydrated reminder", "description": "Drink a glass of water now. Aim for 2-3L throughout the day.", "priority": 1, "metric_source": "", "actionable": True})
        return recs

    def _rec_ergonomics(self, hr_metrics: dict[str, Any], trends: dict[str, Any]) -> list[dict[str, Any]]:
        recs: list[dict[str, Any]] = []
        fatigue = trends.get("fatigue_score")
        if fatigue is not None and isinstance(fatigue, dict):
            fatigue_val = fatigue.get("avg_value", 0)
            if fatigue_val > 6:
                recs.append({"type": "ERGONOMICS", "title": "High fatigue — take a break", "description": f"Fatigue at {fatigue_val:.1f}/10. Stand up, stretch, rest eyes for 5min.", "priority": 4, "metric_source": "fatigue_score", "actionable": True})
        recs.append({"type": "ERGONOMICS", "title": "Posture check", "description": "Roll shoulders back, align ears over shoulders. Check screen at eye level.", "priority": 1, "metric_source": "", "actionable": True})
        return recs

    def _rec_medical_attention(self, hr_metrics: dict[str, Any], spo2_val: float | None, hrv_val: float | None) -> list[dict[str, Any]]:
        recs: list[dict[str, Any]] = []
        hr = hr_metrics.get("avg_value", hr_metrics.get("heart_rate")) if isinstance(hr_metrics, dict) else hr_metrics
        if hr is not None and isinstance(hr, (int, float)):
            if hr > 120:
                recs.append({"type": "MEDICAL_ATTENTION", "title": "Very high heart rate — consult doctor", "description": f"Resting HR at {hr:.0f} bpm. If sustained, consult a healthcare provider.", "priority": 5, "metric_source": "heart_rate", "actionable": True})
            elif hr > 100:
                recs.append({"type": "MEDICAL_ATTENTION", "title": "Elevated heart rate", "description": f"Resting HR at {hr:.0f} bpm. Monitor and consider relaxation techniques.", "priority": 3, "metric_source": "heart_rate", "actionable": True})
        if spo2_val is not None and spo2_val < 92:
            recs.append({"type": "MEDICAL_ATTENTION", "title": "Low blood oxygen — seek medical attention", "description": f"SpO2 at {spo2_val}%. If persistent, consult a healthcare provider.", "priority": 5, "metric_source": "spo2", "actionable": True})
        return recs

    def _rec_lifestyle_balance(self, sleep_val: float | None, stress_val: float | None, steps_val: int | None) -> list[dict[str, Any]]:
        recs: list[dict[str, Any]] = []
        compound_score = 0
        if sleep_val is not None and sleep_val < 6:
            compound_score += 1
        if stress_val is not None and stress_val > 0.6:
            compound_score += 1
        if steps_val is not None and steps_val < 5000:
            compound_score += 1
        if compound_score >= 2:
            recs.append({"type": "LIFESTYLE_BALANCE", "title": "Multiple health signals need attention", "description": "Poor sleep + high stress + low activity detected. Focus on one change today.", "priority": 4, "metric_source": "compound", "actionable": True})
        return recs

    def _rec_routine_optimization(self, trends: dict[str, Any]) -> list[dict[str, Any]]:
        recs: list[dict[str, Any]] = []
        circadian = trends.get("circadian", {})
        if circadian and isinstance(circadian, dict):
            peak_hour = circadian.get("peak_hour")
            trough_hour = circadian.get("trough_hour")
            if peak_hour is not None and trough_hour is not None:
                recs.append({"type": "ROUTINE_OPTIMIZATION", "title": "Circadian-based routine tip", "description": f"Energy peaks around {peak_hour}:00, troughs at {trough_hour}:00. Schedule deep work at peak.", "priority": 2, "metric_source": "circadian", "actionable": True})
        return recs

    def _llm_insight(self, metrics: dict[str, Any], trends: dict[str, Any]) -> str | None:
        try:
            from core.inference.vectorcode_llm import chat
            focus_model = CONFIG.get("models", {}).get("focus", "vector-focus")
            prompt = f"Health metrics summary: {metrics}\nTrends: {trends}\nProvide 1-2 concise health observations and actionable suggestions."
            result = chat(model=focus_model, messages=[
                {"role": "system", "content": "You are a health advisor."},
                {"role": "user", "content": prompt},
            ], timeout=30.0)
            if result and result.strip():
                return result.strip()
        except Exception as exc:
            logger.warning(f"[VECTOR][health_advisor] LLM insight unavailable: {exc}")
        return None

    async def handle(self, event: dict) -> dict:
        if event.get("type") == "health_recommendations":
            metrics = event.get("params", {}).get("metrics", {})
            trends = event.get("params", {}).get("trends", {})
            recs = self.generate_recommendations(metrics, trends)
            return {"status": "ok", "recommendations": recs}
        return await super().handle(event)

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = ["health_recommendations", "health_check"]

        if task_type == "health_recommendations":
            recs = self.generate_recommendations(p.get("metrics", {}), p.get("trends", {}))
            return {"status": "ok", "recommendations": recs}
        if task_type == "health_check":
            # health_check()'s own "status" field is agent liveness
            # (active/dead), a different axis than dispatch-level
            # ok/error — preserve it under "agent_status".
            check = self.health_check()
            return {**check, "agent_status": check.get("status"), "status": "ok"}

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}

    def health_check(self) -> dict[str, Any]:
        monitors = ["sleep_hygiene", "activity_exercise", "stress_management",
                     "hydration_nutrition", "ergonomics", "medical_attention",
                     "lifestyle_balance", "routine_optimization"]
        return {
            "agent": self.name,
            "district": self.district,
            "hp": self.health_points,
            "status": self.get_status(),
            "monitors": monitors,
            "llm_enabled": self._use_llm,
        }

    def fallback_chain(self) -> list[str]:
        return ["local_rules", "llm_advisor"]
