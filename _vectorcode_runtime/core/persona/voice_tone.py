from __future__ import annotations

from core.persona.schemas import ToneContext

__all__ = ["ToneModulator"]

_TONE_RULES: dict[str, dict[str, str]] = {
    "night": {
        "style": "softer, shorter responses; fewer proactive suggestions",
        "instructions": "Use a calm, quiet tone. Keep responses concise. Minimize unsolicited suggestions. Prefer brief confirmations.",
    },
    "morning": {
        "style": "cheerful, energizing; proactive planning",
        "instructions": "Use a warm, energizing tone. Offer proactive planning suggestions. Brief morning-relevant observations are welcome.",
    },
    "afternoon": {
        "style": "balanced, focused; standard professionalism",
        "instructions": "Use a balanced, professional tone. Focus on clarity and accuracy. Standard verbosity.",
    },
    "evening": {
        "style": "winding down; reflective, less intense",
        "instructions": "Use a relaxed, reflective tone. Wind down intensity. Offer summaries rather than new action items.",
    },
}

_URGENCY_RULES: dict[str, str] = {
    "calm": "No urgency markers needed. Standard conversational pace.",
    "normal": "Standard clarity and structure.",
    "elevated": "Be direct. Lead with the key point. Minimize preamble.",
    "critical": "Concise, action-oriented. No pleasantries. State the problem, the action, and the next step. Three sentences maximum unless more detail is requested.",
}

_MOOD_RULES: dict[str, str] = {
    "focused": "Minimize interruptions. Provide precise, technical responses. Stay on-topic.",
    "relaxed": "Conversational warmth is fine. Light observations acceptable. Standard helpfulness.",
    "stressed": "Empathetic but not patronizing. Focus on solutions, not problems. Be brief and reassuring. Avoid adding complexity.",
    "unknown": "Standard professional tone. Observe and adapt.",
}

_SOCIAL_RULES: dict[str, str] = {
    "alone": "Full personality expression. Normal verbosity and proactivity.",
    "meeting": "Minimal interruptions. Summary-only mode. Wait for explicit questions before elaborating.",
    "public": "Formal register. Professional and concise. Avoid private/personal references.",
}


class ToneModulator:
    def modulate(self, text: str, context: ToneContext) -> str:
        if not text:
            return text
        rules = self._collect_rules(context)
        prefix = ""
        if context.urgency == "critical":
            prefix = "[URGENT] "
        return prefix + text

    def get_tone_instructions(self, context: ToneContext) -> str:
        rules = self._collect_rules(context)
        lines = ["[TONE DIRECTIVES]"]
        for category, instruction in rules.items():
            lines.append(f"{category}: {instruction}")
        return "\n".join(lines)

    def _collect_rules(self, context: ToneContext) -> dict[str, str]:
        rules: dict[str, str] = {}
        time_rule = _TONE_RULES.get(context.time_of_day)
        if time_rule:
            rules["time_of_day"] = time_rule["instructions"]
        urgency_rule = _URGENCY_RULES.get(context.urgency)
        if urgency_rule:
            rules["urgency"] = urgency_rule
        mood_rule = _MOOD_RULES.get(context.owner_mood)
        if mood_rule:
            rules["owner_mood"] = mood_rule
        social_rule = _SOCIAL_RULES.get(context.social_context)
        if social_rule:
            rules["social_context"] = social_rule
        return rules

    @staticmethod
    def infer_time_of_day(hour: int) -> str:
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        return "night"
