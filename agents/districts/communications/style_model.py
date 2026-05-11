import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase

from pathlib import Path


class StyleModel(AgentBase):
    """
    Global communication style analyzer and tone adjustment engine.
    Analyzes conversation style and suggests/adjusts tone for any context.
    """

    TONE_LEVELS = {
        "very_formal": {
            "range": (8, 10),
            "indicators": ["sir", "madam", "hereby", "pursuant", "accordingly", "henceforth"],
            "avoid": ["hey", "gonna", "wanna", "lol", "yeah", "cool", "awesome"]
        },
        "formal": {
            "range": (6, 8),
            "indicators": ["please", "kindly", "would appreciate", "regards", "sincerely"],
            "avoid": ["hey", "gonna", "lol", "nah", "bro", "dude"]
        },
        "neutral": {
            "range": (4, 6),
            "indicators": ["I think", "perhaps", "might be", "could consider"],
            "avoid": []
        },
        "casual": {
            "range": (2, 4),
            "indicators": ["hey", "great", "cool", "awesome", "nice", "probably"],
            "avoid": ["sir", "madam", "hereby", "pursuant"]
        },
        "very_casual": {
            "range": (0, 2),
            "indicators": ["gonna", "wanna", "lol", "lmao", "haha", "bro", "dude", "tbh", "imo"],
            "avoid": ["sir", "madam", "please be advised", "pursuant to"]
        }
    }

    def __init__(self, ghost: dict = None):
        super().__init__(str(uuid.uuid4()), "StyleModel", "communications")
        if ghost:
            self.inherit_ghost(ghost)

        self._style_config = CONFIG.get("communication_styles", {})
        self._conversation_cache: list[dict] = []
        self._default_tone = self._style_config.get("default_tone", "neutral")
        self._default_formality = self._style_config.get("default_formality", "neutral")
        logger.info("[VECTOR][style_model] StyleModel initialized")

    def analyze_conversation(self, messages: list[dict]) -> dict:
        """
        Analyze a list of messages to extract overall style attributes.
        Returns comprehensive style analysis.
        """
        if not messages:
            return {
                "status": "error",
                "message": "No messages provided",
                "style": {}
            }

        analysis = {
            "message_count": len(messages),
            "style": {},
            "metrics": {},
            "suggestions": []
        }

        all_text = " ".join(msg.get("content", "") for msg in messages)
        words = all_text.split()

        analysis["metrics"]["total_words"] = len(words)
        analysis["metrics"]["avg_words_per_message"] = round(len(words) / len(messages), 1)
        analysis["metrics"]["unique_words"] = len(set(words))

        formality_score = self._score_formality(all_text)
        analysis["style"]["formality_score"] = formality_score
        analysis["style"]["formality_level"] = self._score_to_level(formality_score)

        tone_score = self._score_tone(all_text)
        analysis["style"]["tone_score"] = tone_score
        analysis["style"]["tone"] = self._tone_score_to_label(tone_score)

        emoji_count = self._count_emojis(all_text)
        analysis["metrics"]["emoji_count"] = emoji_count
        analysis["metrics"]["emoji_frequency"] = round(emoji_count / len(messages), 2)

        question_count = all_text.count("?")
        analysis["metrics"]["question_ratio"] = round(question_count / len(messages), 2)

        exclamation_count = all_text.count("!")
        analysis["metrics"]["exclamation_ratio"] = round(exclamation_count / len(messages), 2)

        sentence_starts = self._analyze_sentence_starts(messages)
        analysis["style"]["sentence_starts"] = sentence_starts

        abbreviation_usage = self._detect_abbreviations(all_text)
        analysis["metrics"]["abbreviation_frequency"] = abbreviation_usage

        analysis["suggestions"] = self._generate_style_suggestions(analysis)

        self._conversation_cache.append({
            "timestamp": self._get_timestamp(),
            "analysis": analysis
        })

        self.award_points(min(len(messages), 10), "conversation_analyzed")
        logger.info(f"[VECTOR][style_model] Analyzed {len(messages)} messages")

        return analysis

    def _score_formality(self, text: str) -> float:
        """Score text formality from 0 (casual) to 10 (formal)."""
        text_lower = text.lower()
        score = 5.0

        for level_name, level_data in self.TONE_LEVELS.items():
            indicators = level_data["indicators"]
            avoid = level_data["avoid"]

            for ind in indicators:
                if ind in text_lower:
                    score += 0.5

            for av in avoid:
                if av in text_lower:
                    score -= 0.5

        return max(0.0, min(10.0, score))

    def _score_tone(self, text: str) -> float:
        """Score text tone from 0 (negative) to 10 (positive)."""
        text_lower = text.lower()

        positive_words = [
            "great", "awesome", "amazing", "love", "excellent", "good", "nice",
            "wonderful", "fantastic", "perfect", "happy", "excited", "thank",
            "thanks", "appreciate", "helpful", "best", "brilliant"
        ]

        negative_words = [
            "bad", "terrible", "hate", "awful", "horrible", "sad", "angry",
            "disappointed", "frustrating", "annoying", "worst", "sucks", "stupid",
            "boring", "difficult", "problem", "issue", "fail", "wrong"
        ]

        pos_count = sum(1 for word in positive_words if word in text_lower)
        neg_count = sum(1 for word in negative_words if word in text_lower)

        if pos_count + neg_count == 0:
            return 5.0

        score = 5.0 + (pos_count - neg_count) * 0.5
        return max(0.0, min(10.0, score))

    def _score_to_level(self, score: float) -> str:
        """Convert formality score to level name."""
        for level_name, level_data in self.TONE_LEVELS.items():
            min_val, max_val = level_data["range"]
            if min_val <= score <= max_val:
                return level_name
        return "neutral"

    def _tone_score_to_label(self, score: float) -> str:
        """Convert tone score to descriptive label."""
        if score >= 8:
            return "very_positive"
        elif score >= 6:
            return "positive"
        elif score >= 4:
            return "neutral"
        elif score >= 2:
            return "negative"
        return "very_negative"

    def _count_emojis(self, text: str) -> int:
        """Count emojis in text."""
        import re
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE
        )
        return len(emoji_pattern.findall(text))

    def _analyze_sentence_starts(self, messages: list[dict]) -> dict:
        """Analyze how sentences typically start."""
        starters = {
            "i": 0, "you": 0, "we": 0, "they": 0, "the": 0,
            "it": 0, "so": 0, "but": 0, "hey": 0, "hi": 0, "hello": 0
        }

        for msg in messages:
            content = msg.get("content", "")
            sentences = content.split(".")
            for sentence in sentences[:3]:
                sentence = sentence.strip()
                if sentence:
                    first_word = sentence.split()[0].lower() if sentence.split() else ""
                    if first_word in starters:
                        starters[first_word] += 1

        total = sum(starters.values())
        if total > 0:
            return {k: round(v / total, 2) for k, v in starters.items()}
        return starters

    def _detect_abbreviations(self, text: str) -> float:
        """Detect abbreviation frequency in text."""
        import re
        abbreviations = re.findall(
            r'\b(gonna|wanna|gotta|ima|btw|idk|imho|tbh|imo|etc|vs|eg|i\.e|e\.g)\b',
            text.lower()
        )
        word_count = len(text.split())
        return round(len(abbreviations) / max(word_count, 1), 4)

    def _generate_style_suggestions(self, analysis: dict) -> list[str]:
        """Generate suggestions based on style analysis."""
        suggestions = []
        style = analysis["style"]
        metrics = analysis["metrics"]

        formality = style.get("formality_level", "neutral")
        if formality in ["very_casual", "casual"]:
            suggestions.append("Consider using more formal language for professional contexts")
        elif formality in ["very_formal", "formal"]:
            suggestions.append("May be too formal for friendly conversations")

        if metrics.get("emoji_frequency", 0) > 2:
            suggestions.append("High emoji usage detected - appropriate for casual chat")

        if metrics.get("abbreviation_frequency", 0) > 0.05:
            suggestions.append("Heavy abbreviation use - consider expanding for clarity")

        sentence_starts = style.get("sentence_starts", {})
        if sentence_starts.get("i", 0) > 0.3:
            suggestions.append("Frequent 'I' statements - balance with questions about the other person")

        return suggestions

    def suggest_tone_adjustment(self, text: str, target_tone: str) -> str:
        """
        Rewrite text with adjusted tone.
        Target tone: 'positive', 'negative', 'neutral', 'enthusiastic', 'serious'
        """
        tone_map = {
            "positive": ("more optimistic phrasing", "great, excellent"),
            "negative": ("more critical phrasing", "concerns, issues"),
            "neutral": ("balanced, objective phrasing", "consider, note"),
            "enthusiastic": ("excited, energetic phrasing", "amazing, fantastic"),
            "serious": ("professional, focused phrasing", "important, priority")
        }

        tone_instruction, example_words = tone_map.get(target_tone, tone_map["neutral"])

        prompt = f"""Rewrite the following text with a {target_tone} tone.

Instructions:
- Use {tone_instruction}
- Incorporate words like: {example_words}
- Maintain the original meaning
- Keep similar length

Original text:
{text}

Return ONLY the rewritten text."""

        try:
            import httpx

            ollama_host = CONFIG["ollama_host"]
            if not ollama_host.startswith("http"):
                ollama_host = "http://" + ollama_host

            model = CONFIG["models"]["focus"]

            response = httpx.post(
                f"{ollama_host}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()
            adjusted_text = result.get("response", "").strip()

            self.award_points(5, "tone_adjusted")
            return adjusted_text

        except Exception as e:
            logger.error(f"[VECTOR][style_model] Tone adjustment failed: {e}")
            return text

    def match_formality_level(self, text: str, level: str) -> str:
        """
        Rewrite text at specified formality level.
        Level: 'very_formal', 'formal', 'neutral', 'casual', 'very_casual'
        """
        if level not in self.TONE_LEVELS:
            logger.warning(f"[VECTOR][style_model] Unknown formality level: {level}")
            return text

        level_config = self.TONE_LEVELS[level]
        indicators = ", ".join(level_config["indicators"][:5])
        avoid = ", ".join(level_config["avoid"][:5])

        prompt = f"""Rewrite the following text at a {level.replace('_', ' ')} formality level.

Formality requirements:
- Use these types of words: {indicators}
- Avoid these types of words: {avoid}

Original text:
{text}

Return ONLY the rewritten text, maintaining the original meaning."""

        try:
            import httpx

            ollama_host = CONFIG["ollama_host"]
            if not ollama_host.startswith("http"):
                ollama_host = "http://" + ollama_host

            model = CONFIG["models"]["focus"]

            response = httpx.post(
                f"{ollama_host}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()
            rewritten_text = result.get("response", "").strip()

            self.award_points(5, "formality_adjusted")
            return rewritten_text

        except Exception as e:
            logger.error(f"[VECTOR][style_model] Formality adjustment failed: {e}")
            return text

    def compare_styles(self, messages_a: list[dict], messages_b: list[dict]) -> dict:
        """Compare communication styles between two sets of messages."""
        analysis_a = self.analyze_conversation(messages_a)
        analysis_b = self.analyze_conversation(messages_b)

        comparison = {
            "person_a": analysis_a["style"],
            "person_b": analysis_b["style"],
            "differences": {}
        }

        style_a = analysis_a["style"]
        style_b = analysis_b["style"]

        formality_diff = abs(
            style_a.get("formality_score", 5) - style_b.get("formality_score", 5)
        )
        comparison["differences"]["formality_gap"] = round(formality_diff, 1)

        tone_diff = abs(
            style_a.get("tone_score", 5) - style_b.get("tone_score", 5)
        )
        comparison["differences"]["tone_gap"] = round(tone_diff, 1)

        metrics_a = analysis_a["metrics"]
        metrics_b = analysis_b["metrics"]

        length_diff = abs(
            metrics_a.get("avg_words_per_message", 0) - metrics_b.get("avg_words_per_message", 0)
        )
        comparison["differences"]["verbosity_gap"] = round(length_diff, 1)

        comparison["compatibility_score"] = self._calculate_compatibility(comparison["differences"])

        return comparison

    def _calculate_compatibility(self, differences: dict) -> float:
        """Calculate style compatibility score (0-100)."""
        max_gap = 10.0

        formality_penalty = (differences.get("formality_gap", 0) / max_gap) * 30
        tone_penalty = (differences.get("tone_gap", 0) / max_gap) * 30
        verbosity_penalty = (differences.get("verbosity_gap", 0) / 50) * 40

        score = 100 - (formality_penalty + tone_penalty + verbosity_penalty)
        return max(0.0, min(100.0, score))

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    model = StyleModel()

    messages = [
        {"content": "Hey! Great work on the project, it looks awesome!"},
        {"content": "Thanks for helping me out, really appreciate it!"},
        {"content": "No worries, happy to help anytime :)"}
    ]

    analysis = model.analyze_conversation(messages)
    print(f"Formality: {analysis['style']['formality_level']}")
    print(f"Tone: {analysis['style']['tone']}")
    print(f"Suggestions: {analysis['suggestions']}")

    adjusted = model.suggest_tone_adjustment("The project is done.", "enthusiastic")
    print(f"Adjusted: {adjusted}")

    print("✅ style_model.py OK")
