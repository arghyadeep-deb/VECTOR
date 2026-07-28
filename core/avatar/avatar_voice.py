"""
AvatarVoice — unified response formatter for the Avatar layer.
Rules:
  - Always speak as "I" (never "CodingBot", "HealthAgent", "District X")
  - Empathy-first: if user is frustrated/sad, acknowledge before solving
  - Tone driven by AvatarState.tone_hint + personality system
"""

import re
from typing import Any

from loguru import logger
from core.config import CONFIG
from core.avatar.avatar_state import AvatarState


# District / internal names VECTOR must never leak to the owner
_INTERNAL_NAMES: list[str] = [
    "CodingBot", "CodeReviewer", "GitBot", "ArchitectBot", "BugHunter",
    "ThreatScout", "MalwareHunter", "NodeGuard", "ThreatDetector",
    "HealthAdvisor", "FatigueMonitor", "SleepTracker",
    "DailyReviewer", "JournalWriter", "GrowthAnalyst",
    "FinanceBot", "UPIParser", "BudgetAnalyst",
    "StockAnalyst", "FundamentalsBot",
    "PatternDetective", "BehaviorAnalyst", "HabitFinder",
    "AINewsBot", "MarketTrendsBot", "OpportunitySpotter",
    "MockInterviewer", "ReportGenerator",
    "ConsolidationBot", "PatternFinder",
    "ChiefOfStaff", "Governor", "LLMCouncil",
    "district", "District", "agent", "Agent",
]
_INTERNAL_RE = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in _INTERNAL_NAMES) + r")\b"
)

# Empathy acknowledgments keyed on emotion
_EMPATHY_MAP: dict[str, str] = {
    "frustrated": "I hear you — that's genuinely frustrating. Let me sort this out.",
    "sad":        "I notice you seem a bit down. I'm here. Let me help with this.",
    "urgent":     "On it right away.",
}


class AvatarVoice:
    """
    Formats raw district output into a unified first-person VECTOR response.
    Reuses core/personality ToneAdapter + ConsistencyEnforcer; never duplicates them.
    """

    def __init__(self):
        self._tone_adapter = None
        self._consistency = None
        self._sentiment_analyzer = None
        self._card = None

    def _get_personality(self):
        """Lazy-load personality components."""
        if self._card is None:
            try:
                from core.personality.character_card import CharacterCard
                from core.personality.tone_adapter import ToneAdapter
                from core.personality.consistency import ConsistencyEnforcer
                self._card = CharacterCard()
                self._tone_adapter = ToneAdapter(self._card)
                self._consistency = ConsistencyEnforcer(self._card)
            except Exception as e:
                logger.warning("[VECTOR][avatar_voice] personality load failed: {}", e)

    def _get_sentiment_analyzer(self):
        if self._sentiment_analyzer is None:
            try:
                from core.personality.sentiment import SentimentAnalyzer
                self._sentiment_analyzer = SentimentAnalyzer()
            except Exception as e:
                logger.warning("[VECTOR][avatar_voice] sentiment analyzer load failed: {}", e)
        return self._sentiment_analyzer

    # ── public API ────────────────────────────────────────────────────────────
    def format(
        self,
        district_output: Any,
        state: AvatarState,
        task_context: dict | None = None,
        user_message: str = "",
    ) -> str:
        """
        Convert raw district output to a clean first-person VECTOR response.

        district_output: dict from agent.run() or a plain string
        state:           current AvatarState (for tone)
        task_context:    optional dict with 'task_type', 'district', etc.
        user_message:    original owner message (for empathy + consistency check)
        """
        raw = self._extract_text(district_output)

        # 1. Sanitise: strip internal agent/district names
        clean = self._sanitise(raw)

        # 2. Empathy wrapper: acknowledge emotion before solution
        clean = self._maybe_prepend_empathy(clean, user_message, state)

        # 3. Consistency check + optional LLM rewrite via existing enforcer
        clean = self._enforce_consistency(clean, user_message, state)

        # 4. First-person guarantee
        clean = self._ensure_first_person(clean)

        logger.debug("[VECTOR][avatar_voice] formatted ({} chars)", len(clean))
        return clean

    # ── internal helpers ─────────────────────────────────────────────────────
    # Keys that are pure routing/plumbing metadata — never the answer the owner
    # wants to read. Anything NOT in here is treated as potentially substantive
    # content when building the fallback render below.
    _METADATA_KEYS: frozenset[str] = frozenset({
        "status", "district", "agent", "agent_name", "task_id", "task_type",
        "success", "ok", "error", "reason", "code", "http_status",
        "health_points", "hp", "capability_match", "confidence", "score",
        "timestamp", "ts", "created_at", "updated_at", "elapsed_ms", "latency",
        "source", "caller_id", "trace_id", "span_id", "id", "uuid",
    })

    def _extract_text(self, output: Any) -> str:
        """Render a district's raw result into owner-facing text.

        2026-07-22 (KNOWN_ISSUES #1/#14/#15 root-cause fix): previously this
        checked only 6 keys and, finding none, emitted a bare
        "Task completed — status: X" stub. Most of VECTOR's ~38 districts
        return their real content under *other* keys (emails, items, summary,
        analysis, plan, draft, quiz, ...), so a third-plus of districts and
        every multi-district combo response rendered as that meaningless stub
        in the live eval. Rather than patch 27+ districts one-by-one, fix the
        shared choke point: after the 6 priority keys, walk the dict for any
        substantive (non-metadata) content and render it readably. The
        priority-key path is unchanged, so the 5 already-fixed districts and
        every working one keep their exact current output.
        """
        if isinstance(output, str):
            return output
        if isinstance(output, list):
            return self._render_value(output).strip()
        if isinstance(output, dict):
            # 1) Priority keys — unchanged. Fixed/working districts hit here and
            #    return exactly what they did before (no regression).
            for key in ("response", "result", "content", "message", "text", "output"):
                val = output.get(key)
                if val and isinstance(val, str):
                    return val

            # 2) Root-cause fallback: gather every substantive (non-metadata)
            #    field and render it. This is what rescues the ~27 unaudited
            #    districts and the combo path from the stub.
            parts: list[str] = []
            for key, val in output.items():
                if key in self._METADATA_KEYS:
                    continue
                rendered = self._render_value(val).strip()
                if not rendered:
                    continue
                # Single unlabeled block reads cleaner without a key prefix;
                # multiple fields get a "Label: ..." so nothing is ambiguous.
                label = key.replace("_", " ").strip().capitalize()
                parts.append((label, rendered))

            if len(parts) == 1:
                label, body = parts[0]
                # 2026-07-23 KNOWN_ISSUES #23: a memory_curator agent's
                # fallback action (task_type it doesn't declare, HP-lottery
                # picked it anyway — see governor.py's Task A.3 note) returned
                # {"status": "ok", "consolidated": 200}. "consolidated" isn't
                # metadata, so this was the sole substantive field and got
                # returned bare: the literal string "200" — meaningless
                # without its label. A bare token (no whitespace) isn't
                # self-explanatory the way a full sentence is; only skip the
                # label when the value reads as actual prose.
                if " " in body or len(body) > 40:
                    return body
                return f"{label}: {body}"
            if parts:
                return "\n\n".join(f"{label}: {body}" for label, body in parts)

            # 3) Genuinely nothing substantive. Be honest rather than claim a
            #    fake completion — an empty/error dict should read as "couldn't
            #    do it", not "Task completed". If there's an error string,
            #    surface a cleaned version of it.
            err = output.get("error") or output.get("reason")
            if err and isinstance(err, str):
                return f"I ran into a problem with that: {err}"
            status = output.get("status", "")
            if status in ("no_agents", "error", "failed"):
                return (
                    "I wasn't able to complete that one — nothing came back "
                    "from the part of me that handles it. Want me to try a "
                    "different way?"
                )
            return "I've noted that, but I don't have a result to show for it yet."
        return str(output)

    def _render_value(self, val: Any, depth: int = 0) -> str:
        """Turn an arbitrary district value (str/num/list/dict) into readable text.

        Depth-guarded so a deeply nested or self-referential structure can't
        run away. Lists render as bullet-ish lines; nested dicts recurse
        through the same substantive-field logic (minus the stub fallback)."""
        if val is None or isinstance(val, bool):
            return ""
        if isinstance(val, str):
            return val.strip()
        if isinstance(val, (int, float)):
            return str(val)
        if depth >= 3:
            return ""
        if isinstance(val, dict):
            lines: list[str] = []
            for k, v in val.items():
                if k in self._METADATA_KEYS:
                    continue
                sub = self._render_value(v, depth + 1).strip()
                if sub:
                    lines.append(f"{k.replace('_', ' ').capitalize()}: {sub}")
            return "\n".join(lines)
        if isinstance(val, (list, tuple)):
            items: list[str] = []
            for item in val:
                sub = self._render_value(item, depth + 1).strip()
                if sub:
                    items.append(sub if len(val) == 1 else f"• {sub}")
            return "\n".join(items)
        return str(val).strip()

    def _sanitise(self, text: str) -> str:
        """Replace leaked internal names with neutral 'I'."""
        result = _INTERNAL_RE.sub("I", text)
        if result != text:
            logger.debug("[VECTOR][avatar_voice] sanitised internal name leak")
        return result

    def _maybe_prepend_empathy(self, text: str, user_message: str, state: AvatarState) -> str:
        if not user_message:
            return text
        sa = self._get_sentiment_analyzer()
        if sa is None:
            return text
        try:
            sentiment = sa.analyze(user_message)
            # Only acknowledge negative/urgent emotions with intensity > threshold
            if sentiment.emotion in _EMPATHY_MAP and sentiment.intensity > 0.3:
                ack = _EMPATHY_MAP[sentiment.emotion]
                # Don't double-ack if the district already said something empathetic
                if ack[:15].lower() not in text.lower()[:80]:
                    text = f"{ack}\n\n{text}"
                    logger.debug("[VECTOR][avatar_voice] empathy ack prepended ({})", sentiment.emotion)
                # Update state — use SentimentResult.vad as the authoritative PAD values
                v, a, d = sentiment.vad
                alpha = 0.3 * sentiment.intensity
                state.valence   = state.valence   * (1 - alpha) + v * alpha
                state.arousal   = state.arousal   * (1 - alpha) + a * alpha
                state.dominance = state.dominance * (1 - alpha) + d * alpha
                state.emotional_arc.append(f"{sentiment.emotion}:{sentiment.intensity:.2f}")
        except Exception as e:
            logger.debug("[VECTOR][avatar_voice] empathy check failed: {}", e)
        return text

    def _enforce_consistency(self, text: str, user_message: str, state: AvatarState) -> str:
        self._get_personality()
        if self._consistency is None:
            return text
        try:
            from core.personality.sentiment import SentimentResult
            result = self._consistency.check(text, user_message or None, state.mood_label)
            if result.rewritten:
                return result.rewritten
        except Exception as e:
            logger.debug("[VECTOR][avatar_voice] consistency check failed: {}", e)
        return text

    def _ensure_first_person(self, text: str) -> str:
        """Capitalise the first 'I' if missing from the start."""
        # If text begins with third-person agent phrase, prepend "I've handled this —"
        if re.match(r"^(The agent|The system|Agent|System)\b", text, re.IGNORECASE):
            text = "I've handled this — " + text[text.index(" ") + 1:]
        return text


if __name__ == "__main__":
    state = AvatarState.load()
    voice = AvatarVoice()

    raw = {"status": "ok", "response": "CodingBot has reviewed your code and found 2 issues."}
    out = voice.format(raw, state, user_message="review my code")
    assert "CodingBot" not in out, f"Internal name leaked: {out}"
    assert "I" in out or "found" in out, f"No first-person: {out}"
    print(f"OK avatar_voice -- output: {out[:80]!r}")
