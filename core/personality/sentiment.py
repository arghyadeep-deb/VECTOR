"""3-tier sentiment analyzer: keyword → embedding → LLM fallback."""

from __future__ import annotations

__all__ = [
    "SentimentAnalyzer",
    "SentimentResult",
]


import re
import time
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from core.config import CONFIG


class SentimentResult(BaseModel):
    emotion: str = "neutral"
    intensity: float = Field(default=0.0, ge=0.0, le=1.0)
    urgency: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    raw_scores: dict[str, float] = Field(default_factory=dict)

    # VAD (Valence-Arousal-Dominance) — computed from emotion+intensity, never stored raw
    # Populated lazily via the `vad` property so existing callers are unaffected.
    _vad_cache: tuple[float, float, float] | None = None

    # PAD values per emotion (v, a, d)
    _EMOTION_PAD: dict[str, tuple[float, float, float]] = {
        "happy":      ( 0.8,  0.4,  0.3),
        "frustrated": (-0.6,  0.7, -0.2),
        "urgent":     ( 0.0,  0.9,  0.0),
        "curious":    ( 0.4,  0.3,  0.1),
        "sad":        (-0.5, -0.4, -0.3),
        "neutral":    ( 0.0,  0.0,  0.0),
    }

    @property
    def label(self) -> str:
        if self.urgency > 0.6:
            return f"urgent_{self.emotion}"
        return self.emotion

    @property
    def vad(self) -> tuple[float, float, float]:
        """(valence, arousal, dominance) scaled by intensity. Range -1..1."""
        base = self._EMOTION_PAD.get(self.emotion, (0.0, 0.0, 0.0))
        scale = max(0.1, self.intensity)
        return (
            round(base[0] * scale, 4),
            round(base[1] * scale, 4),
            round(base[2] * scale, 4),
        )

    @property
    def valence(self) -> float:
        return self.vad[0]

    @property
    def arousal(self) -> float:
        return self.vad[1]

    @property
    def dominance(self) -> float:
        return self.vad[2]


_EMOTION_KEYWORDS: dict[str, list[tuple[str, float]]] = {
    "happy": [
        ("great", 0.7), ("awesome", 0.8), ("thanks", 0.6),
        ("perfect", 0.8), ("love", 0.7), ("amazing", 0.8),
        ("excellent", 0.8), ("wonderful", 0.8), ("good", 0.4),
        ("nice", 0.5), ("fantastic", 0.9), ("brilliant", 0.8),
        ("well done", 0.7), ("impressive", 0.7), ("satisfied", 0.6),
    ],
    "frustrated": [
        ("damn", 0.7), ("stupid", 0.7), ("hate", 0.8),
        ("annoying", 0.7), ("useless", 0.7), ("frustrat", 0.9),
        ("not working", 0.9), ("broken", 0.8), ("bug", 0.6),
        ("failed", 0.7), ("error", 0.5), ("wrong", 0.5),
        ("terrible", 0.8), ("awful", 0.8), ("horrible", 0.8),
        ("ridiculous", 0.7), ("unacceptable", 0.8),
        ("incompetent", 0.8), ("waste", 0.6), ("pointless", 0.6),
    ],
    "urgent": [
        ("hurry", 0.8), ("quick", 0.7), ("fast", 0.6),
        ("emergency", 0.9), ("asap", 0.9), ("now", 0.7),
        ("immediately", 0.9), ("urgent", 0.9), ("right now", 0.8),
        ("deadline", 0.7), ("critical", 0.8), ("important", 0.6),
        ("as soon as possible", 0.8), ("drop everything", 0.9),
        ("time-sensitive", 0.8), ("pressing", 0.7),
    ],
    "curious": [
        ("what", 0.4), ("how", 0.4), ("why", 0.5),
        ("tell me about", 0.6), ("explain", 0.7), ("how does", 0.6),
        ("interesting", 0.7), ("wondering", 0.7), ("curious", 0.8),
        ("?", 0.2), ("how to", 0.5), ("what is", 0.4),
        ("could you elaborate", 0.7), ("tell me more", 0.7),
        ("what's the difference", 0.5), ("how come", 0.5),
    ],
    "sad": [
        ("sad", 0.8), ("unfortunate", 0.7), ("disappointed", 0.8),
        ("tired", 0.6), ("exhausted", 0.7), ("depressed", 0.9),
        ("lonely", 0.8), ("down", 0.6), ("bad day", 0.7),
        ("sigh", 0.7), ("not good", 0.6), ("fail", 0.5),
        ("sorry", 0.4), ("miserable", 0.9), ("hopeless", 0.9),
        ("overwhelmed", 0.7), ("stressed", 0.6),
    ],
}

_URGENCY_BOOSTERS: dict[str, float] = {
    "!!!": 0.3,
    "??": 0.2,
    "ALL_CAPS": 0.4,
    "right now": 0.3,
    "asap": 0.4,
}


class SentimentAnalyzer:
    def __init__(self):
        self._embedding_model: Any = None
        self._emotion_embeddings: dict[str, Any] = {}
        self._method = CONFIG.get("personality", {}).get("sentiment_method", "keyword")

    def analyze(self, text: str) -> SentimentResult:
        start = time.perf_counter()
        result = self._keyword_analyze(text)
        elapsed = time.perf_counter() - start
        if result.confidence >= 0.6:
            logger.debug("[SentimentAnalyzer] keyword: {} (conf={:.2f}, {:.1f}ms)", result.emotion, result.confidence, elapsed * 1000)
            return result
        if self._method in ("embedding", "llm") or (self._method == "keyword" and self._embedding_model):
            embedding_result = self._embedding_analyze(text)
            elapsed = time.perf_counter() - start
            if embedding_result.confidence > result.confidence:
                result = embedding_result
                logger.debug("[SentimentAnalyzer] embedding: {} (conf={:.2f}, {:.1f}ms)", result.emotion, result.confidence, elapsed * 1000)
                if result.confidence >= 0.6:
                    return result
        if self._method != "llm":
            return result
        llm_result = self._llm_analyze(text)
        elapsed = time.perf_counter() - start
        if llm_result.confidence > result.confidence:
            result = llm_result
            logger.debug("[SentimentAnalyzer] llm: {} (conf={:.2f}, {:.1f}ms)", result.emotion, result.confidence, elapsed * 1000)
        return result

    def _keyword_analyze(self, text: str) -> SentimentResult:
        lower = text.lower()
        scores: dict[str, float] = {}
        for emotion, keywords in _EMOTION_KEYWORDS.items():
            total = 0.0
            count = 0
            for word, weight in keywords:
                if word in lower:
                    total += weight
                    count += 1
            scores[emotion] = total / (count + 1) * min(count, 5) / 5 if count > 0 else 0.0
        best_emotion = max(scores, key=scores.get)
        best_score = scores[best_emotion]
        urgency = self._compute_urgency(lower)
        if urgency > best_score and urgency > 0.3:
            scores["urgent"] = urgency
            best_emotion = "urgent"
            best_score = urgency
        elif best_score <= 0.0:
            best_emotion = "neutral"
            best_score = 0.0
        return SentimentResult(
            emotion=best_emotion,
            intensity=min(1.0, best_score * 1.5),
            urgency=urgency,
            confidence=best_score,
            raw_scores=scores,
        )

    def _compute_urgency(self, text: str) -> float:
        urgency = 0.0
        if "!!!" in text:
            urgency += 0.3
        if "?" in text:
            urgency += 0.1
        all_caps_words = [w for w in text.split() if w.isupper() and len(w) > 2]
        if all_caps_words:
            urgency += min(0.4, len(all_caps_words) * 0.1)
        for phrase, boost in _URGENCY_BOOSTERS.items():
            if phrase in text:
                urgency += boost
        return min(1.0, urgency)

    def _embedding_analyze(self, text: str) -> SentimentResult:
        try:
            if self._embedding_model is None:
                from sentence_transformers import SentenceTransformer
                model_name = "all-MiniLM-L6-v2"
                self._embedding_model = SentenceTransformer(model_name)
                emotions = list(_EMOTION_KEYWORDS.keys())
                emotion_phrases = [
                    f"This text expresses {e} emotion: " + ", ".join(kw for kw, _ in _EMOTION_KEYWORDS[e][:5])
                    for e in emotions
                ]
                self._emotion_embeddings = {e: self._embedding_model.encode(p) for e, p in zip(emotions, emotion_phrases)}
            text_emb = self._embedding_model.encode(text)
            import numpy as np
            scores = {}
            for emotion, ref_emb in self._emotion_embeddings.items():
                sim = float(np.dot(text_emb, ref_emb) / (np.linalg.norm(text_emb) * np.linalg.norm(ref_emb) + 1e-10))
                scores[emotion] = max(0.0, sim)
            best_emotion = max(scores, key=scores.get)
            best_score = scores[best_emotion]
            return SentimentResult(
                emotion=best_emotion,
                intensity=min(1.0, best_score * 1.3),
                urgency=self._compute_urgency(text.lower()),
                confidence=best_score,
                raw_scores=scores,
            )
        except ImportError:
            logger.warning("[SentimentAnalyzer] sentence-transformers not installed, falling back to keyword")
            return self._keyword_analyze(text)

    def _llm_analyze(self, text: str) -> SentimentResult:
        try:
            import httpx
            emotions_list = ", ".join(_EMOTION_KEYWORDS.keys())
            prompt = (
                f"Classify the emotion of this text as one of: {emotions_list}. "
                f"Return JSON with keys: emotion, intensity (0-1), confidence (0-1).\n\nText: {text}"
            )
            resp = httpx.post(
                f"{CONFIG['ollama_host']}/api/generate",
                json={"model": CONFIG["models"]["fast"], "prompt": prompt, "stream": False, "format": "json"},
                timeout=10.0,
            )
            if resp.status_code != 200:
                return SentimentResult(emotion="neutral", confidence=0.3, raw_scores={})
            data = resp.json()
            import json as _json
            parsed = _json.loads(data.get("response", "{}"))
            emotion = parsed.get("emotion", "neutral")
            intensity = float(parsed.get("intensity", 0.5))
            confidence = float(parsed.get("confidence", 0.5))
            urgency = self._compute_urgency(text.lower())
            scores = {e: 0.0 for e in _EMOTION_KEYWORDS}
            scores[emotion] = confidence
            return SentimentResult(
                emotion=emotion if emotion in _EMOTION_KEYWORDS else "neutral",
                intensity=intensity,
                urgency=urgency,
                confidence=confidence,
                raw_scores=scores,
            )
        except Exception as e:
            logger.debug("[SentimentAnalyzer] LLM fallback failed: {}", e)
            return SentimentResult(emotion="neutral", confidence=0.2, raw_scores={})
