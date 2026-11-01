"""
StyleModel — absorbed from reference communications/style_model.py.
Conversation analytics, tone/formality adjustment, style comparison.
Standalone — no AgentBase. Uses Ollama directly for text rewriting.
"""
import re
import os

from loguru import logger


class StyleModel:
    """
    Analyzes conversation style and adjusts tone/formality via Ollama.
    Absorbed from reference — no HTTP dependency, no AgentBase.
    """

    TONE_LEVELS = {
        "very_formal": {
            "range": (8, 10),
            "indicators": ["sir", "madam", "hereby", "pursuant", "accordingly"],
            "avoid": ["hey", "gonna", "wanna", "lol", "yeah", "cool"],
        },
        "formal": {
            "range": (6, 8),
            "indicators": ["please", "kindly", "would appreciate", "regards", "sincerely"],
            "avoid": ["hey", "gonna", "lol", "nah", "bro", "dude"],
        },
        "neutral": {
            "range": (4, 6),
            "indicators": ["I think", "perhaps", "might be", "could consider"],
            "avoid": [],
        },
        "casual": {
            "range": (2, 4),
            "indicators": ["hey", "great", "cool", "awesome", "nice"],
            "avoid": ["sir", "madam", "hereby", "pursuant"],
        },
        "very_casual": {
            "range": (0, 2),
            "indicators": ["gonna", "wanna", "lol", "lmao", "bro", "dude", "tbh"],
            "avoid": ["sir", "madam", "please be advised"],
        },
    }

    def __init__(self):
        self._cache: list[dict] = []

    # ── Analysis ───────────────────────────────────────────────────────────────

    def analyze_conversation(self, messages: list[dict]) -> dict:
        if not messages:
            return {"status": "error", "message": "No messages", "style": {}}

        all_text = " ".join(m.get("content", "") for m in messages)
        words = all_text.split()

        formality_score = self._score_formality(all_text)
        tone_score = self._score_tone(all_text)
        emoji_count = self._count_emojis(all_text)

        analysis = {
            "message_count": len(messages),
            "metrics": {
                "total_words": len(words),
                "avg_words_per_message": round(len(words) / len(messages), 1),
                "unique_words": len(set(words)),
                "emoji_count": emoji_count,
                "emoji_frequency": round(emoji_count / len(messages), 2),
                "question_ratio": round(all_text.count("?") / len(messages), 2),
                "exclamation_ratio": round(all_text.count("!") / len(messages), 2),
                "abbreviation_frequency": self._detect_abbreviations(all_text),
            },
            "style": {
                "formality_score": formality_score,
                "formality_level": self._score_to_level(formality_score),
                "tone_score": tone_score,
                "tone": self._tone_to_label(tone_score),
                "sentence_starts": self._analyze_sentence_starts(messages),
            },
        }
        analysis["suggestions"] = self._generate_suggestions(analysis)
        return analysis

    def _score_formality(self, text: str) -> float:
        text_lower = text.lower()
        score = 5.0
        for data in self.TONE_LEVELS.values():
            for ind in data["indicators"]:
                if ind in text_lower: score += 0.5
            for av in data["avoid"]:
                if av in text_lower: score -= 0.5
        return max(0.0, min(10.0, score))

    def _score_tone(self, text: str) -> float:
        text_lower = text.lower()
        pos = ["great","awesome","amazing","love","excellent","good","nice","wonderful","thank"]
        neg = ["bad","terrible","hate","awful","horrible","angry","disappointed","fail","wrong"]
        pc = sum(1 for w in pos if w in text_lower)
        nc = sum(1 for w in neg if w in text_lower)
        if pc + nc == 0: return 5.0
        return max(0.0, min(10.0, 5.0 + (pc - nc) * 0.5))

    def _score_to_level(self, score: float) -> str:
        for name, data in self.TONE_LEVELS.items():
            lo, hi = data["range"]
            if lo <= score <= hi: return name
        return "neutral"

    def _tone_to_label(self, score: float) -> str:
        if score >= 8: return "very_positive"
        if score >= 6: return "positive"
        if score >= 4: return "neutral"
        if score >= 2: return "negative"
        return "very_negative"

    def _count_emojis(self, text: str) -> int:
        return len(re.findall(
            r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF]+",
            text, flags=re.UNICODE,
        ))

    def _analyze_sentence_starts(self, messages: list[dict]) -> dict:
        starters = {k: 0 for k in ["i","you","we","they","the","it","so","but","hey","hi"]}
        for m in messages:
            for sentence in m.get("content", "").split(".")[:3]:
                sentence = sentence.strip()
                if sentence:
                    first = sentence.split()[0].lower() if sentence.split() else ""
                    if first in starters: starters[first] += 1
        total = sum(starters.values()) or 1
        return {k: round(v / total, 2) for k, v in starters.items()}

    def _detect_abbreviations(self, text: str) -> float:
        abbrs = re.findall(
            r"\b(gonna|wanna|gotta|btw|idk|tbh|imo|lol|lmao|omg|smh)\b",
            text.lower()
        )
        return round(len(abbrs) / max(len(text.split()), 1), 4)

    def _generate_suggestions(self, analysis: dict) -> list[str]:
        suggestions = []
        level = analysis["style"]["formality_level"]
        if level in ("very_casual", "casual"):
            suggestions.append("Consider more formal language for professional contexts")
        elif level in ("very_formal", "formal"):
            suggestions.append("May be too formal for casual conversations")
        if analysis["metrics"]["emoji_frequency"] > 2:
            suggestions.append("High emoji usage — appropriate for casual chat only")
        if analysis["metrics"]["abbreviation_frequency"] > 0.05:
            suggestions.append("Heavy abbreviation use — expand for clarity in formal contexts")
        if analysis["style"]["sentence_starts"].get("i", 0) > 0.3:
            suggestions.append("Frequent 'I' statements — balance with questions")
        return suggestions

    # ── LLM-powered rewriting ──────────────────────────────────────────────────

    def suggest_tone_adjustment(self, text: str, target_tone: str) -> str:
        """Rewrite text with a different tone via Ollama."""
        tone_map = {
            "positive":     ("optimistic, encouraging phrasing", "great, excellent"),
            "negative":     ("critical, concerned phrasing", "concerns, issues"),
            "neutral":      ("balanced, objective phrasing", "consider, note"),
            "enthusiastic": ("excited, energetic phrasing", "amazing, fantastic"),
            "serious":      ("professional, focused phrasing", "important, priority"),
        }
        instruction, examples = tone_map.get(target_tone, tone_map["neutral"])
        prompt = (
            f"Rewrite the following text with a {target_tone} tone.\n"
            f"Use {instruction}. Incorporate words like: {examples}.\n"
            f"Maintain original meaning. Return ONLY the rewritten text.\n\n"
            f"Original: {text}"
        )
        return self._ollama_rewrite(prompt, fallback=text)

    def match_formality_level(self, text: str, level: str) -> str:
        """Rewrite text at the specified formality level via Ollama."""
        if level not in self.TONE_LEVELS:
            return text
        cfg = self.TONE_LEVELS[level]
        prompt = (
            f"Rewrite the following text at a {level.replace('_', ' ')} formality level.\n"
            f"Use words like: {', '.join(cfg['indicators'][:5])}.\n"
            f"Avoid words like: {', '.join(cfg['avoid'][:5]) or 'none'}.\n"
            f"Return ONLY the rewritten text.\n\nOriginal: {text}"
        )
        return self._ollama_rewrite(prompt, fallback=text)

    def compare_styles(self, messages_a: list[dict], messages_b: list[dict]) -> dict:
        """Compare two conversations. Returns compatibility_score 0-100."""
        a = self.analyze_conversation(messages_a)
        b = self.analyze_conversation(messages_b)

        formality_gap = abs(a["style"]["formality_score"] - b["style"]["formality_score"])
        tone_gap = abs(a["style"]["tone_score"] - b["style"]["tone_score"])
        verbosity_gap = abs(
            a["metrics"]["avg_words_per_message"] - b["metrics"]["avg_words_per_message"]
        )

        score = 100 - (formality_gap / 10) * 30 - (tone_gap / 10) * 30 - (verbosity_gap / 50) * 40
        score = max(0.0, min(100.0, score))

        return {
            "person_a_style": a["style"],
            "person_b_style": b["style"],
            "differences": {
                "formality_gap": round(formality_gap, 1),
                "tone_gap": round(tone_gap, 1),
                "verbosity_gap": round(verbosity_gap, 1),
            },
            "compatibility_score": round(score, 1),
        }

    def _ollama_rewrite(self, prompt: str, fallback: str) -> str:
        if os.environ.get("VECTOR_STYLE_LLM") != "1":
            return fallback

        try:
            import ollama
            from core.loop.context_engine import ContextEngine

            hydration = ContextEngine().session_hydration_prompt()
            resp = ollama.chat(
                model="vector-focus",
                messages=[
                    {"role": "system", "content": hydration},
                    {"role": "user", "content": prompt},
                ],
            )
            result = resp["message"]["content"].strip()
            return result if result else fallback
        except Exception as e:
            logger.warning(f"[VECTOR][style] ollama rewrite failed: {e}")
            return fallback


if __name__ == "__main__":
    sm = StyleModel()
    msgs = [
        {"content": "Hey! Great work on the project, it looks awesome!"},
        {"content": "Thanks for helping me out, really appreciate it!"},
        {"content": "No worries, happy to help anytime :)"},
    ]
    analysis = sm.analyze_conversation(msgs)
    assert "style" in analysis and "metrics" in analysis
    assert "formality_level" in analysis["style"]
    assert "tone" in analysis["style"]

    comparison = sm.compare_styles(msgs, msgs)
    assert "compatibility_score" in comparison
    assert comparison["compatibility_score"] == 100.0

    print(f"persona/style_model.py OK — formality={analysis['style']['formality_level']} tone={analysis['style']['tone']}")


