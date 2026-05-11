import sys
import uuid
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.obsidian_sync import ObsidianSync


class PersonModel(AgentBase):
    """
    Builds and maintains communication style profiles for people.
    Learns from message history and generates text matching their style.
    """

    def __init__(self, ghost: dict = None):
        super().__init__(str(uuid.uuid4()), "PersonModel", "communications")
        if ghost:
            self.inherit_ghost(ghost)

        self._profiles: dict[str, dict] = {}
        self._obsidian = ObsidianSync()
        self._profile_dir = "Research/PersonModels"
        self._load_profiles()
        logger.info("[VECTOR][person_model] PersonModel initialized")

    def _load_profiles(self) -> None:
        """Load existing person profiles from Obsidian vault."""
        try:
            profile_path = self._obsidian._vault / self._profile_dir
            if profile_path.exists():
                for json_file in profile_path.glob("*.json"):
                    person_name = json_file.stem
                    with open(json_file, "r", encoding="utf-8") as f:
                        self._profiles[person_name] = json.load(f)
            logger.info(f"[VECTOR][person_model] Loaded {len(self._profiles)} profiles")
        except Exception as e:
            logger.warning(f"[VECTOR][person_model] Failed to load profiles: {e}")

    def _save_profile(self, person_name: str) -> bool:
        """Save person profile to Obsidian vault."""
        if person_name not in self._profiles:
            return False

        try:
            profile_path = self._obsidian._vault / self._profile_dir
            profile_path.mkdir(parents=True, exist_ok=True)

            file_path = profile_path / f"{person_name}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self._profiles[person_name], f, indent=2)

            logger.info(f"[VECTOR][person_model] Saved profile for {person_name}")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][person_model] Failed to save profile: {e}")
            return False

    def learn_from_messages(self, person_name: str, messages: list[dict]) -> dict:
        """
        Learn communication style from a list of messages.
        Messages should be dicts with 'content' and optionally 'timestamp'.
        """
        if not messages:
            return {"status": "error", "message": "No messages provided"}

        person_name = person_name.strip().title()

        if person_name not in self._profiles:
            self._profiles[person_name] = {
                "name": person_name,
                "created_at": self._get_timestamp(),
                "message_count": 0,
                "style": {},
                "vocabulary": [],
                "patterns": [],
                "topics": []
            }

        profile = self._profiles[person_name]
        profile["message_count"] += len(messages)
        profile["last_updated"] = self._get_timestamp()

        all_text = " ".join(msg.get("content", "") for msg in messages)
        words = all_text.lower().split()

        profile["vocabulary"] = list(set(profile["vocabulary"] + words))[-500:]

        tone_analysis = self._analyze_tone(messages)
        profile["style"]["tone"] = tone_analysis

        formality = self._analyze_formality(messages)
        profile["style"]["formality"] = formality

        emoji_usage = self._analyze_emoji_usage(messages)
        profile["style"]["emoji_frequency"] = emoji_usage

        greeting_pattern = self._analyze_greetings(messages)
        profile["patterns"].append(greeting_pattern)

        response_length = self._analyze_response_length(messages)
        profile["style"]["avg_response_length"] = response_length

        topics = self._extract_topics(all_text)
        profile["topics"] = list(set(profile["topics"] + topics))[:50]

        self._save_profile(person_name)
        self.award_points(len(messages), "style_learned")

        return {
            "status": "success",
            "person": person_name,
            "messages_analyzed": len(messages),
            "style_summary": profile["style"]
        }

    def _analyze_tone(self, messages: list[dict]) -> str:
        """Analyze the overall tone of messages."""
        all_text = " ".join(msg.get("content", "") for msg in messages).lower()

        positive_words = ["great", "awesome", "amazing", "love", "excellent", "good", "nice", "thanks", "thank"]
        negative_words = ["bad", "terrible", "hate", "awful", "horrible", "sad", "angry", "disappointed"]
        neutral_words = ["ok", "okay", "sure", "maybe", "perhaps", "could", "would"]

        positive_count = sum(1 for word in positive_words if word in all_text)
        negative_count = sum(1 for word in negative_words if word in all_text)

        if positive_count > negative_count * 2:
            return "positive"
        elif negative_count > positive_count * 2:
            return "negative"
        return "neutral"

    def _analyze_formality(self, messages: list[dict]) -> str:
        """Analyze formality level of messages."""
        all_text = " ".join(msg.get("content", "") for msg in messages).lower()

        formal_indicators = ["would", "could", "please", "kindly", "appreciate", "regards", "sincerely"]
        informal_indicators = ["hey", "gonna", "wanna", "lol", "lmao", "bro", "dude", "yeah", "nah"]

        formal_count = sum(1 for word in formal_indicators if word in all_text)
        informal_count = sum(1 for word in informal_indicators if word in all_text)

        if formal_count > informal_count * 2:
            return "formal"
        elif informal_count > formal_count * 2:
            return "casual"
        return "mixed"

    def _analyze_emoji_usage(self, messages: list[dict]) -> float:
        """Calculate emoji frequency per message."""
        import re
        total_messages = len(messages)
        if total_messages == 0:
            return 0.0

        emoji_count = 0
        for msg in messages:
            content = msg.get("content", "")
            emoji_count += len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF]', content))

        return round(emoji_count / total_messages, 2)

    def _analyze_greetings(self, messages: list[dict]) -> dict:
        """Extract greeting patterns."""
        import re
        greetings = []
        for msg in messages[:10]:
            content = msg.get("content", "").strip()
            if content:
                first_word = content.split()[0].lower() if content.split() else ""
                if first_word in ["hi", "hey", "hello", "yo", "sup", "what's"]:
                    greetings.append(first_word)

        return {
            "type": "greeting",
            "common_greetings": list(set(greetings))[:5]
        }

    def _analyze_response_length(self, messages: list[dict]) -> float:
        """Calculate average response length in words."""
        if not messages:
            return 0.0

        total_words = sum(
            len(msg.get("content", "").split())
            for msg in messages
        )
        return round(total_words / len(messages), 1)

    def _extract_topics(self, text: str) -> list[str]:
        """Extract common topics from text using simple keyword extraction."""
        common_topics = {
            "work": ["work", "job", "office", "project", "meeting", "deadline", "client"],
            "technology": ["code", "computer", "software", "programming", "ai", "python", "api"],
            "personal": ["family", "friend", "birthday", "vacation", "holiday", "weekend"],
            "education": ["study", "exam", "college", "university", "kiit", "course", "class"],
            "entertainment": ["movie", "game", "music", "sport", "fitness", "gym"],
            "food": ["food", "eat", "restaurant", "dinner", "lunch", "breakfast", "coffee"],
            "finance": ["money", "investment", "stock", "bitcoin", "trading", "profit"]
        }

        text_lower = text.lower()
        found_topics = []
        for topic, keywords in common_topics.items():
            if any(kw in text_lower for kw in keywords):
                found_topics.append(topic)

        return found_topics

    def get_style(self, person_name: str) -> dict:
        """
        Get the communication style profile for a person.
        Returns empty dict if person not found.
        """
        person_name = person_name.strip().title()
        return self._profiles.get(person_name, {}).get("style", {})

    def generate_response_style(self, person_name: str, text: str) -> str:
        """
        Generate a response that matches the person's communication style.
        Uses Ollama to adapt the text to match the stored style profile.
        """
        person_name = person_name.strip().title()
        if person_name not in self._profiles:
            logger.warning(f"[VECTOR][person_model] Unknown person: {person_name}")
            return text

        profile = self._profiles[person_name]
        style = profile.get("style", {})
        formality = style.get("formality", "mixed")
        tone = style.get("tone", "neutral")
        vocabulary = profile.get("vocabulary", [])[:50]

        prompt = f"""Rewrite the following message to match this person's communication style.

Original message: {text}

Person's style:
- Formality: {formality}
- Tone: {tone}
- Common words: {', '.join(vocabulary[:20])}
- Emoji frequency: {style.get('emoji_frequency', 0)}

Return ONLY the rewritten message, no explanations."""

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
            adapted_text = result.get("response", "").strip()

            self.award_points(5, "response_style_generated")
            return adapted_text

        except Exception as e:
            logger.error(f"[VECTOR][person_model] Style generation failed: {e}")
            return text

    def list_profiles(self) -> list[str]:
        """List all person profiles."""
        return list(self._profiles.keys())

    def delete_profile(self, person_name: str) -> bool:
        """Delete a person profile."""
        person_name = person_name.strip().title()
        if person_name in self._profiles:
            del self._profiles[person_name]
            profile_path = self._obsidian._vault / self._profile_dir / f"{person_name}.json"
            if profile_path.exists():
                profile_path.unlink()
            logger.info(f"[VECTOR][person_model] Deleted profile for {person_name}")
            return True
        return False

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    model = PersonModel()

    sample_messages = [
        {"content": "Hey! How's it going?", "timestamp": "2024-01-01T10:00:00Z"},
        {"content": "Great work on the project, thanks for helping out!", "timestamp": "2024-01-01T10:05:00Z"},
        {"content": "No worries at all, happy to help", "timestamp": "2024-01-01T10:10:00Z"},
        {"content": "Hey what's up? Got a minute?", "timestamp": "2024-01-01T14:00:00Z"}
    ]

    result = model.learn_from_messages("TestPerson", sample_messages)
    print(f"Learned from {result['messages_analyzed']} messages")

    style = model.get_style("TestPerson")
    print(f"Style: {style}")

    print("✅ person_model.py OK")
