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
]
# 2026-07-29: bare "district"/"agent" used to be in _INTERNAL_NAMES above too.
# Found live while testing the Governor capability-match caveat fix
# (KNOWN_ISSUES #31): a legitimate, owner-facing sentence — "email_agent in
# the communications district doesn't have a dedicated capability..." — came
# out of _sanitise() as "...communications I doesn't have...", because
# "district" is a common English word that also appears in ordinary
# sentences, not just as a leaked internal codename (unlike "CodingBot" or
# "ChiefOfStaff", which are unambiguous implementation names with no
# legitimate use in owner-facing prose). Removed the two bare generic words;
# the actual internal bot/system codenames above are untouched and still
# get scrubbed.
# 2026-07-30 audit fix (Phase 3 — guardrails): the bare name -> "I"
# substitution below was grammatically fine only when the name sat in
# object position ("ask CodingBot" -> "ask I" — already imperfect, but a
# separate, smaller, pre-existing limitation not touched here). When the
# name was the SUBJECT of a 3rd-person-singular verb, the swap stranded
# that verb's conjugation behind: "CodingBot has reviewed" -> "I has
# reviewed", "GitBot doesn't have" -> "I doesn't have", "ThreatScout is
# monitoring" -> "I is monitoring" — all live, all wrong, and none of it was
# caught by the existing self-test (which only checked the name was gone
# and *an* "I" was present, not that the sentence still parsed). The
# 2026-07-29 fix only removed a false-POSITIVE match ("district"/"agent"
# wrongly caught as if they were internal names) — a different bug class
# from this one, and patching _INTERNAL_NAMES entry-by-entry was never
# going to fix verb agreement no matter how carefully the list was curated.
# _INTERNAL_RE now also captures the word immediately after a matched name
# so _sanitise() can re-conjugate the small set of verbs whose 1st- and
# 3rd-person-singular forms actually differ, instead of leaving a
# 3rd-person verb stranded after "I".
_IRREGULAR_VERB_AGREEMENT: dict[str, str] = {
    "is": "am", "isn't": "am not",
    "has": "have", "hasn't": "haven't",
    "does": "do", "doesn't": "don't",
}


def _naive_first_person_verb(word: str) -> "str | None":
    """Best-effort 3rd-person-singular -> 1st-person conjugation for regular
    '-s' verbs (reviews->review, finds->find, handles->handle). Not a real
    morphological analyzer — deliberately conservative, returns None (leave
    the word untouched) for anything it isn't reasonably confident about,
    since "verb left as-is" was already today's behavior and is a safe
    fallback, never a regression."""
    lower = word.lower()
    fixed = _IRREGULAR_VERB_AGREEMENT.get(lower)
    if fixed is not None:
        return fixed
    if lower.endswith(("ches", "shes", "xes", "zes", "sses")):
        return word[:-2]
    if lower.endswith("ies") and len(lower) > 3:
        return word[:-3] + "y"
    if re.fullmatch(r"[a-z]+s", lower) and not lower.endswith(("ss", "us", "ous", "his", "is")):
        return word[:-1]
    return None


def _sanitise_name_and_verb(m: "re.Match") -> str:
    """re.sub callback: replace a leaked internal name with 'I', and — if
    the very next word is a verb whose conjugation actually depends on
    grammatical person — fix it up too, instead of stranding a 3rd-person
    verb after a 1st-person subject."""
    gap, word = m.group(2), m.group(3)
    if not word:
        return "I"
    fixed = _naive_first_person_verb(word)
    return "I" + gap + (fixed if fixed is not None else word)


_INTERNAL_RE = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in _INTERNAL_NAMES) + r")\b"
    r"(?:(\s+)([A-Za-z']+))?"
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

        # 0. Strip markdown: some districts (e.g. chief_of_staff's executive
        #    brief, docs/report generators) deliberately produce markdown
        #    for a document/panel view. When that same string reaches the
        #    owner as a *conversational* reply — including via this HP-
        #    lottery-style fallback path, where a mismatched-capability
        #    agent's own default output gets returned for an unrelated
        #    request — raw "#", "**", "-" bullets read as visibly broken
        #    formatting in chat and get read aloud literally ("hash",
        #    "asterisk", "hyphen") over voice. 2026-07-30's #105 fix handled
        #    this for the streaming voice paths' LLM-generated conversational
        #    text specifically; this is the same problem in the shared
        #    dispatch-result formatter every text response passes through,
        #    string or dict, regardless of which district produced it.
        raw = self._strip_markdown(raw)

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
            # KNOWN_ISSUES #10: "no_capable_agent" is governor.dispatch()'s
            # honest-refusal status for an LLM-classified chat action with no
            # capability match anywhere in the city (see governor.py) — same
            # "be honest, don't fake a completion" family as no_agents/error/
            # failed. In practice the `err` branch above already catches this
            # (that result always carries a `reason` string), but listed here
            # too so this stays correct even if a future caller ever emits
            # this status without a reason.
            if status in ("no_agents", "no_capable_agent", "error", "failed"):
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

    def _strip_markdown(self, text: str) -> str:
        """Turn markdown-formatted text into plain conversational prose.

        Deliberately conservative: removes syntax markers while preserving
        the underlying words, rather than trying to fully re-flow structure
        into new sentences (that's a much harder, LLM-shaped problem, and
        wrong 5% of the time is worse than a visible '#' the rest of the
        time). Handles the shapes VECTOR's own districts actually produce:
        ATX headers, bold/italic, inline code, and leading bullet/numbered-
        list markers. Numbered prefixes ("1. ", "2. ") are left alone —
        spoken or read as literal numbers they're mildly odd but not the
        "hash"/"asterisk"/"hyphen" mispronunciation problem this exists for.
        """
        if not text or ("#" not in text and "*" not in text and "_" not in text
                         and "`" not in text and not re.search(r"(?m)^\s*[-•]\s+", text)):
            return text
        # ATX headers: "## Executive Brief" -> "Executive Brief"
        out = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
        # Bold/italic/bold-italic (**x**, __x__, *x*, _x_) -> x. Bold pass
        # first so "**x**" doesn't leave a stray single "*" for the italic
        # pass to mis-handle.
        out = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", out)
        out = re.sub(r"\*\*(.+?)\*\*", r"\1", out)
        out = re.sub(r"__(.+?)__", r"\1", out)
        out = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", out)
        out = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"\1", out)
        # Inline code spans: `x` -> x
        out = re.sub(r"`([^`]+)`", r"\1", out)
        # Leading bullet markers: "- x" / "• x" -> "x"
        out = re.sub(r"(?m)^\s*[-•]\s+", "", out)
        # Collapse the blank-line runs left behind by removed header lines
        out = re.sub(r"\n{3,}", "\n\n", out).strip()
        if out != text:
            logger.debug("[VECTOR][avatar_voice] stripped markdown syntax from response")
        return out

    def _sanitise(self, text: str) -> str:
        """Replace leaked internal names with neutral 'I', re-conjugating
        the following verb for 1st person when the name was that verb's
        subject (see _sanitise_name_and_verb() / _naive_first_person_verb())."""
        result = _INTERNAL_RE.sub(_sanitise_name_and_verb, text)
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

    # 2026-07-30 audit fix: verb-agreement regression tests — these are the
    # exact live-confirmed mangled shapes ("I has", "I doesn't", "I is")
    # that the old bare name->"I" substitution produced.
    _voice = AvatarVoice()
    _grammar_cases = [
        ("CodingBot has reviewed your code.", "I have reviewed your code."),
        ("GitBot doesn't have that capability.", "I don't have that capability."),
        ("ThreatScout is monitoring your network.", "I am monitoring your network."),
        ("GitBot reviews pull requests automatically.", "I review pull requests automatically."),
        ("MalwareHunter catches suspicious files.", "I catch suspicious files."),
        ("PatternFinder tries new correlations daily.", "I try new correlations daily."),
        ("ChiefOfStaff will follow up tomorrow.", "I will follow up tomorrow."),
    ]
    for _src, _expected in _grammar_cases:
        _got = _voice._sanitise(_src)
        assert _got == _expected, f"grammar mangled: {_src!r} -> {_got!r} (expected {_expected!r})"
    print("OK avatar_voice -- verb-agreement fix verified (7/7 cases)")

    # 2026-08-04 fix: markdown-stripping regression tests, including the
    # exact live-observed shape (chief_of_staff's executive brief markdown
    # reaching the owner verbatim via the HP-lottery fallback — see
    # KNOWN_ISSUES.md #10 / #11).
    _md_cases = [
        ("## Executive Brief — 2026-08-04\n\n1. ACCOMPLISHED — did stuff.",
         "Executive Brief — 2026-08-04\n\n1. ACCOMPLISHED — did stuff."),
        ("# ACCOMPLISHED\nNo significant autonomous actions taken.",
         "ACCOMPLISHED\nNo significant autonomous actions taken."),
        ("- Review goals\n- Check budget", "Review goals\nCheck budget"),
        ("**bold** and *italic* and __also bold__ and _also italic_",
         "bold and italic and also bold and also italic"),
        ("Run `pytest` to check.", "Run pytest to check."),
        ("No markdown here, just prose.", "No markdown here, just prose."),
    ]
    for _src, _expected in _md_cases:
        _got = _voice._strip_markdown(_src)
        assert _got == _expected, f"markdown not stripped: {_src!r} -> {_got!r} (expected {_expected!r})"
    print("OK avatar_voice -- markdown-stripping fix verified (6/6 cases)")

    # End-to-end: the exact live-observed chief_of_staff brief text (trimmed)
    # should come out with no stray '#'/'*' characters after a full format()
    # pass, not just the isolated _strip_markdown() call above.
    _brief = {
        "response": (
            "# ACCOMPLISHED\n No significant autonomous actions taken by "
            "VECTOR today.\n\n## DECISIONS NEEDED\n- Review Phase 1.\n"
            "- Assess **revenue** progress."
        )
    }
    _out = voice.format(_brief, state, user_message="Remember that my favorite color is teal.")
    assert "#" not in _out and "**" not in _out, f"markdown leaked end-to-end: {_out!r}"
    print("OK avatar_voice -- end-to-end markdown strip verified on live-observed shape")
