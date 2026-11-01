"""
Module: agents/languages/japanese_coach.py
District: languages | Focus: Japanese language coaching (Hiragana, Katakana, Kanji, Grammar)
"""

import sys
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import uuid, asyncio, json, random
from typing import Optional


class JapaneseCoach(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="JapaneseCoach",
            district="languages",
            generation=1
        )
        self.capabilities = ["generate_sentences", "grammar_check", "japanese", "language", "learn", "practice_vocabulary", "track_progress"]
        self.language = "japanese"
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.vocabulary = []
        self.grammar_rules = {}
        self._load_language_data()
        logger.info("[VECTOR][languages] JapaneseCoach ready")

    def _load_language_data(self):
        self.grammar_rules = {
            "particle_usage": "は、が、を、に、で、へ、と、から",
            "verb_conjugation": "dictionary form, te-form, nai-form, ta-form",
            "adjective_types": "i-adjectives and na-adjectives",
            "keigo": "polite and humble forms",
            "sentence_structure": "SOV (Subject-Object-Verb) order",
            "question_particles": "か、かい、なのか",
            "counter_suffixes": "一二三四五六七八九十百千万",
        }
        self.vocabulary = [
            {"word": "本", "reading": "ほん", "meaning": "book", "level": 1},
            {"word": "水", "reading": "みず", "meaning": "water", "level": 1},
            {"word": "食べる", "reading": "たべる", "meaning": "to eat", "level": 1},
            {"word": "飲む", "reading": "のむ", "meaning": "to drink", "level": 1},
            {"word": "勉強", "reading": "べんきょう", "meaning": "study", "level": 2},
            {"word": "知識", "reading": "ちしき", "meaning": "knowledge", "level": 3},
            {"word": "成功", "reading": "せいこう", "meaning": "success", "level": 3},
            {"word": "努力", "reading": "どりょく", "meaning": "effort", "level": 2},
            {"word": "日本語", "reading": "にほんご", "meaning": "Japanese language", "level": 1},
            {"word": "達成", "reading": "たっせい", "meaning": "achievement", "level": 3},
        ]

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
        )

    def practice_vocabulary(self, word_count: int) -> dict:
        logger.info(f"[VECTOR][languages] Japanese vocabulary practice: {word_count} words")
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
        prompt = f"Create a Japanese vocabulary practice session with these words: {json.dumps([{'kanji': w['word'], 'reading': w.get('reading',''), 'meaning': w['meaning'], 'level': w['level']} for w in selected_words], ensure_ascii=False)}. Include romaji readings and example sentences."
        session["study_guide"] = self._call_ollama(prompt, model=CONFIG["models"]["multilingual"])
        self.memory.store(event_type="vocabulary_practice", content=f"Japanese vocabulary practice: {len(selected_words)} words", tags=["language", self.language, "vocabulary", "japanese"], context=session, source="JapaneseCoach")
        return session

    def grammar_check(self, text: str) -> dict:
        logger.info(f"[VECTOR][languages] Checking Japanese grammar")
        self.add_lesson({"action": "grammar_check", "language": self.language})
        prompt = f"Check this Japanese text for grammar errors (particle usage, verb conjugation, keigo). Provide corrections with explanations.\n\nText: {text}\nNote: Provide corrections in a way that a language learner can understand."
        result = self._call_ollama(prompt, model=CONFIG["models"]["multilingual"])
        if not (result or "").strip():
            logger.error("[VECTOR][languages] Japanese grammar check got an empty LLM response")
            return {"status": "error", "error": "llm returned no response", "original_text": text, "language": self.language}
        check_result = {"original_text": text, "language": self.language, "corrections": result, "checked_at": self.last_active}
        self.memory.store(event_type="grammar_check", content=f"Grammar check for Japanese text", tags=["language", self.language, "grammar", "japanese"], context=check_result, source="JapaneseCoach")
        return check_result

    def generate_sentences(self, word: str) -> dict:
        logger.info(f"[VECTOR][languages] Generating Japanese sentences for: {word}")
        self.add_lesson({"action": "generate_sentences", "word": word, "language": self.language})
        prompt = f"Generate 5 example sentences in Japanese using the word '{word}'. Include romaji reading, English translation, and grammar notes. Use polite form (です/ます)."
        sentences_text = self._call_ollama(prompt, model=CONFIG["models"]["multilingual"])
        if not (sentences_text or "").strip():
            logger.error("[VECTOR][languages] Japanese sentence generation got an empty LLM response for: {}", word)
            return {"status": "error", "error": "llm returned no response", "word": word, "language": self.language}
        result = {"word": word, "language": self.language, "sentences": sentences_text, "count": sentences_text.count("\n") + 1}
        self.memory.store(event_type="sentences_generated", content=f"Generated Japanese sentences for '{word}'", tags=["language", self.language, "sentences", "japanese"], context=result, source="JapaneseCoach")
        return result

    def track_progress(self) -> dict:
        logger.info("[VECTOR][languages] Tracking Japanese learning progress")
        self.add_lesson({"action": "track_progress", "language": self.language})
        words_by_level = {}
        for w in self.vocabulary:
            lvl = w.get("level", 1)
            words_by_level.setdefault(lvl, []).append(w)
        progress = {
            "language": self.language,
            "total_words": len(self.vocabulary),
            "levels": {str(k): len(v) for k, v in words_by_level.items()},
            "grammar_rules_covered": list(self.grammar_rules.keys()),
            "jlpt_recommendation": "N4" if len(self.vocabulary) >= 10 else "N5",
        }
        self.memory.store(event_type="progress_tracked", content=f"Japanese learning progress: {len(self.vocabulary)} words", tags=["language", self.language, "progress", "japanese"], context=progress, source="JapaneseCoach")
        return progress


    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {}) or {}
        supported = ["practice_vocabulary", "grammar_check", "generate_sentences", "track_progress"]

        if task_type == "practice_vocabulary":
            result = self.practice_vocabulary(p.get("word_count", 5))
            return {"status": "ok", **result}
        if task_type == "grammar_check":
            result = self.grammar_check(p.get("text", ""))
            return {"status": "ok", **result}
        if task_type == "generate_sentences":
            result = self.generate_sentences(p.get("word", ""))
            return {"status": "ok", **result}
        if task_type == "track_progress":
            result = self.track_progress()
            return {"status": "ok", **result}

        # 2026-07-29 (eval finding, languages TIER6): real chat dispatch
        # (governor's classifier can invent a task_type like "generate_quiz"
        # that has no exact match here and doesn't snap to a known
        # DISTRICT_TASK_MAP key either) used to always return a bare
        # "unhandled type" error, ignoring the real free-text question —
        # same bug class as #1/#14/#15/#21/#33/#36, just presenting as an
        # honest error instead of a wrong action. Route it to whichever
        # real capability the query actually asks for instead of erroring;
        # default to a vocabulary quiz (this coach's core capability, real
        # data, no LLM dependency) for a generic "quiz/practice me" ask
        # rather than guessing a grammar sentence or word that wasn't given.
        query = (
            p.get("query") or p.get("content") or task.get("query") or task.get("prompt") or ""
        ).strip()
        if query:
            q = query.lower()
            if "progress" in q or "how am i doing" in q or "how far" in q:
                result = self.track_progress()
                return {"status": "ok", **result}
            if ("grammar" in q or "correct" in q) and "text" not in p:
                return {"status": "ok", "response": f"Share the {self.language} sentence you'd like me to check and I'll review its grammar."}
            if ("sentence" in q or "example" in q) and "word" not in p:
                return {"status": "ok", "response": f"Tell me a {self.language} word and I'll generate example sentences using it."}
            result = self.practice_vocabulary(p.get("word_count", 5))
            return {"status": "ok", **result}

        return {"status": "error", "error": f"unhandled type '{task_type}'", "supported": supported}

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    coach = JapaneseCoach()
    assert coach.language == "japanese"
    session = coach.practice_vocabulary(5)
    assert session["language"] == "japanese"
    result = coach.grammar_check("私は食べる")
    assert "corrections" in result
    progress = coach.track_progress()
    assert "total_words" in progress
    assert progress["jlpt_recommendation"] in ["N5", "N4", "N3"]
    print("✅ japanese_coach.py OK")