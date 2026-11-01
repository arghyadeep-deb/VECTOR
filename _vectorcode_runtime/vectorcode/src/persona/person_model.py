"""
PersonModel — absorbed from reference communications/person_model.py.
Builds per-person communication style profiles. Standalone, no AgentBase.
Stores profiles in ~/.vector/personas/ (no Obsidian dependency).
"""
import re
import json
from pathlib import Path

from loguru import logger

_STORE = Path.home() / ".vector" / "personas"


class PersonModel:
    """
    Learns communication style profiles from message history.
    Generates style-matched responses via local Ollama.
    """

    def __init__(self):
        _STORE.mkdir(parents=True, exist_ok=True)
        self._profiles: dict[str, dict] = {}
        self._load_profiles()

    # ── Persistence ────────────────────────────────────────────────────────────

    def _load_profiles(self) -> None:
        for f in _STORE.glob("*.json"):
            try:
                self._profiles[f.stem] = json.loads(f.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"[VECTOR][persona] load failed {f}: {e}")

    def _save_profile(self, person_name: str) -> None:
        try:
            self._profile_path(person_name).write_text(
                json.dumps(self._profiles[person_name], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"[VECTOR][persona] save failed: {e}")
            raise

    @staticmethod
    def _profile_path(person_name: str) -> Path:
        if (
            not person_name
            or len(person_name) > 128
            or person_name in {".", ".."}
            or "\x00" in person_name
            or "/" in person_name
            or "\\" in person_name
        ):
            raise ValueError("Invalid person_name for profile storage")
        return _STORE / f"{person_name}.json"

    # ── Learning ───────────────────────────────────────────────────────────────

    def learn_from_messages(self, person_name: str, messages: list[dict]) -> dict:
        if not messages:
            return {"status": "error", "message": "No messages provided"}

        person_name = person_name.strip().title()

        if person_name not in self._profiles:
            from datetime import datetime, timezone
            self._profiles[person_name] = {
                "name": person_name,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "message_count": 0,
                "style": {},
                "vocabulary": [],
                "patterns": [],
                "topics": [],
            }

        profile = self._profiles[person_name]
        profile["message_count"] += len(messages)

        all_text = " ".join(m.get("content", "") for m in messages)
        new_words = all_text.lower().split()
        profile["vocabulary"] = list(set(profile["vocabulary"] + new_words))[-500:]

        profile["style"]["tone"] = self._analyze_tone(messages)
        profile["style"]["formality"] = self._analyze_formality(messages)
        profile["style"]["emoji_frequency"] = self._analyze_emoji_usage(messages)
        profile["style"]["avg_response_length"] = self._analyze_response_length(messages)
        profile["patterns"].append(self._analyze_greetings(messages))
        profile["topics"] = list(set(profile["topics"] + self._extract_topics(all_text)))[:50]

        self._save_profile(person_name)
        return {
            "status": "success",
            "person": person_name,
            "messages_analyzed": len(messages),
            "style_summary": profile["style"],
        }

    # ── Analysis helpers ───────────────────────────────────────────────────────

    def _analyze_tone(self, messages: list[dict]) -> str:
        text = " ".join(m.get("content", "") for m in messages).lower()
        pos = sum(1 for w in ["great","awesome","amazing","love","excellent","good","thanks"] if w in text)
        neg = sum(1 for w in ["bad","terrible","hate","awful","horrible","angry","disappointed"] if w in text)
        if pos > neg * 2: return "positive"
        if neg > pos * 2: return "negative"
        return "neutral"

    def _analyze_formality(self, messages: list[dict]) -> str:
        text = " ".join(m.get("content", "") for m in messages).lower()
        formal = sum(1 for w in ["would","could","please","kindly","appreciate","regards"] if w in text)
        casual = sum(1 for w in ["hey","gonna","wanna","lol","bro","dude","yeah","nah"] if w in text)
        if formal > casual * 2: return "formal"
        if casual > formal * 2: return "casual"
        return "mixed"

    def _analyze_emoji_usage(self, messages: list[dict]) -> float:
        total = len(messages)
        if total == 0: return 0.0
        count = sum(
            len(re.findall(r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF]", m.get("content", "")))
            for m in messages
        )
        return round(count / total, 2)

    def _analyze_greetings(self, messages: list[dict]) -> dict:
        greetings = []
        for m in messages[:10]:
            content = m.get("content", "").strip()
            if content:
                word = content.split()[0].lower() if content.split() else ""
                if word in ("hi", "hey", "hello", "yo", "sup"):
                    greetings.append(word)
        return {"type": "greeting", "common_greetings": list(set(greetings))[:5]}

    def _analyze_response_length(self, messages: list[dict]) -> float:
        if not messages: return 0.0
        total = sum(len(m.get("content", "").split()) for m in messages)
        return round(total / len(messages), 1)

    def _extract_topics(self, text: str) -> list[str]:
        topic_map = {
            "work":        ["work","job","project","meeting","deadline"],
            "technology":  ["code","computer","software","programming","ai","python","api"],
            "education":   ["study","exam","college","university","kiit","course"],
            "entertainment":["movie","game","music","sport","gym"],
            "finance":     ["money","investment","stock","bitcoin","trading"],
        }
        text_lower = text.lower()
        return [t for t, kws in topic_map.items() if any(kw in text_lower for kw in kws)]

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_style(self, person_name: str) -> dict:
        return self._profiles.get(person_name.strip().title(), {}).get("style", {})

    def generate_response_style(self, person_name: str, text: str) -> str:
        """Rewrite text to match person's style using Ollama."""
        person_name = person_name.strip().title()
        if person_name not in self._profiles:
            return text

        style = self._profiles[person_name].get("style", {})
        vocab = self._profiles[person_name].get("vocabulary", [])[:20]

        prompt = (
            f"Rewrite the following message to match this person's communication style.\n\n"
            f"Original: {text}\n\n"
            f"Style — formality: {style.get('formality','mixed')}, "
            f"tone: {style.get('tone','neutral')}, "
            f"common words: {', '.join(vocab)}\n\n"
            f"Return ONLY the rewritten message."
        )
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
            return resp["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"[VECTOR][persona] style gen failed: {e}")
            return text

    def list_profiles(self) -> list[str]:
        return list(self._profiles.keys())

    def delete_profile(self, person_name: str) -> bool:
        person_name = person_name.strip().title()
        if person_name in self._profiles:
            del self._profiles[person_name]
            p = self._profile_path(person_name)
            if p.exists(): p.unlink()
            return True
        return False

    def compare_with(self, person_a: str, person_b: str) -> dict:
        """Compare two stored profiles. Returns compatibility score 0-100."""
        pa = self._profiles.get(person_a.strip().title(), {}).get("style", {})
        pb = self._profiles.get(person_b.strip().title(), {}).get("style", {})
        if not pa or not pb:
            return {"compatibility_score": 50, "note": "insufficient data"}

        formality_match = 1 if pa.get("formality") == pb.get("formality") else 0
        tone_match = 1 if pa.get("tone") == pb.get("tone") else 0
        score = 40 + (formality_match * 30) + (tone_match * 30)
        return {
            "person_a": person_a,
            "person_b": person_b,
            "compatibility_score": score,
            "formality_match": bool(formality_match),
            "tone_match": bool(tone_match),
        }


if __name__ == "__main__":
    pm = PersonModel()
    msgs = [
        {"content": "Hey! How's it going?"},
        {"content": "Great work on the project, thanks for helping out!"},
        {"content": "No worries at all, happy to help"},
    ]
    result = pm.learn_from_messages("TestPerson", msgs)
    assert result["status"] == "success"
    style = pm.get_style("TestPerson")
    assert "tone" in style and "formality" in style
    profiles = pm.list_profiles()
    assert "TestPerson" in profiles
    print("persona/person_model.py OK")


