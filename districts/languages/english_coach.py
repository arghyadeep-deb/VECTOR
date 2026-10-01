"""
Module: agents/languages/english_coach.py
District: languages | Focus: English language coaching and vocabulary practice
"""

import sys
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from loguru import logger
import os
import uuid, asyncio, json, random
from typing import Optional


class EnglishCoach(AgentBase):
    def __init__(self):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="EnglishCoach",
            district="languages",
            generation=1
        )
        self.capabilities = ["english", "generate_sentences", "grammar_check", "language", "languages", "learn", "practice_vocabulary", "track_progress"]
        self.language = "english"
        self.memory = EpisodicMemory()
        self.obsidian = ObsidianSync()
        self.vocabulary = []
        self.grammar_rules = {}
        self._load_language_data()
        logger.info("[VECTOR][languages] EnglishCoach ready")

    def _load_language_data(self):
        self.grammar_rules = {
            "tenses": "12 verb tenses for expressing time",
            "articles": "a, an, the usage rules",
            "prepositions": "in, on, at, by, for, from, to, with",
            "conditionals": "zero, first, second, third, mixed conditionals",
            "modal_verbs": "can, could, may, might, must, should, would",
            "relative_clauses": "defining and non-defining relative clauses",
            "passive_voice": "form and usage of passive voice",
        }
        self.vocabulary = [
            {"word": "ubiquitous", "meaning": "present everywhere", "level": 3},
            {"word": "ephemeral", "meaning": "lasting for a short time", "level": 3},
            {"word": "pragmatic", "meaning": "practical and realistic", "level": 2},
            {"word": "meticulous", "meaning": "showing great attention to detail", "level": 3},
            {"word": "ambiguous", "meaning": "open to more than one interpretation", "level": 2},
            {"word": "elucidate", "meaning": "make something clear", "level": 4},
            {"word": "paradigm", "meaning": "a typical example or pattern", "level": 3},
            {"word": "sycophant", "meaning": "a person who flatters for gain", "level": 4},
            {"word": "benevolent", "meaning": "well-meaning and kind", "level": 2},
            {"word": "cogent", "meaning": "clear, logical, and convincing", "level": 3},
        ]
        logger.debug(f"[VECTOR][languages] Loaded {len(self.vocabulary)} English vocabulary words")

    def _call_ollama(self, prompt: str, model: Optional[str] = None) -> str:
        if os.getenv("VECTOR_LANGUAGE_LLM") != "1":
            return "Offline language guidance available; set VECTOR_LANGUAGE_LLM=1 for live model feedback."
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
        logger.info(f"[VECTOR][languages] English vocabulary practice: {word_count} words")
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

        session = {
            "language": self.language,
            "words_practiced": len(selected_words),
            "words": selected_words,
            "practice_type": "vocabulary",
        }

        prompt = f"Create an English vocabulary practice session with these words: {json.dumps([{'word': w['word'], 'meaning': w['meaning'], 'level': w['level']} for w in selected_words])}. Format as a study guide with definitions, synonyms, and example sentences."
        study_guide = self._call_ollama(prompt, model=CONFIG["models"]["multilingual"])
        session["study_guide"] = study_guide

        self.memory.store(
            event_type="vocabulary_practice",
            content=f"English vocabulary practice: {len(selected_words)} words",
            tags=["language", self.language, "vocabulary"],
            context=session,
            source="EnglishCoach"
        )

        logger.info(f"[VECTOR][languages] English practice session: {len(selected_words)} words")
        return session

    def grammar_check(self, text: str) -> dict:
        logger.info(f"[VECTOR][languages] Checking English grammar: {text[:50]}...")
        self.add_lesson({"action": "grammar_check", "language": self.language})

        prompt = f"Check this English text for grammar errors, tense consistency, article usage, and preposition errors. Provide corrections with explanations.\n\nText: {text}"
        result = self._call_ollama(prompt, model=CONFIG["models"]["multilingual"])
        if not (result or "").strip():
            logger.error("[VECTOR][languages] English grammar check got an empty LLM response")
            return {"status": "error", "error": "llm returned no response", "original_text": text, "language": self.language}

        check_result = {
            "original_text": text,
            "language": self.language,
            "corrections": result,
            "checked_at": self.last_active,
        }

        self.memory.store(
            event_type="grammar_check",
            content=f"Grammar check for English text: {text[:30]}...",
            tags=["language", self.language, "grammar"],
            context=check_result,
            source="EnglishCoach"
        )

        return check_result

    def generate_sentences(self, word: str) -> dict:
        logger.info(f"[VECTOR][languages] Generating English sentences for: {word}")
        self.add_lesson({"action": "generate_sentences", "word": word, "language": self.language})

        prompt = f"Generate 5 example sentences in English using the word '{word}'. Include varied contexts (formal, informal, academic) and English translations if needed. Vary difficulty."
        sentences_text = self._call_ollama(prompt, model=CONFIG["models"]["multilingual"])
        if not (sentences_text or "").strip():
            logger.error("[VECTOR][languages] English sentence generation got an empty LLM response for: {}", word)
            return {"status": "error", "error": "llm returned no response", "word": word, "language": self.language}

        result = {
            "word": word,
            "language": self.language,
            "sentences": sentences_text,
            "count": sentences_text.count("\n") + 1,
        }

        self.memory.store(
            event_type="sentences_generated",
            content=f"Generated English sentences for '{word}'",
            tags=["language", self.language, "sentences"],
            context=result,
            source="EnglishCoach"
        )

        return result

    def track_progress(self) -> dict:
        logger.info("[VECTOR][languages] Tracking English learning progress")
        self.add_lesson({"action": "track_progress", "language": self.language})

        words_by_level = {}
        for w in self.vocabulary:
            lvl = w.get("level", 1)
            words_by_level.setdefault(lvl, []).append(w)

        prompt = f"Generate a concise English learning progress summary. Current vocabulary: {len(self.vocabulary)} words across {len(words_by_level)} levels. Grammar rules covered: {list(self.grammar_rules.keys())}. Give progress feedback and next steps."
        summary = self._call_ollama(prompt, model=CONFIG["models"]["multilingual"])

        progress = {
            "language": self.language,
            "total_words": len(self.vocabulary),
            "levels": {str(k): len(v) for k, v in words_by_level.items()},
            "grammar_rules_covered": list(self.grammar_rules.keys()),
            "summary": summary,
        }

        self.memory.store(
            event_type="progress_tracked",
            content=f"English learning progress: {len(self.vocabulary)} words, {len(words_by_level)} levels",
            tags=["language", self.language, "progress"],
            context=progress,
            source="EnglishCoach"
        )

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
    coach = EnglishCoach()
    assert coach.language == "english"
    assert coach.district == "languages"

    session = coach.practice_vocabulary(5)
    assert session["language"] == "english"

    result = coach.grammar_check("I have went to the store yesterday")
    assert "corrections" in result

    sentences = coach.generate_sentences("ubiquitous")
    assert "sentences" in sentences

    progress = coach.track_progress()
    assert "total_words" in progress
    assert progress["language"] == "english"

    print("✅ english_coach.py OK")
