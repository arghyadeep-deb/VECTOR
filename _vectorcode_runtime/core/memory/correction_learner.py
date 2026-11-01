"""Owner-correction learning mechanism for VECTOR.

When the owner corrects VECTOR's behavior, this module:
1. Detects the correction (distinguishes from normal chat/preferences/temporary instructions)
2. Extracts a structured lesson
3. Stores it in episodic_memory (event_type="correction_lesson")
4. Retrieves applicable lessons before future LLM calls
5. Injects them into session_hydration_prompt() so behavior changes

Reuses existing memory architecture — no new tables, no new subsystems.

Design constraints:
- NO fine-tuning model weights
- NO neural RL
- NO new memory subsystem (uses episodic_memory + semantic_memory)
- Corrections are NOT permanent global rules — they have confidence + validation status
- Ambiguous statements are rejected (min confidence 0.7 to store)
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from loguru import logger


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

# Validation states for a correction lesson
VALIDATION_UNVALIDATED = "unvalidated"
VALIDATION_VALIDATED = "validated"
VALIDATION_CONTRADICTED = "contradicted"
VALIDATION_EXPIRED = "expired"

# Correction types — explicit corrections vs other speech acts
CORRECTION_EXPLICIT = "explicit"        # "no, do X instead"
CORRECTION_IMPLICIT = "implicit"        # "actually, X" (softer)
NOT_CORRECTION_PREFERENCE = "preference"  # "I prefer X"
NOT_CORRECTION_TEMPORARY = "temporary"   # "just this once, do X"
NOT_CORRECTION_CONVERSATION = "conversation"  # normal chat
NOT_CORRECTION_AMBIGUOUS = "ambiguous"  # unclear if correction


@dataclass
class CorrectionLesson:
    """A structured lesson extracted from an owner correction.

    Stored as JSON in episodic_memory.content with event_type="correction_lesson".
    Tags include domain + situation keywords for FTS5 retrieval.
    """

    id: str
    situation: str              # what VECTOR was doing/answering
    wrong_behavior: str         # what VECTOR did wrong
    correction: str             # what the owner said
    lesson: str                 # extracted generalized rule
    domain: str                 # task category (coding, research, communication, etc.)
    confidence: float           # 0.0–1.0 (starts at detection confidence)
    timestamp: str              # ISO-8601
    applicability: str          # when this lesson applies (context description)
    source: str                 # "owner_correction"
    validation_status: str      # unvalidated | validated | contradicted | expired
    correction_type: str        # explicit | implicit
    times_applied: int = 0      # how many times retrieved and injected
    times_validated: int = 0    # how many times the outcome was good after applying
    last_applied: str = ""      # ISO-8601 timestamp of last retrieval
    situation_hash: str = ""    # SHA256 of situation for dedup
    supersedes: str = ""        # ID of lesson this one replaces (if consolidation)
    tags: list[str] = field(default_factory=list)  # for FTS5 retrieval

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CorrectionLesson:
        return cls(
            id=str(d.get("id") or f"cl_{uuid.uuid4().hex[:10]}"),
            situation=str(d.get("situation") or ""),
            wrong_behavior=str(d.get("wrong_behavior") or ""),
            correction=str(d.get("correction") or ""),
            lesson=str(d.get("lesson") or ""),
            domain=str(d.get("domain") or "general"),
            confidence=float(d.get("confidence", 0.5) or 0.0),
            timestamp=str(d.get("timestamp") or _now()),
            applicability=str(d.get("applicability") or ""),
            source=str(d.get("source") or "owner_correction"),
            validation_status=str(d.get("validation_status") or VALIDATION_UNVALIDATED),
            correction_type=str(d.get("correction_type") or CORRECTION_EXPLICIT),
            times_applied=int(d.get("times_applied", 0) or 0),
            times_validated=int(d.get("times_validated", 0) or 0),
            last_applied=str(d.get("last_applied") or ""),
            situation_hash=str(d.get("situation_hash") or ""),
            supersedes=str(d.get("supersedes") or ""),
            tags=list(d.get("tags") or []),
        )

    def to_storage_content(self) -> str:
        """Serialize to JSON string for episodic_memory.content."""
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_storage_content(cls, content: str) -> CorrectionLesson:
        """Deserialize from episodic_memory.content JSON string."""
        try:
            d = json.loads(content)
            return cls.from_dict(d)
        except (json.JSONDecodeError, TypeError):
            return cls(
                id=f"cl_{uuid.uuid4().hex[:10]}",
                situation="parse_error",
                wrong_behavior="",
                correction=content[:200],
                lesson="Failed to parse correction lesson",
                domain="general",
                confidence=0.0,
                timestamp=_now(),
                applicability="",
                source="system",
                validation_status=VALIDATION_EXPIRED,
                correction_type=NOT_CORRECTION_AMBIGUOUS,
            )


# ---------------------------------------------------------------------------
# Correction Detector — distinguishes corrections from other speech acts
# ---------------------------------------------------------------------------

# Patterns that signal EXPLICIT corrections (high confidence)
_EXPLICIT_PATTERNS = [
    r"\bno[, ,]+(.+)",                          # "no, do X"
    r"\bno[, ]+it(?:'s| is)\b(.+)",             # "no it's X"
    r"\bwrong[, ]+(.+)",                         # "wrong, X"
    r"\bthat(?:'s| is) wrong[, ]+(.+)",          # "that's wrong, X"
    r"\bincorrect[, ]+(.+)",                     # "incorrect, X"
    r"\bactually[, ]+(.+)",                      # "actually, X"
    r"\bnot (.+?)[, ]+(?:do |use |say )(.+)",    # "not X, do Y"
    r"\bdon'?t (?:do |say |use )(.+?)[, ]+(?:do |say |use )(.+)",  # "don't do X, do Y"
    r"\bI said (.+)",                            # "I said X"
    r"\bI meant (.+)",                           # "I meant X"
    r"\bcorrection[: ]+(.+)",                    # "correction: X"
    r"\byou got (?:that |it )?wrong[, ]+(.+)",   # "you got that wrong, X"
    r"\bshould (?:be |have been )(.+)",          # "should be X"
    r"\bthe (?:correct |right )?answer is (.+)",  # "the answer is X"
    r"\bit should (?:be |say )(.+)",             # "it should be X"
]

# Patterns that signal IMPLICIT corrections (medium confidence)
_IMPLICIT_PATTERNS = [
    r"\bhmm[, ]+(?:I think )?(?:it(?:'s| is) )?(.+)",  # "hmm, it's X"
    r"\bI (?:think|believe) (?:it(?:'s| is) )?(?:actually )?(.+)",  # "I think it's actually X"
    r"\baren'?t you (.+)",                       # "aren't you wrong about X"
    r"\bthat doesn'?t (?:seem |look )?(?:right|correct)",  # "that doesn't seem right"
    r"\bI (?:would|might) (?:have )?(?:done |said )(.+)",  # "I would have done X"
]

# Patterns that signal NON-corrections (should NOT be stored)
_PREFERENCE_PATTERNS = [
    r"\bI prefer\b",
    r"\bI (?:like|love) (.+) (?:better|more)",
    r"\bmy (?:favorite|preferred) is\b",
    r"\b(I'?d|I would) (?:rather|choose)\b",
]

_TEMPORARY_PATTERNS = [
    r"\bjust (?:this (?:once|time)|for now|temporarily|this one)\b",
    r"\bfor this (?:task|one|specific)\b",
    r"\b(?:only|just) this time\b",
    r"\b(?:don'?t|not) (?:worry about this|make this a rule)\b",
]

# Minimum confidence to store a correction
MIN_STORE_CONFIDENCE = 0.7


@dataclass
class DetectionResult:
    """Result of correction detection on an owner utterance."""
    is_correction: bool
    correction_type: str  # explicit | implicit | preference | temporary | conversation | ambiguous
    confidence: float     # 0.0–1.0
    correction_text: str  # extracted correction content
    matched_pattern: str  # regex that matched (for debugging)


class CorrectionDetector:
    """Detects explicit owner corrections in natural language.

    Distinguishes:
    - Explicit corrections ("no, do X") → confidence 0.85–0.95
    - Implicit corrections ("actually, X") → confidence 0.70–0.85
    - Preferences ("I prefer X") → NOT a correction
    - Temporary instructions ("just this once") → NOT a correction
    - Normal conversation → NOT a correction
    - Ambiguous → NOT stored (confidence too low)
    """

    def detect(self, utterance: str, prior_vector_response: str = "") -> DetectionResult:
        """Analyze an owner utterance for correction signals.

        Args:
            utterance: The owner's message
            prior_vector_response: VECTOR's preceding response (for context)

        Returns:
            DetectionResult with is_correction, type, confidence, extracted text
        """
        text = utterance.strip()
        if len(text) < 5:
            return DetectionResult(False, NOT_CORRECTION_CONVERSATION, 0.0, "", "")

        # Check non-correction patterns first (these override)
        for pattern in _PREFERENCE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return DetectionResult(False, NOT_CORRECTION_PREFERENCE, 0.8, "", pattern)

        for pattern in _TEMPORARY_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return DetectionResult(False, NOT_CORRECTION_TEMPORARY, 0.75, "", pattern)

        # Check explicit correction patterns
        for pattern in _EXPLICIT_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                correction_text = match.group(match.lastindex or 1) if match.lastindex else text
                confidence = _confidence_for_explicit(pattern, text)
                return DetectionResult(True, CORRECTION_EXPLICIT, confidence, correction_text.strip(), pattern)

        # Check implicit correction patterns
        for pattern in _IMPLICIT_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                correction_text = match.group(match.lastindex or 1) if match.lastindex else text
                confidence = _confidence_for_implicit(pattern, text)
                if confidence >= MIN_STORE_CONFIDENCE:
                    return DetectionResult(True, CORRECTION_IMPLICIT, confidence, correction_text.strip(), pattern)

        # No correction detected
        return DetectionResult(False, NOT_CORRECTION_CONVERSATION, 0.0, "", "")


def _confidence_for_explicit(pattern: str, text: str) -> float:
    """Score confidence for an explicit correction match."""
    base = 0.85
    # Longer corrections with specific content are more reliable
    if len(text) > 20:
        base += 0.05
    # "no" + comma is very strong signal
    if re.match(r"\bno\s*,", text, re.IGNORECASE):
        base += 0.05
    # "wrong" / "incorrect" is strong
    if re.search(r"\b(wrong|incorrect)\b", text, re.IGNORECASE):
        base += 0.05
    return min(0.95, base)


def _confidence_for_implicit(pattern: str, text: str) -> float:
    """Score confidence for an implicit correction match."""
    base = 0.72
    if len(text) > 30:
        base += 0.05
    if re.search(r"\bactually\b", text, re.IGNORECASE):
        base += 0.08
    return min(0.85, base)


# ---------------------------------------------------------------------------
# Lesson Extractor — converts detection result into a structured lesson
# ---------------------------------------------------------------------------

class LessonExtractor:
    """Extracts structured lessons from correction detections.

    Given:
    - VECTOR's wrong response
    - Owner's correction utterance
    - Detection result (type, confidence, correction text)

    Produces:
    - CorrectionLesson with situation, wrong_behavior, correction, lesson, domain, etc.
    """

    # Domain detection keywords
    _DOMAIN_KEYWORDS = {
        "coding": ["code", "coding", "function", "bug", "error", "syntax", "variable", "import", "class",
                    "debug", "refactor", "compile", "run", "execute", "script", "api", "endpoint",
                    "library", "package", "dependency", "install", "requests", "httpx", "module"],
        "research": ["search", "paper", "arxiv", "study", "research", "find", "lookup", "source"],
        "communication": ["message", "email", "text", "reply", "say", "tell", "write", "respond",
                          "tone", "style", "format"],
        "finance": ["money", "budget", "expense", "invoice", "payment", "tax", "finance", "cost",
                     "price", "revenue"],
        "scheduling": ["meeting", "calendar", "schedule", "appointment", "reminder", "deadline",
                       "time", "date"],
        "security": ["password", "auth", "security", "encrypt", "permission", "access", "token"],
        "data": ["database", "query", "table", "sql", "data", "record", "row", "column"],
    }

    def extract(
        self,
        detection: DetectionResult,
        prior_vector_response: str = "",
        context: dict | None = None,
    ) -> CorrectionLesson | None:
        """Extract a structured lesson from a correction detection.

        Returns None if confidence is below MIN_STORE_CONFIDENCE.
        """
        if not detection.is_correction or detection.confidence < MIN_STORE_CONFIDENCE:
            return None

        ctx = context or {}
        situation = ctx.get("situation", ctx.get("action_type", "conversation"))
        domain = self._detect_domain(
            f"{situation} {prior_vector_response} {detection.correction_text}"
        )

        # Build the generalized lesson
        lesson = self._build_lesson(detection, prior_vector_response, domain)

        # Build situation hash for dedup.
        #
        # E5 (contradiction audit) — investigated, and deliberately did NOT
        # change this to hash only (domain, situation). Doing so WOULD make
        # _consolidate()'s confidence-gated supersession branch reachable
        # for genuine contradictions (e.g. "the deadline is Friday" vs "the
        # deadline is Monday") -- but a direct regression test proved it
        # also incorrectly collapses independent, non-contradictory
        # corrections that merely share a broad situation (e.g. "use httpx",
        # "always use type hints", and "prefer async over sync" are all
        # real, simultaneously-valid tips for situation="coding", not
        # competing answers to one question -- confirmed by the pre-existing
        # tests/integration/test_correction_integration.py::
        # test_multiple_corrections_same_domain, which correctly expects
        # all 3 to remain independently retrievable). Distinguishing "a
        # different answer to the same question" from "an additional,
        # compatible tip for the same broad context" requires semantic
        # judgment this codebase's existing non-LLM mechanisms (exact hash,
        # keyword tags, Jaccard word-overlap -- all tried) cannot reliably
        # provide: "Friday" and "Monday" share no lexical overlap either, so
        # a similarity-based test could not distinguish the two cases any
        # better than domain+situation grouping does. See
        # VECTOR_TECHNICAL_KNOWLEDGE/E5_CONTRADICTION_REPORT.md for the full
        # investigation -- this is reported as a genuine, unresolved
        # architectural question, not silently guessed at. The hash keeps
        # its original, fine-grained form (includes the correction text)
        # so existing correct behavior (independent tips staying
        # independent) is preserved.
        sit_hash = hashlib.sha256(
            f"{domain}:{situation}:{detection.correction_text[:100]}".encode()
        ).hexdigest()[:16]

        # Build applicability description
        applicability = self._build_applicability(situation, domain, detection)

        # Build tags for FTS5 retrieval
        tags = self._build_tags(domain, situation, detection)

        return CorrectionLesson(
            id=f"cl_{uuid.uuid4().hex[:10]}",
            situation=situation,
            wrong_behavior=prior_vector_response[:300] if prior_vector_response else "unknown",
            correction=detection.correction_text,
            lesson=lesson,
            domain=domain,
            confidence=detection.confidence,
            timestamp=_now(),
            applicability=applicability,
            source="owner_correction",
            validation_status=VALIDATION_UNVALIDATED,
            correction_type=detection.correction_type,
            situation_hash=sit_hash,
            tags=tags,
        )

    def _detect_domain(self, text: str) -> str:
        """Detect task domain from text context."""
        text_lower = text.lower()
        scores: dict[str, int] = {}
        for domain, keywords in self._DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[domain] = score
        if scores:
            return max(scores, key=scores.get)
        return "general"

    def _build_lesson(self, detection: DetectionResult, prior_response: str, domain: str) -> str:
        """Build a generalized lesson string from the correction."""
        correction = detection.correction_text.strip()
        # Remove leading filler words
        correction = re.sub(r'^(no|wrong|incorrect|actually)[, ]*\s*', '', correction, flags=re.IGNORECASE)

        if prior_response:
            return f"When handling {domain} tasks: {correction} (not the previous approach)"
        return f"When handling {domain} tasks: {correction}"

    def _build_applicability(self, situation: str, domain: str, detection: DetectionResult) -> str:
        """Build a description of when this lesson applies."""
        return f"Applies when: situation is '{situation}', domain is '{domain}'"

    def _build_tags(self, domain: str, situation: str, detection: DetectionResult) -> list[str]:
        """Build FTS5-friendly tags for retrieval."""
        tags = [f"domain:{domain}", f"situation:{situation}", "source:owner_correction"]
        # Add key words from correction as tags
        words = re.findall(r'\b\w{4,}\b', detection.correction_text.lower())
        for w in words[:5]:
            if w not in ("that", "this", "with", "from", "should", "would", "could"):
                tags.append(f"keyword:{w}")
        return tags


# ---------------------------------------------------------------------------
# CorrectionLearner — store, retrieve, consolidate, inject
# ---------------------------------------------------------------------------


class CorrectionLearner:
    """Manages the correction lesson lifecycle using existing EpisodicMemory.

    Storage: episodic_memory table, event_type="correction_lesson"
    Retrieval: recall() with event_type filter + keyword matching
    Consolidation: duplicate detection via situation_hash, merge on conflict
    """

    def __init__(self, memory=None):
        # memory=None (every existing caller): lazily built on first use via
        # _get_memory() -> EpisodicMemory() -> the shared primary singleton,
        # unchanged behavior. An explicit memory lets a caller inject an
        # EpisodicMemory already bound to a different connection (see
        # core/memory/episodic.py's get_secondary_read_connection()).
        self._memory = memory
        self._detector = CorrectionDetector()
        self._extractor = LessonExtractor()
        logger.info("[VECTOR][correction_learner] initialized")

    def _get_memory(self):
        if self._memory is None:
            from core.memory.episodic import EpisodicMemory
            self._memory = EpisodicMemory()
        return self._memory

    # -- Detection + storage --------------------------------------------------

    def process_owner_message(
        self,
        utterance: str,
        prior_vector_response: str = "",
        context: dict | None = None,
    ) -> CorrectionLesson | None:
        """Process an owner message: detect correction → extract lesson → store.

        This is the main entry point. Called from autonomous_loop._handle_user_input()
        or from the chat handler whenever the owner sends a message.

        Returns the stored lesson, or None if no correction detected.
        """
        detection = self._detector.detect(utterance, prior_vector_response)
        if not detection.is_correction:
            return None

        lesson = self._extractor.extract(detection, prior_vector_response, context)
        if lesson is None:
            return None

        # Check for duplicates before storing
        existing = self._find_duplicate(lesson)
        if existing is not None:
            return self._consolidate(existing, lesson)

        # Store in episodic_memory
        self._store_lesson(lesson)
        logger.info(
            "[VECTOR][correction_learner] stored lesson '{}' (domain={}, conf={:.2f})",
            lesson.lesson[:60], lesson.domain, lesson.confidence,
        )
        return lesson

    def _store_lesson(self, lesson: CorrectionLesson) -> None:
        """Store a lesson in episodic_memory."""
        mem = self._get_memory()
        mem.store(
            event_type="correction_lesson",
            content=lesson.to_storage_content(),
            tags=lesson.tags,
            source="owner_correction",
        )

    def _find_duplicate(self, lesson: CorrectionLesson) -> CorrectionLesson | None:
        """Check if a lesson with the same situation_hash already exists.

        E5 (contradiction audit): _consolidate() never updates a stored row
        in place -- every call re-stores a fresh row, so several historical
        snapshots of the same logical (situation_hash-identified) lesson can
        coexist. Returning the FIRST match encountered (mem.recall()'s own
        order, not guaranteed to be the newest) could hand consolidation a
        STALE base state -- e.g. the original, pre-reinforcement confidence
        instead of the current one -- silently underselling how much
        reinforcement/supersession has already happened. Scanning all
        matches and keeping the highest-(confidence, timestamp) one applies
        the exact same authority rule retrieve_applicable_lessons() now
        uses, so both paths agree on what "the current state of this
        situation" means.
        """
        try:
            mem = self._get_memory()
            results = mem.recall(
                f"domain:{lesson.domain} situation:{lesson.situation}",
                limit=10,
                event_type="correction_lesson",
            )
            best: CorrectionLesson | None = None
            for r in results:
                try:
                    existing = CorrectionLesson.from_storage_content(r.get("content", ""))
                    if existing.situation_hash != lesson.situation_hash:
                        continue
                    if best is None or (existing.confidence, existing.timestamp) > (best.confidence, best.timestamp):
                        best = existing
                except Exception:
                    continue
            return best
        except Exception as e:
            logger.debug(f"[VECTOR][correction_learner] dedup check failed: {e}")
        return None

    def _consolidate(self, existing: CorrectionLesson, new: CorrectionLesson) -> CorrectionLesson:
        """Handle a duplicate: update confidence, merge lessons if needed."""
        # Boost confidence of existing lesson (reinforcement)
        existing.confidence = min(0.95, existing.confidence + 0.05)
        existing.times_applied += 1
        existing.last_applied = _now()

        # If new correction has different content, it might be a refinement
        if new.correction != existing.correction and new.confidence > existing.confidence:
            existing.supersedes = existing.id
            existing.id = f"cl_{uuid.uuid4().hex[:10]}"
            existing.correction = new.correction
            existing.lesson = new.lesson
            existing.wrong_behavior = new.wrong_behavior
            existing.timestamp = new.timestamp

        # Re-store with updated confidence
        try:
            mem = self._get_memory()
            mem.store(
                event_type="correction_lesson",
                content=existing.to_storage_content(),
                tags=existing.tags,
                source="owner_correction",
            )
        except Exception as e:
            logger.warning(f"[VECTOR][correction_learner] consolidation store failed: {e}")

        logger.info(
            "[VECTOR][correction_learner] consolidated lesson '{}' (conf={:.2f})",
            existing.lesson[:60], existing.confidence,
        )
        return existing

    # -- Retrieval -------------------------------------------------------------

    def retrieve_applicable_lessons(
        self,
        current_situation: str = "",
        domain: str = "",
        limit: int = 5,
    ) -> list[CorrectionLesson]:
        """Retrieve lessons applicable to the current situation.

        Searches episodic_memory for correction_lesson events matching the
        situation/domain. Returns sorted by confidence (highest first).

        Only returns lessons with confidence >= 0.5 and validation_status != expired.
        """
        try:
            mem = self._get_memory()
            query_parts = ["source:owner_correction"]
            if domain:
                query_parts.append(f"domain:{domain}")
            if current_situation:
                query_parts.append(current_situation[:100])
            query = " ".join(query_parts)

            results = mem.recall(query, limit=limit * 2, event_type="correction_lesson")
        except Exception as e:
            logger.debug(f"[VECTOR][correction_learner] retrieval failed: {e}")
            return []

        lessons: list[CorrectionLesson] = []
        for r in results:
            try:
                lesson = CorrectionLesson.from_storage_content(r.get("content", ""))
                # Filter: skip expired/contradicted and low-confidence
                if lesson.validation_status == VALIDATION_EXPIRED:
                    continue
                if lesson.validation_status == VALIDATION_CONTRADICTED:
                    continue
                if lesson.confidence < 0.5:
                    continue
                lessons.append(lesson)
            except Exception:
                continue

        # E5 (contradiction audit) — dedup by situation_hash BEFORE sorting/
        # limiting. _consolidate() never updates a row in place: every
        # process_owner_message() call (initial store AND every later
        # reinforcement/supersession) does its own fresh mem.store(), so
        # episodic_memory can hold several accumulated snapshots of the SAME
        # logical lesson (identified by situation_hash) at different points
        # in its history. Without this, retrieve_applicable_lessons() could
        # surface an old, already-superseded snapshot alongside its own
        # replacement as if they were two independent, unrelated lessons —
        # "stores both, selects none" instead of "stores both, selects one".
        # Selecting the highest-confidence snapshot (ties broken by most
        # recent timestamp) is exactly the same authority rule
        # _consolidate()'s own supersession logic already uses — this does
        # not invent a second one.
        latest_by_situation: dict[str, CorrectionLesson] = {}
        for lesson in lessons:
            key = lesson.situation_hash or lesson.id  # no hash -> never collapse with another
            current = latest_by_situation.get(key)
            if current is None:
                latest_by_situation[key] = lesson
            elif (lesson.confidence, lesson.timestamp) > (current.confidence, current.timestamp):
                latest_by_situation[key] = lesson
        deduped = list(latest_by_situation.values())

        # Sort by confidence (highest first), limit results
        deduped.sort(key=lambda l: l.confidence, reverse=True)
        return deduped[:limit]

    def mark_applied(self, lesson_id: str) -> None:
        """Record that a lesson was retrieved and applied."""
        try:
            mem = self._get_memory()
            results = mem.recall(
                f"correction_lesson {lesson_id}",
                limit=5,
                event_type="correction_lesson",
            )
            for r in results:
                try:
                    lesson = CorrectionLesson.from_storage_content(r.get("content", ""))
                    if lesson.id == lesson_id:
                        lesson.times_applied += 1
                        lesson.last_applied = _now()
                        mem.store(
                            event_type="correction_lesson",
                            content=lesson.to_storage_content(),
                            tags=lesson.tags,
                            source="owner_correction",
                        )
                        return
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[VECTOR][correction_learner] mark_applied failed: {e}")

    def validate_lesson(self, lesson_id: str, outcome_good: bool) -> None:
        """Update lesson confidence based on outcome after applying it.

        If outcome was good: confidence += 0.05, times_validated += 1
        If outcome was bad: confidence -= 0.10, potentially mark contradicted
        """
        try:
            mem = self._get_memory()
            results = mem.recall(
                f"correction_lesson {lesson_id}",
                limit=5,
                event_type="correction_lesson",
            )
            for r in results:
                try:
                    lesson = CorrectionLesson.from_storage_content(r.get("content", ""))
                    if lesson.id == lesson_id:
                        if outcome_good:
                            lesson.confidence = min(0.95, lesson.confidence + 0.05)
                            lesson.times_validated += 1
                            if lesson.confidence >= 0.85:
                                lesson.validation_status = VALIDATION_VALIDATED
                        else:
                            lesson.confidence = max(0.0, lesson.confidence - 0.10)
                            if lesson.confidence < 0.3:
                                lesson.validation_status = VALIDATION_CONTRADICTED
                        mem.store(
                            event_type="correction_lesson",
                            content=lesson.to_storage_content(),
                            tags=lesson.tags,
                            source="owner_correction",
                        )
                        return
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[VECTOR][correction_learner] validate_lesson failed: {e}")

    # -- Decision-path influence (R8) -------------------------------------------

    def get_correction_penalty(self, action_type: str) -> float:
        """R8 — bounded, deterministic decision-path influence.

        Returns a penalty in [0.0, 0.12] for DecisionEngine to SUBTRACT from
        a candidate's weighted total_score, IF a real, persisted, still-valid
        (non-expired, non-contradicted) owner correction lesson exists whose
        `situation` field is an EXACT match for `action_type`.

        Why exact match, not domain/keyword matching: `lesson.situation` is
        populated by autonomous_loop._act_on() with the literal action_type
        that was just attempted (see `_current_action_type`) when the owner
        corrects it. Matching exactly — no substring/keyword/semantic
        interpretation of the lesson text — is what keeps this mechanism
        honest: a correction about `send_email` can never accidentally
        penalize `send_email_bulk` or any other unrelated action_type, and
        no LLM call is used to "interpret" what the correction meant.

        Why this is NOT the same as validate_lesson()'s VALIDATED status:
        this only requires the lesson to have cleared MIN_STORE_CONFIDENCE
        (0.7) at DETECTION time — the same bar every persisted correction
        already meets. It deliberately does NOT require
        validation_status == VALIDATED, because that status is driven by
        validate_lesson(outcome_good), which is an OUTCOME/reward-linked
        reinforcement signal with zero production callers today (see R8
        report) — gating decision-influence on it would make this mechanism
        silently inert in practice, AND would blur explicit-correction
        learning with reward learning, which R8 explicitly must not do.

        Bounded and safe: max 0.12, matching the existing bias_penalty scale
        in DecisionEngine._score_candidate(). Cannot make a FORBIDDEN/RED/
        YELLOW action GREEN (permission tier is a static action_type lookup,
        entirely independent of this score) and cannot elevate a candidate
        past the permission classification of its own action_type.
        """
        try:
            candidates = self.retrieve_applicable_lessons(current_situation=action_type, limit=10)
        except Exception as e:
            logger.debug(f"[VECTOR][correction_learner] get_correction_penalty retrieval failed: {e}")
            return 0.0

        matching = [
            lesson for lesson in candidates
            if lesson.situation == action_type and lesson.confidence >= MIN_STORE_CONFIDENCE
        ]
        if not matching:
            return 0.0

        # Multiple matching lessons: use the single highest-confidence one,
        # never sum them — prevents duplicate/repeated corrections from
        # uncontrollably stacking penalty (R8 test M).
        best = max(matching, key=lambda l: l.confidence)
        return round(min(0.12, best.confidence * 0.15), 4)

    # -- Context injection ----------------------------------------------------

    def build_injection_line(
        self,
        current_situation: str = "",
        domain: str = "",
    ) -> str:
        """Build a context line for session_hydration_prompt() with applicable lessons.

        Returns an empty string if no applicable lessons found.
        Format: "Owner corrections: [lesson1] | [lesson2] | ..."
        """
        lessons = self.retrieve_applicable_lessons(current_situation, domain, limit=3)
        if not lessons:
            return ""

        lines = []
        for lesson in lessons:
            lines.append(f"• {lesson.lesson[:120]}")
            # Mark as applied
            self.mark_applied(lesson.id)

        return "Owner corrections to remember:\n" + "\n".join(lines)

    # -- Bulk operations -------------------------------------------------------

    def list_all_lessons(self, limit: int = 50) -> list[CorrectionLesson]:
        """List all stored correction lessons (for diagnostics/HUD)."""
        try:
            mem = self._get_memory()
            results = mem.recall("source:owner_correction", limit=limit, event_type="correction_lesson")
            lessons = []
            for r in results:
                try:
                    lessons.append(CorrectionLesson.from_storage_content(r.get("content", "")))
                except Exception:
                    continue
            return lessons
        except Exception:
            return []

    def expire_old_lessons(self, max_age_days: int = 90) -> int:
        """Mark lessons older than max_age_days as expired (unless validated).

        Called during 2AM reflection to prevent stale corrections from persisting forever.
        Returns count of expired lessons.
        """
        expired_count = 0
        try:
            mem = self._get_memory()
            results = mem.recall(
                "source:owner_correction",
                limit=100,
                event_type="correction_lesson",
            )
            cutoff = (
                datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=max_age_days)
            ).isoformat()

            for r in results:
                try:
                    lesson = CorrectionLesson.from_storage_content(r.get("content", ""))
                    if lesson.timestamp < cutoff and lesson.validation_status == VALIDATION_UNVALIDATED:
                        lesson.validation_status = VALIDATION_EXPIRED
                        mem.store(
                            event_type="correction_lesson",
                            content=lesson.to_storage_content(),
                            tags=lesson.tags,
                            source="owner_correction",
                        )
                        expired_count += 1
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[VECTOR][correction_learner] expire_old_lessons failed: {e}")

        if expired_count:
            logger.info(f"[VECTOR][correction_learner] expired {expired_count} stale lessons")
        return expired_count


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    detector = CorrectionDetector()
    extractor = LessonExtractor()

    # Test 1: Explicit correction detected
    r = detector.detect("no, use httpx instead of requests")
    assert r.is_correction, f"Expected correction, got {r.correction_type}"
    assert r.confidence >= 0.7, f"Confidence too low: {r.confidence}"
    assert r.correction_type == CORRECTION_EXPLICIT

    # Test 2: Preference NOT detected as correction
    r = detector.detect("I prefer using fastapi over flask")
    assert not r.is_correction, "Preference should not be detected as correction"
    assert r.correction_type == NOT_CORRECTION_PREFERENCE

    # Test 3: Temporary NOT detected as correction
    r = detector.detect("just this once, use the old format")
    assert not r.is_correction, "Temporary should not be detected as correction"
    assert r.correction_type == NOT_CORRECTION_TEMPORARY

    # Test 4: Normal conversation NOT detected
    r = detector.detect("what time is the meeting tomorrow?")
    assert not r.is_correction, "Normal conversation should not be detected"

    # Test 5: "actually" detected as correction
    r = detector.detect("actually, the API returns a list, not a dict")
    assert r.is_correction, "Actually should be detected"
    assert r.confidence >= 0.7

    # Test 6: Lesson extraction
    r = detector.detect("no, use httpx instead of requests")
    lesson = extractor.extract(r, prior_vector_response="I'll use requests library", context={"situation": "coding"})
    assert lesson is not None
    assert lesson.domain == "coding"
    assert "httpx" in lesson.correction
    assert lesson.confidence >= 0.7

    # Test 7: CorrectionLesson serialization
    d = lesson.to_dict()
    restored = CorrectionLesson.from_dict(d)
    assert restored.id == lesson.id
    assert restored.lesson == lesson.lesson

    # Test 8: Storage round-trip
    content = lesson.to_storage_content()
    restored2 = CorrectionLesson.from_storage_content(content)
    assert restored2.domain == lesson.domain

    # Test 9: Domain detection
    assert extractor._detect_domain("fix the bug in the function") == "coding"
    assert extractor._detect_domain("search for recent papers on arxiv") == "research"
    assert extractor._detect_domain("what should I have for lunch") == "general"

    # Test 10: "wrong" keyword detection
    r = detector.detect("wrong, the answer is 42")
    assert r.is_correction
    assert r.confidence >= 0.85  # "wrong" boosts confidence

    print("✅ correction_learner.py OK — all self-tests passed")
