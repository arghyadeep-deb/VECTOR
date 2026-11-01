# DORMANT (2026-09-24, docs/design/core-module-triage.md): not imported by the running VECTOR.
# Superseded by Governor routing (core/city/governor.py). Kept on purpose (personal-use build); do not add a second live path --
# route through the existing mechanism so the Governor and PermissionGateway stay the only way in.
"""
V.E.C.T.O.R. TaskRouter.
Routes incoming tasks to the appropriate district districts.
"""

__all__ = [
    "DISTRICT_KEYWORDS",
    "TaskRouter",
]

from loguru import logger
from core.config import CONFIG


DISTRICT_KEYWORDS = {
    "governance": ["council", "decision", "governance", "policy", "vote", "debate"],
    "coding": ["code", "git", "debug", "test", "review", "architect", "build", "program"],
    "calendar": ["calendar", "schedule", "event", "reminder", "deadline", "time block"],
    "security": ["security", "threat", "scan", "malware", "virus", "protect", "firewall"],
    "research": ["research", "paper", "arxiv", "news", "web", "search", "reddit"],
    "memory_curator": ["memory", "remember", "consolidate", "rag", "pattern", "graph"],
    "health": ["health", "exercise", "sleep", "fatigue", "wellness", "fitness"],
    "finance": ["budget", "expense", "upi", "money", "finance", "tax", "invest"],
    "projects": ["project", "deadline", "planning", "doc", "documentation", "progress"],
    "reflection": ["reflect", "journal", "review", "grow", "learn", "insight"],
    "communications": ["message", "vectorcode", "communicate", "style", "person", "email"],
    "content": ["video", "script", "caption", "upload", "youtube", "content", "thumbnail"],
    "calls": ["call", "voice", "transcribe", "respond", "screener"],
    "interview_prep": ["interview", "mock", "company", "feedback", "question"],
    "investment": ["stock", "market", "invest", "sentiment", "technical", "fundamental"],
    "learning": ["course", "learn", "note", "concept", "video"],
    "startups": ["startup", "idea", "revenue", "competitor", "market"],
    "privacy": ["privacy", "gdpr", "pii", "data", "leak"],
    "relationships": ["contact", "relationship", "communication", "reconnect"],
    "skills": ["skill", "mastery", "gap", "track"],
    "languages": ["language", "hindi", "english", "japanese", "coach"],
    "news_trends": ["news", "trend", "opportunity", "market"],
    "pattern_detective": ["pattern", "habit", "behavior"],
    "devops": ["deploy", "scale", "rollback", "health"],
    "data_analytics": ["analytics", "dataset", "dashboard", "anomaly"],
    "ux_writing": ["ux", "writing", "button", "error", "tooltip"],
    "product": ["product", "spec", "feature", "roadmap", "feedback"],
    "qa_testing": ["test", "qa", "bug", "smoke"],
    "legal": ["legal", "terms", "compliance", "policy"],
    "accessibility": ["accessibility", "a11y", "contrast", "screen reader"],
    "karpathy_lab": ["train", "model", "architecture", "data prep"],
}


class TaskRouter:
    """Routes user tasks to the correct district based on keywords."""

    def __init__(self):
        self._district_keywords = DISTRICT_KEYWORDS
        logger.info("[VECTOR][task_router] TaskRouter initialized")

    def route(self, task_description: str) -> list[str]:
        """
        Route a task description to matching districts.
        Returns a list of district names (best match first).
        """
        text = task_description.lower()
        scores: dict[str, float] = {}
        for district, keywords in self._district_keywords.items():
            score = sum(1.0 for kw in keywords if kw in text)
            if score > 0:
                scores[district] = score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        results = [d for d, s in ranked]
        if not results:
            results = ["reflection"]
        logger.info(f"[VECTOR][task_router] Routed '{task_description[:50]}' -> {results}")
        return results

    def add_keyword(self, district: str, keyword: str):
        """Add a keyword mapping for a district."""
        if district in self._district_keywords:
            self._district_keywords[district].append(keyword)
            logger.info(f"[VECTOR][task_router] Added keyword '{keyword}' to {district}")


if __name__ == "__main__":
    r = TaskRouter()
    print(r.route("I need help with my Python code and fixing a bug"))
    print(r.route("Schedule a meeting for tomorrow at 3pm"))
