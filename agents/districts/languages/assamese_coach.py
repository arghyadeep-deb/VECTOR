"""
Module: agents/districts/languages/assamese_coach.py
District: languages | Focus: Assamese language coaching
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, random
from typing import Optional


class AssameseCoach(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="AssameseCoach",
            district="languages",
            generation=1
        )
        self.language = "assamese"
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.vocabulary = []
        self.grammar_rules = {}
        self._load_language_data()
        logger.info("[VECTOR][languages] AssameseCoach ready")

    def _load_language_data(self):
        self.grammar_rules = {
            "sandhi": "Word combination rules in Assamese",
            "samas": "Compound word formation",
            "vibhakti": "Postpositions and case markers",
            "ling_vivaran": "Gender and number agreement",
        }
        self.vocabulary = [
            {"word": "কিতাপ", "meaning": "book", "level": 1},
            {"word": "পানী", "meaning": "water", "level": 1},
            {"word": "খাদ্য", "meaning": "food", "level": 1},
            {"word": "শিকিবলৈ", "meaning": "to learn", "level": 1},
            {"word": "জ্ঞান", "meaning": "knowledge", "level": 2},
            {"word": "অধ্যয়ন", "meaning": "study", "level": 2},
            {"word": "চিন্তা", "meaning": "thought", "level": 2},
            {"word": "প্রচেষ্টা", "meaning": "effort", "level": 2},
            {"word": "সাফল্য", "meaning": "success", "level": 3},
            {"word": "অর্জন", "meaning": "achievement", "level": 3},
        ]

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        from core.inference.ollama_safe import chat as ollama_chat
        from core.loop.context_engine import ContextEngine
        hydration = ContextEngine().session_hydration_prompt()
        return ollama_chat(
            model=model or self.model,
            messages=[
                {"role": "system", "content": hydration},
                {"role": "user", "content": prompt},
            ],
            timeout=120,
        )

    def practice_vocabulary(self, word_count: int) -> dict:
        logger.info(f"[VECTOR][languages] Assamese vocabulary practice: {word_count} words")
        self.add_lesson({"action": "practice_vocabulary", "word_count": word_count, "language": self.language})
        level_buckets = {}
        for w in self.vocabulary:
            lvl = w.get("level", 1)
            level_buckets.setdefault(lvl, []).append(w)
        all_levels = sorted(level_buckets.keys())
        selected_words = []
        for lvl in all_levels:
            words_in_level = level_buckets[lvl]
            selected_words.extend(random.sample(words_in_level, min(len(words_in_level), max(1, word_count // len(all_levels)))))
        session = {"language": self.language, "words_practiced": len(selected_words), "words": selected_words, "practice_type": "vocabulary"}
        prompt = f"Create an Assamese vocabulary practice session with: {json.dumps([{'word': w['word'], 'meaning': w['meaning']} for w in selected_words], ensure_ascii=False)}. Format as study guide with definitions."
        session["study_guide"] = self._call_ollama(prompt, model=CONFIG["models"]["multilingual"])
        self.memory.store(event_type="vocabulary_practice", content=f"Assamese vocabulary practice: {len(selected_words)} words", tags=["language", self.language, "vocabulary"], context=session, source="AssameseCoach")
        return session

    def grammar_check(self, text: str) -> dict:
        logger.info(f"[VECTOR][languages] Checking Assamese grammar")
        self.add_lesson({"action": "grammar_check", "language": self.language})
        prompt = f"Check this Assamese text for grammar errors. Provide corrections.\nText: {text}"
        result = self._call_ollama(prompt, model=CONFIG["models"]["multilingual"])
        check_result = {"original_text": text, "language": self.language, "corrections": result, "checked_at": self.last_active}
        self.memory.store(event_type="grammar_check", content=f"Grammar check for Assamese text", tags=["language", self.language, "grammar"], context=check_result, source="AssameseCoach")
        return check_result

    def generate_sentences(self, word: str) -> dict:
        logger.info(f"[VECTOR][languages] Generating Assamese sentences for: {word}")
        self.add_lesson({"action": "generate_sentences", "word": word, "language": self.language})
        prompt = f"Generate 5 example sentences in Assamese using the word '{word}'. Include English translations."
        sentences_text = self._call_ollama(prompt, model=CONFIG["models"]["multilingual"])
        result = {"word": word, "language": self.language, "sentences": sentences_text, "count": sentences_text.count("\n") + 1}
        self.memory.store(event_type="sentences_generated", content=f"Generated Assamese sentences for '{word}'", tags=["language", self.language, "sentences"], context=result, source="AssameseCoach")
        return result

    def track_progress(self) -> dict:
        logger.info("[VECTOR][languages] Tracking Assamese learning progress")
        self.add_lesson({"action": "track_progress", "language": self.language})
        words_by_level = {}
        for w in self.vocabulary:
            lvl = w.get("level", 1)
            words_by_level.setdefault(lvl, []).append(w)
        progress = {"language": self.language, "total_words": len(self.vocabulary), "levels": {str(k): len(v) for k, v in words_by_level.items()}, "grammar_rules_covered": list(self.grammar_rules.keys())}
        self.memory.store(event_type="progress_tracked", content=f"Assamese learning progress: {len(self.vocabulary)} words", tags=["language", self.language, "progress"], context=progress, source="AssameseCoach")
        return progress


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    coach = AssameseCoach()
    assert coach.language == "assamese"
    session = coach.practice_vocabulary(5)
    assert session["language"] == "assamese"
    progress = coach.track_progress()
    assert "total_words" in progress
    print("✅ assamese_coach.py OK")