import sys
import uuid
import json
from pathlib import Path
from typing import Optional

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory


class FeedbackAnalyst(AgentBase):
    """
    Analyzes interview feedback, identifies improvement areas,
    and tracks progress over time.
    """

    IMPROVEMENT_CATEGORIES = [
        "technical_skills", "communication", "problem_solving",
        "behavioral", "cultural_fit", "confidence", "time_management",
        "follow_up_questions", "examples", "star_format"
    ]

    def __init__(self, ghost: dict = None):
        super().__init__(str(uuid.uuid4()), "FeedbackAnalyst", "interview_prep")
        if ghost:
            self.inherit_ghost(ghost)

        self._feedback_entries: list[dict] = []
        self._improvement_tracking: dict[str, list[dict]] = {cat: [] for cat in self.IMPROVEMENT_CATEGORIES}
        self._episodic = EpisodicMemory()
        self._data_file = Path(__file__).parent.parent.parent.parent / "data" / "interview_feedback.json"
        self._load_data()
        logger.info(f"[VECTOR][feedback_analyst] FeedbackAnalyst initialized")

    def _load_data(self) -> None:
        """Load feedback data from storage."""
        if self._data_file.exists():
            try:
                with open(self._data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._feedback_entries = data.get("feedback", [])
                    self._improvement_tracking = data.get("tracking", self._improvement_tracking)
                logger.info(f"[VECTOR][feedback_analyst] Loaded {len(self._feedback_entries)} feedback entries")
            except Exception as e:
                logger.error(f"[VECTOR][feedback_analyst] Failed to load data: {e}")

    def _save_data(self) -> bool:
        """Save feedback data to storage."""
        try:
            self._data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._data_file, "w", encoding="utf-8") as f:
                json.dump({
                    "feedback": self._feedback_entries[-500:],
                    "tracking": self._improvement_tracking
                }, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"[VECTOR][feedback_analyst] Failed to save data: {e}")
            return False

    def analyze_feedback(self, text: str) -> dict:
        """
        Analyze interview feedback text and extract structured insights.
        """
        prompt = f"""Analyze this interview feedback and extract structured insights.

Feedback:
{text}

Provide analysis in this format:
AREAS_STRONG: List of strong areas (bullet points)
AREAS_IMPROVE: List of areas needing improvement (bullet points)
SKILLS_TO_PRACTICE: Specific skills to practice (numbered list)
OVERALL_SCORE: Numerical score 1-10
KEY_TAKEAWAY: One sentence summary
CATEGORIES: Which of these categories apply (comma-separated):
- technical_skills, communication, problem_solving, behavioral,
- cultural_fit, confidence, time_management, follow_up_questions,
- examples, star_format

Be specific and actionable in your analysis.
"""

        try:
            import httpx

            ollama_host = CONFIG["ollama_host"]
            if not ollama_host.startswith("http"):
                ollama_host = "http://" + ollama_host

            model = CONFIG["models"]["focus"]

            response = httpx.post(
                f"{ollama_host}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=60.0
            )
            response.raise_for_status()
            result = response.json()
            analysis_text = result.get("response", "").strip()

            analysis = self._parse_analysis(analysis_text, text)

            entry = {
                "id": str(uuid.uuid4()),
                "original_feedback": text,
                "analysis": analysis,
                "categories": analysis.get("categories", []),
                "score": analysis.get("overall_score", 5),
                "timestamp": self._get_timestamp()
            }

            self._feedback_entries.append(entry)
            self._update_tracking(entry)
            self._save_data()

            self.award_points(10, "feedback_analyzed")
            logger.info(f"[VECTOR][feedback_analyst] Analyzed feedback: score={entry['score']}")

            return entry

        except Exception as e:
            logger.error(f"[VECTOR][feedback_analyst] Analysis failed: {e}")
            return {"original_feedback": text, "error": str(e)}

    def _parse_analysis(self, analysis_text: str, original: str) -> dict:
        """Parse LLM analysis into structured format."""
        analysis = {
            "strong_areas": [],
            "improve_areas": [],
            "skills_to_practice": [],
            "overall_score": 5,
            "key_takeaway": "",
            "categories": [],
            "full_text": analysis_text
        }

        lines = analysis_text.split("\n")
        current_section = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            line_lower = line.lower()

            if "area_strong" in line_lower:
                current_section = "strong"
            elif "area_improve" in line_lower or "area_to_improve" in line_lower:
                current_section = "improve"
            elif "skill_to_practice" in line_lower or "practice" in line_lower:
                current_section = "skill"
            elif "score" in line_lower and ":" in line:
                import re
                match = re.search(r'\d+', line)
                if match:
                    analysis["overall_score"] = min(10, max(1, int(match.group())))
            elif "takeaway" in line_lower or "summary" in line_lower:
                analysis["key_takeaway"] = line.split(":", 1)[-1].strip()
            elif "category" in line_lower:
                cats = line.split(":", 1)[-1].strip()
                analysis["categories"] = [c.strip() for c in cats.split(",")]
            elif current_section == "strong" and (line.startswith("-") or line[0].isdigit()):
                analysis["strong_areas"].append(line.lstrip("-0123456789. )").strip())
            elif current_section == "improve" and (line.startswith("-") or line[0].isdigit()):
                analysis["improve_areas"].append(line.lstrip("-0123456789. )").strip())
            elif current_section == "skill" and (line.startswith("-") or line[0].isdigit()):
                analysis["skills_to_practice"].append(line.lstrip("-0123456789. )").strip())

        return analysis

    def identify_improvements(self, feedback: str) -> dict:
        """
        Identify specific improvement areas from feedback.
        """
        analysis = self.analyze_feedback(feedback)
        return {
            "status": "success",
            "areas_to_improve": analysis.get("improve_areas", []),
            "skills_to_practice": analysis.get("skills_to_practice", []),
            "recommended_resources": self._suggest_resources(analysis.get("categories", [])),
            "practice_plan": self._create_practice_plan(analysis.get("improve_areas", []))
        }

    def _suggest_resources(self, categories: list[str]) -> list[dict]:
        """Suggest resources based on improvement categories."""
        resource_map = {
            "technical_skills": [
                {"type": "practice", "resource": "LeetCode/HackerRank", "focus": "Coding problems"},
                {"type": "course", "resource": "Coursera/edX", "focus": "Technical fundamentals"}
            ],
            "communication": [
                {"type": "practice", "resource": "Speak out loud", "focus": "Verbal articulation"},
                {"type": "book", "resource": "Crucial Conversations", "focus": "High-stakes communication"}
            ],
            "problem_solving": [
                {"type": "practice", "resource": "Brain teasers", "focus": "Analytical thinking"},
                {"type": "course", "resource": "AlgoExpert", "focus": "Problem-solving patterns"}
            ],
            "behavioral": [
                {"type": "practice", "resource": "STAR method practice", "focus": "Behavioral stories"},
                {"type": "book", "resource": "Interview Gold", "focus": "Behavioral prep"}
            ],
            "confidence": [
                {"type": "practice", "resource": "Mock interviews", "focus": "Real-time practice"},
                {"type": "tip", "resource": "Power posing", "focus": "Body language"}
            ],
            "star_format": [
                {"type": "guide", "resource": "STAR method guide", "focus": "Structured responses"},
                {"type": "practice", "resource": "Write 10 STAR stories", "focus": "Story preparation"}
            ]
        }

        suggestions = []
        for cat in categories:
            if cat in resource_map:
                suggestions.extend(resource_map[cat])

        return suggestions[:10]

    def _create_practice_plan(self, improve_areas: list[str]) -> list[str]:
        """Create a practice plan based on improvement areas."""
        plan = []

        for i, area in enumerate(improve_areas[:5], 1):
            plan.append(f"Week {i}: Focus on '{area}'")
            plan.append(f"  - Practice 30 minutes daily")
            plan.append(f"  - Get feedback from mock interview")
            plan.append(f"  - Track improvement in session")

        return plan

    def _update_tracking(self, entry: dict) -> None:
        """Update improvement tracking with new feedback."""
        categories = entry.get("categories", [])
        score = entry.get("score", 5)

        for cat in categories:
            if cat in self._improvement_tracking:
                self._improvement_tracking[cat].append({
                    "timestamp": entry["timestamp"],
                    "score": score,
                    "feedback_id": entry["id"]
                })

                if len(self._improvement_tracking[cat]) > 100:
                    self._improvement_tracking[cat] = self._improvement_tracking[cat][-50:]

    def track_progress(self) -> dict:
        """
        Track improvement progress over time.
        """
        if not self._feedback_entries:
            return {
                "status": "no_data",
                "message": "No feedback entries to analyze"
            }

        recent_entries = self._feedback_entries[-10:]
        avg_recent_score = sum(e.get("score", 0) for e in recent_entries) / len(recent_entries)

        older_entries = self._feedback_entries[:-10] if len(self._feedback_entries) > 10 else []
        avg_past_score = sum(e.get("score", 0) for e in older_entries) / max(len(older_entries), 1)

        progress = avg_recent_score - avg_past_score

        category_progress = {}
        for cat, entries in self._improvement_tracking.items():
            if len(entries) >= 2:
                recent = entries[-1]["score"]
                past = entries[0]["score"]
                category_progress[cat] = {
                    "current": recent,
                    "initial": past,
                    "change": recent - past,
                    "trend": "improving" if recent > past else "declining" if recent < past else "stable"
                }

        return {
            "status": "success",
            "total_feedback_entries": len(self._feedback_entries),
            "overall_score": {
                "recent_avg": round(avg_recent_score, 1),
                "past_avg": round(avg_past_score, 1),
                "progress": round(progress, 1),
                "trend": "improving" if progress > 0 else "declining" if progress < 0 else "stable"
            },
            "category_progress": category_progress,
            "strongest_areas": self._get_strongest_areas(),
            "weakest_areas": self._get_weakest_areas(),
            "recommendations": self._generate_recommendations(category_progress)
        }

    def _get_strongest_areas(self) -> list[str]:
        """Get areas with highest recent scores."""
        scores = {}
        for cat, entries in self._improvement_tracking.items():
            if entries:
                scores[cat] = entries[-1]["score"]

        sorted_areas = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [area for area, score in sorted_areas[:3]]

    def _get_weakest_areas(self) -> list[str]:
        """Get areas with lowest recent scores."""
        scores = {}
        for cat, entries in self._improvement_tracking.items():
            if entries:
                scores[cat] = entries[-1]["score"]

        sorted_areas = sorted(scores.items(), key=lambda x: x[1])
        return [area for area, score in sorted_areas[:3]]

    def _generate_recommendations(self, category_progress: dict) -> list[str]:
        """Generate recommendations based on progress."""
        recs = []

        for cat, data in category_progress.items():
            if data["trend"] == "declining":
                recs.append(f"Focus more practice on {cat.replace('_', ' ')} - showing decline")

        declining_count = sum(1 for d in category_progress.values() if d["trend"] == "declining")
        if declining_count == 0:
            recs.append("Great job! All areas showing improvement. Keep up the momentum.")

        return recs

    def get_feedback_history(self, limit: int = 50) -> list[dict]:
        """Get feedback history."""
        return sorted(
            self._feedback_entries[-limit:],
            key=lambda x: x["timestamp"],
            reverse=True
        )

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


    async def run(self, task: dict) -> dict:
        result = self.track_progress()
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    analyst = FeedbackAnalyst()

    feedback = "The candidate showed strong technical skills but struggled with behavioral questions. Communication was clear but they could work on providing more specific examples."

    analysis = analyst.analyze_feedback(feedback)
    print(f"Analysis score: {analysis.get('score', 'N/A')}")

    progress = analyst.track_progress()
    print(f"Progress trend: {progress.get('overall_score', {}).get('trend', 'N/A')}")

    print("✅ feedback_analyst.py OK")
