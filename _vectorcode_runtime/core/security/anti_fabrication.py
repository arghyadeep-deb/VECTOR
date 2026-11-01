"""Deterministic post-hoc filter for fabricated action-completion claims.

Extracted 2026-08-06 from core/api/routers/commands.py (KNOWN_ISSUES #13) while
auditing the /command vs /ws/command divergence. Originally lived only in
commands.py::_llm_answer(), so any pure-conversational LLM reply generated via
core.city.governor.Governor._answer_conversationally() (the path every
answer_question task hits when it flows through Governor.dispatch() — i.e.
every request that reaches /ws/command, and any /command request that
classify_chat_intent() routes there) never got this filter. A message like
"Store this in your memory permanently: my favorite color is teal" could come
back "✅ Stored permanently: favorite color = teal" on one transport and be
correctly de-fabricated on the other, purely depending on which endpoint the
caller happened to hit — same bug class as the English-only backstop gap
(84a663934) this task was written to prevent from recurring.

Moved here (rather than importing commands.py from governor.py) to avoid a
core -> api layering violation: core/city/governor.py must not depend on
core/api/routers/*.

2026-07-22 KNOWN_ISSUES #13 (real fix, not another prompt tweak): two
escalating rounds of anti-fabrication system-prompt instructions (kept in each
caller's own system prompt as a first line of defense) reduced but did NOT
eliminate confident false completion claims — a repeat live test still got
"Noted. Fox preference stored in permanent memory." (no checkmark, same lie).
Prompting is probabilistic; this class of claim is provably false 100% of the
time out of a pure-text conversational reply, because neither caller does any
tool-calling on this path — there is never a "corresponding tool call this
turn" to check against, there is NEVER one. So: deterministic post-hoc filter.
"""

import sys
import re

__all__ = [
    "defabricate_llm_answer",
    "remove_unsupported_action_claims",
    "requires_current_information",
    "current_information_plan",
    "current_information_decline_reply",
    "paper_retrieval_topic",
    "current_web_search_query",
]

_CHECKMARK_RE = re.compile(r"[✅✔️☑]\s*")

# ── V1 TRUST CLOSURE (2026-09-21, T1): factual grounding for current info ──
#
# defabricate_llm_answer() above only strips false ACTION-COMPLETION claims.
# It cannot notice a different fabrication: a confident, specific,
# current-looking FACTUAL answer (product names, versions, "new papers")
# free-generated from stale training data when the owner asked what is
# newly out there and nothing was retrieved (live V1,
# OWNER_ROUTING_CLOSURE_REPORT.md §20: "Synthesia 2.0", "Midjourney 5.0").
# Prompting alone doesn't hold (same lesson as #13), so this is a
# deterministic gate on the REQUEST: if the answer would materially depend
# on external, changing information, the conversational path must not
# free-generate it — it either retrieves (caller's job, via a real
# capability) or says honestly that it cannot verify. Three small,
# structural cues — not a topic keyword list:
#   recency marker  AND  external-information marker  AND NOT
#   (creative-generation or owner-local marker)
_RECENCY_RE = re.compile(
    r"\b(?:latest|newest|newly|recent(?:ly)?|lately|current(?:ly)?|"
    r"just\s+(?:released|published|announced|came\s+out)|"
    r"this\s+(?:week|month|year)|these\s+days|right\s+now|up[- ]to[- ]date|"
    r"state[- ]of[- ]the[- ]art|what(?:['’]s|\s+is|\s+has)?\s+new|out\s+there)\b",
    re.IGNORECASE,
)
_EXTERNAL_INFO_RE = re.compile(
    r"\b(?:published|papers?|research|studies|study|news|releases?|released|versions?|"
    r"announce(?:d|ments?)?|updates?|developments?|breakthroughs?|advances?|trends?|"
    r"benchmarks?|products?|tools?|models?|prices?|find\s+out|"
    r"check\s+(?:what|whether|if)|look\s+(?:up|into)|dig\s+up|pull\s+up)\b",
    re.IGNORECASE,
)
_CREATIVE_OR_LOCAL_RE = re.compile(
    r"\b(?:brainstorm|draft|write|compose|generate|come\s+up\s+with|suggest|imagine|pretend|"
    r"role[- ]?play|ideas?\s+for|names?\s+for|poem|story|"
    r"my\s+(?:day|week|schedule|calendar|goals?|notes?|code|projects?|attendance|habits?|portfolio)|"
    r"our\s+(?:code|repo|project))\b",
    re.IGNORECASE,
)
# "published" alone is NOT an academic cue ("news ... published this week" is not a paper
# request); it counts only alongside one of these nouns.
_PAPER_RE = re.compile(r"\b(?:papers?|research|studies|study|literature|preprints?|arxiv)\b", re.IGNORECASE)
_TOPIC_MARKER_RE = re.compile(r"\b(?:on|about|regarding|concerning|around)\s+(?P<topic>[^?.!]+)", re.IGNORECASE)
# A trailing task clause ("... , and summarize it for me", "... and explain the result",
# "..., please") is an instruction about what to do with the answer, not part of the
# topic — cut it off so its verb can never be mistaken for the subject.
_TOPIC_TASK_CLAUSE_RE = re.compile(
    r"(?:,|\s+(?:and|then|so|but)\s+(?:please\s+)?(?:summari[sz]e|explain|tell|list|give|show|write|compare|"
    r"describe|walk|break|outline|pull|find|check|let|send|email|save|store|post|share)\b"
    r"|\s+please\b|\s+for\s+me\b).*$",
    re.IGNORECASE,
)
_TOPIC_NOISE = frozenset({
    "this", "that", "these", "those", "the", "a", "an", "it", "its", "general", "particular",
    "specific", "certain", "some", "any", "area", "areas", "field", "fields", "topic", "topics",
    "subject", "study", "studies", "research", "of", "in", "on", "for", "and", "or", "to",
    "there", "out", "here", "new", "latest", "newest", "recent", "recently", "lately", "please",
    "thing", "things", "stuff", "one", "ones", "me", "my", "our", "us", "right", "now", "today",
})

CURRENT_INFO_UNVERIFIED_REPLY = (
    "I can't verify current information from here — I have no live source for it in this "
    "reply, and my training knowledge can be out of date — so I won't list recent releases, "
    "versions, papers or news as if they were current. Tell me the specific topic and I can "
    "run a paper search (arXiv) for research, or share stable background from general "
    "knowledge, clearly labelled as such."
)
CURRENT_INFO_NO_TOPIC_REPLY = (
    "I can search arXiv for recent papers, but you haven't named a topic yet — which area "
    "should I look at? I can't verify what's new without actually searching, so I won't "
    "guess at it."
)


def requires_current_information(user_text: str) -> bool:
    """True when answering `user_text` would materially depend on external,
    changing information (recency marker + external-information marker,
    and not a creative-generation or owner-local request)."""
    t = user_text or ""
    return bool(
        _RECENCY_RE.search(t) and _EXTERNAL_INFO_RE.search(t) and not _CREATIVE_OR_LOCAL_RE.search(t)
    )


def _research_topic(user_text: str) -> str | None:
    """The concrete subject of a research request ("... on protein folding"),
    or None when the owner named none ("... on this general area of study")."""
    matches = list(_TOPIC_MARKER_RE.finditer(user_text or ""))
    if not matches:
        return None
    phrase = _TOPIC_TASK_CLAUSE_RE.sub("", matches[-1].group("topic"))
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-\+\.]*", phrase)
    kept = [w for w in words if w.lower() not in _TOPIC_NOISE]
    return " ".join(kept[:6]) if kept else None


def current_information_plan(user_text: str) -> dict | None:
    """None when no grounding is required. Otherwise either
    {"mode": "retrieve", "topic": ...} — a paper/research request with a
    concrete topic, which the caller should route to the real `search_arxiv`
    capability — or {"mode": "decline", "reply": ...}: an honest inability
    statement (no capability with usable evidence, or no topic to search)."""
    if not requires_current_information(user_text):
        return None
    if _PAPER_RE.search(user_text):
        topic = _research_topic(user_text)
        if topic:
            return {"mode": "retrieve", "topic": topic}
        return {"mode": "decline", "reply": CURRENT_INFO_NO_TOPIC_REPLY}
    return {"mode": "decline", "reply": CURRENT_INFO_UNVERIFIED_REPLY}


# An imperative that asks VECTOR to DO something with the papers (send / post /
# schedule / save / deploy ...) makes the request an action, not a retrieval —
# the deterministic paper route must not swallow it (fail closed: the normal
# classifier path decides).
_PAPER_ROUTE_ACTION_RE = re.compile(
    r"\b(?:send|email|mail|forward|share|tweet|post|publish|schedule|remind|save|store|remember|"
    r"download|export|commit|push|deploy|delete|remove|cancel|book|buy|install|launch|upload|execute|"
    r"run\s+(?:the|a|my))\b",
    re.IGNORECASE,
)


def paper_retrieval_topic(user_text: str, *, require_recency: bool = True) -> str | None:
    """The concrete topic when `user_text` is genuinely an academic-paper
    RETRIEVAL request that the existing real capability (`search_arxiv`) can
    serve, else None (fail closed). Deterministic — no LLM.

    require_recency=True (the pre-classifier route): the request must also be a
    current-information request (recency + external marker) per
    current_information_plan(). require_recency=False (alias fold after the
    classifier already said "paper search"): academic cue + a named topic,
    not creative/owner-local. Either way an action verb (send/post/schedule/...)
    disqualifies it."""
    t = user_text or ""
    if _PAPER_ROUTE_ACTION_RE.search(t):
        return None
    if require_recency:
        plan = current_information_plan(t)
        return plan["topic"] if plan and plan.get("mode") == "retrieve" else None
    if _CREATIVE_OR_LOCAL_RE.search(t) or not _PAPER_RE.search(t):
        return None
    return _research_topic(t)


def current_web_search_query(user_text: str) -> str | None:
    """Return a current-fact question for the existing gated web search.

    Preserve the paper-specific arXiv route and never swallow an action that
    merely happens to mention current information.
    """
    plan = current_information_plan(user_text)
    if not plan or plan["mode"] != "decline" or _PAPER_RE.search(user_text):
        return None
    if _PAPER_ROUTE_ACTION_RE.search(user_text):
        return None
    return user_text.strip()[:500] or None


def current_information_decline_reply(user_text: str) -> str | None:
    """The honest reply for a conversational path that cannot retrieve, or
    None when the request does not depend on current information."""
    plan = current_information_plan(user_text)
    if plan is None:
        return None
    return plan.get("reply") or CURRENT_INFO_UNVERIFIED_REPLY

# Verbs that, in a first-person/implicit-subject completion claim, assert an
# action was actually carried out. Deliberately narrower than every possible
# synonym (skips generic "done"/"completed"/"created"/"added" etc. — those
# false-positive too easily on ordinary factual answers, e.g. "Python was
# created by Guido van Rossum") — scoped to the verbs actually observed in
# the live fabrication bug plus close, low-ambiguity synonyms.
_FABRICATED_COMPLETION_RE = re.compile(
    r"(?P<neg>\b(?:not|never|n['’]t|cannot|can['’]t|won['’]t|"
    r"didn['’]t|doesn['’]t|isn['’]t|wasn['’]t|"
    r"couldn['’]t|unable to|without)\b\s*(?:\w+\s+){0,4})?"
    r"\b(?P<verb>stored|saved|sent|scheduled|posted|executed|updated|"
    r"recorded|logged|persisted|remembered|confirmed)\b",
    re.IGNORECASE,
)

# Only engage the filter when the user's own message plausibly asked for an
# action — keeps it from mangling unrelated factual answers that happen to
# contain one of the verbs above (e.g. "Napoleon was sent to Elba").
_ACTION_REQUEST_HINT_RE = re.compile(
    r"\b(store|save|remember|remind|send|email|schedule|post|publish|"
    r"execute|run|update|record|log|persist)\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_PLANNED_PASSIVE_RE = re.compile(
    r"\b(?:(?:must|should|could|can|may|might|will|would)\s+be|"
    r"(?:needs?|has|have)\s+to\s+be)\s+(?:\w+\s+){0,2}$", re.IGNORECASE,
)


def defabricate_llm_answer(response: str, user_text: str) -> str:
    """Strip fabricated action-completion claims from a pure-text LLM reply.

    Callers of this function never invoke a tool on this reply path, so any
    sentence claiming something was actually stored/sent/scheduled/executed/
    etc. is unconditionally false — there's no "no corresponding tool call"
    check needed because there is categorically never a tool call here.
    Drops the offending sentence(s) (unless the claim is itself negated, e.g.
    "I can't confirm that was saved" — that's an honest hedge, not a
    fabrication) and appends an explicit caveat so the user isn't left with a
    false impression.
    """
    if not response:
        return response

    had_checkmark = bool(_CHECKMARK_RE.search(response))
    stripped = _CHECKMARK_RE.sub("", response)

    if not _ACTION_REQUEST_HINT_RE.search(user_text or ""):
        return stripped if had_checkmark else response

    sentences = _SENTENCE_SPLIT_RE.split(stripped)
    kept, dropped = [], []
    for s in sentences:
        unsupported = any(
            not match.group("neg") and not _PLANNED_PASSIVE_RE.search(s[:match.start("verb")])
            for match in _FABRICATED_COMPLETION_RE.finditer(s)
        )
        if unsupported:
            dropped.append(s.strip())
            continue
        kept.append(s)

    if not dropped:
        return stripped if had_checkmark else response

    from loguru import logger
    logger.warning(
        "[VECTOR][anti_fabrication] KNOWN_ISSUES #13 filter stripped "
        "fabricated completion claim(s): {}", dropped,
    )
    result = " ".join(s for s in kept if s.strip()).strip()
    caveat = (
        "Heads up, sir — I don't have tool-calling in this reply path, so "
        "nothing above was actually stored, sent, scheduled, or executed. "
        "I've only noted it in this conversation; there's currently no way "
        "for me to confirm it was carried out from here."
    )
    return f"{result}\n\n{caveat}" if result else caveat


# ── PRE-RG-D2 FINAL CLOSURE (2026-09-22, Target A): unsupported action claims ─
#
# defabricate_llm_answer() strips a narrow set of past-tense completion verbs
# and only when the owner's message hints at an action. The live frozen
# matrix (V1_TRUST_..._REPORT.md §14 #1) showed the same fabrication in other
# shapes with NO action routed or executed: a future commitment ("I'll ping
# you in 60 seconds"), and an invented "Action Taken:" narration. The LLM's
# own sentence is not evidence that anything happened.
#
# remove_unsupported_action_claims() classifies sentence SHAPES (first-person
# / VECTOR subject + action verb in a past, progressive or future form; a
# small set of "the deployment is running" state claims; "Action Taken:"
# headers) and checks each against AUTHORITATIVE evidence: `action_evidence`
# is the command's real execution trace ([] on a pure-text reply path, where
# nothing can have run). Unsupported claims are removed and an honest note is
# appended. Advice/hypothetical/ordinary language is untouched: no
# first-person action subject, an earlier "if/could/would/…" guard on future
# forms, or a negation, means it is not a claim.
_SUCCESS_STATUSES = frozenset({"ok", "executed", "completed", "success", "scheduled"})
_SCHEDULING_TOKENS = frozenset({"remind", "reminder", "timer", "alarm", "schedule", "calendar"})
# claim stem synonyms per evidence-action token (5-char stems)
_CLAIM_FAMILIES = {
    "remind": {"remin", "ping", "notif", "alert", "nudge"},
    "reminder": {"remin", "ping", "notif", "alert", "nudge"},
    "timer": {"timer", "alarm", "remin", "ping"},
    "alarm": {"timer", "alarm", "remin", "ping"},
    "email": {"email", "mail", "messa", "send", "sent"},
    "send": {"send", "sent", "email", "messa"},
    "message": {"messa", "send", "sent", "text"},
    "schedule": {"sched", "post", "publ", "book"},
    "post": {"post", "publ", "sched"},
    "calendar": {"calen", "event", "meeti", "appoi", "sched", "book"},
    "deploy": {"deplo", "relea", "ship"},
    "production": {"deplo", "relea", "ship"},
    "execute": {"execu", "run", "ran"},
    "code": {"execu", "run", "ran"},
}
_STRONG_PAST = (r"sent|emailed|scheduled|deployed|executed|booked|published|notified|pinged|reminded|texted|"
                r"messaged|queued|triggered|cancel(?:l)?ed|dispatched|posted")
_STRONG_BASE = r"send|email|schedule|deploy|execute|book|publish|notify|ping|remind|text|message|queue|trigger|cancel|dispatch|alert|post"
_STRONG_PROG = (r"sending|emailing|scheduling|deploying|executing|booking|publishing|notifying|pinging|"
                r"reminding|texting|messaging|queue?ing|triggering|cancel(?:l)?ing|dispatching|posting")
_AMBIG_PAST = r"created|saved|stored|set|updated|added|logged|recorded|deleted|removed|started|launched|ran|opened|closed"
_AMBIG_BASE = r"create|save|store|set|update|add|log|record|delete|remove|start|launch|run|open|close"
_AMBIG_PROG = r"creating|saving|storing|setting|updating|adding|logging|recording|deleting|removing|starting|launching|running|opening"
_ACTION_OBJECT_RE = re.compile(
    r"\b(?:reminders?|timers?|alarms?|notes?|events?|entry|entries|tasks?|jobs?|calendar|schedule|files?|records?|"
    r"backups?|builds?|scripts?|tests?|notifications?|meetings?|appointments?|deadlines?|goals?|projects?|drafts?|"
    r"emails?|messages?|releases?|deployments?|reservations?|tickets?|standups?|invites?|orders?)\b",
    re.IGNORECASE,
)
_SUBJ = r"\b(?:I|VECTOR|we)\b"
_ADV = r"(?:\s+(?:just|already|now|successfully|also|then|shortly|promptly|definitely|went\s+ahead\s+and))*"
_PAST_STRONG_RE = re.compile(rf"{_SUBJ}(?:['’]ve|\s+have|\s+had)?{_ADV}\s+(?:{_STRONG_PAST})\b", re.IGNORECASE)
_PAST_AMBIG_RE = re.compile(rf"{_SUBJ}(?:['’]ve|\s+have|\s+had)?{_ADV}\s+(?:{_AMBIG_PAST})\b", re.IGNORECASE)
_PROG_STRONG_RE = re.compile(rf"\b(?:I['’]m|I\s+am|VECTOR\s+is|we['’]re|we\s+are){_ADV}\s+(?:{_STRONG_PROG})\b", re.IGNORECASE)
_PROG_AMBIG_RE = re.compile(rf"\b(?:I['’]m|I\s+am|VECTOR\s+is|we['’]re|we\s+are){_ADV}\s+(?:{_AMBIG_PROG})\b", re.IGNORECASE)
_FUT_AUX = r"(?:['’]ll|\s+will|\s+shall|['’]m\s+going\s+to|\s+am\s+going\s+to|\s+is\s+going\s+to)"
_FUTURE_STRONG_RE = re.compile(
    rf"\b(?:I|VECTOR){_FUT_AUX}{_ADV}\s+(?:(?:{_STRONG_BASE})\b|get\s+back\s+to\s+you|follow\s+up|circle\s+back|check\s+in\s+(?:with|on))"
    rf"|\blet\s+me\s+(?:{_STRONG_BASE})\b",
    re.IGNORECASE,
)
_FUTURE_AMBIG_RE = re.compile(
    rf"\b(?:I|VECTOR){_FUT_AUX}{_ADV}\s+(?:{_AMBIG_BASE})\b|\blet\s+me\s+(?:{_AMBIG_BASE})\b",
    re.IGNORECASE,
)
_STATE_RE = re.compile(
    r"\b(?:the|your|that|this)\s+(?:deployment|reminder|email|message|timer|alarm|job|upload|backup|download|"
    r"notification|meeting|appointment|build|release)\s+(?:is|are)\s+(?:now\s+|currently\s+|already\s+)?"
    r"(?:running|underway|in\s+progress|scheduled|queued|set|being\s+\w+ed)\b"
    r"|\b(?:your|that)\s+(?:\w+\s+){0,2}(?:has|have)\s+been\s+(?:sent|scheduled|queued|deployed|booked|triggered|"
    r"cancel(?:l)?ed|created|saved)\b",
    re.IGNORECASE,
)
_BARE_DONE_RE = re.compile(r"^\W*(?:done|all\s+set|consider\s+it\s+done|on\s+it|will\s+do)\W*$", re.IGNORECASE)
_HEADER_RE = re.compile(
    r"\*{0,2}\s*actions?\s+(?:taken|performed|completed)\s*(?::\s*\*{0,2}|\*{0,2}\s*:)"
    r"|\*{0,2}\s*what\s+i\s+did\s*(?::\s*\*{0,2}|\*{0,2}\s*:)",
    re.IGNORECASE,
)
_NEGATION_RE = re.compile(r"\b(?:not|never|n['’]t|cannot|unable|without)\b", re.IGNORECASE)
_HYPOTHETICAL_BEFORE_RE = re.compile(
    r"\b(?:if|could|would|might|may|should|whether|unless|suggest|recommend|consider|happy\s+to|"
    r"want\s+me\s+to|like\s+me\s+to)\b",
    re.IGNORECASE,
)
_LINE_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

ACTION_CLAIM_HEADER_REPLY = (
    "I didn't take any action on that, sir — this was only a text reply and nothing was executed "
    "or scheduled. Tell me specifically what you'd like done and I'll route it through a real "
    "capability if one exists."
)
ACTION_CLAIM_NOTE = (
    "To be clear, sir — I haven't scheduled, sent or run anything from this reply; it's text only. "
    "Ask me directly and I'll route it through a real capability if one exists."
)


def _stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 2}


def _evidence_supports(sentence: str, kind: str, action_evidence) -> bool:
    """True when authoritative evidence backs this claim: a SUCCESSFUL
    execution of a lexically-matching action (or its synonym family); a
    future commitment additionally needs scheduling state."""
    claim = _stems(sentence)
    for rec in action_evidence or []:
        if str(rec.get("status", "")).lower() not in _SUCCESS_STATUSES:
            continue
        tokens = [t for t in str(rec.get("action_type", "")).lower().split("_") if t]
        action_stems = {t[:5] for t in tokens}
        for t in tokens:
            action_stems |= _CLAIM_FAMILIES.get(t, set())
        if not (claim & action_stems):
            continue
        if kind == "future" and not (
            rec.get("scheduled") or str(rec.get("status", "")).lower() == "scheduled"
            or _SCHEDULING_TOKENS & set(tokens)
        ):
            continue
        return True
    return False


def _claim_kind(sentence: str) -> str | None:
    """'past' | 'future' | None — the shape of an action claim in `sentence`
    after the negation / earlier-hypothetical guards."""
    has_object = bool(_ACTION_OBJECT_RE.search(sentence))
    for rx, ambiguous in ((_PAST_STRONG_RE, False), (_PAST_AMBIG_RE, True),
                          (_PROG_STRONG_RE, False), (_PROG_AMBIG_RE, True), (_STATE_RE, False)):
        if rx.search(sentence) and (has_object or not ambiguous) and not _NEGATION_RE.search(sentence):
            return "past"
    if _BARE_DONE_RE.match(sentence):
        return "past"
    for rx, ambiguous in ((_FUTURE_STRONG_RE, False), (_FUTURE_AMBIG_RE, True)):
        m = rx.search(sentence)
        if m and (has_object or not ambiguous):
            if _NEGATION_RE.search(sentence[: m.start()]) or _HYPOTHETICAL_BEFORE_RE.search(sentence[: m.start()]):
                continue
            return "future"
    return None


def remove_unsupported_action_claims(response: str, action_evidence=None) -> str:
    """Remove statements that VECTOR did / is doing / will do something when
    `action_evidence` (the authoritative execution/scheduling trace; empty on
    a pure-text path) does not back them. See the block comment above."""
    if not response:
        return response
    if _HEADER_RE.search(response):
        from loguru import logger
        logger.warning("[VECTOR][anti_fabrication] 'Action Taken' narration with no execution evidence — "
                       "replaced with an honest capability response")
        return ACTION_CLAIM_HEADER_REPLY

    dropped: list[str] = []
    out_lines: list[str] = []
    for line in response.split("\n"):
        kept: list[str] = []
        for sentence in _LINE_SENTENCE_SPLIT_RE.split(line):
            kind = _claim_kind(sentence) if sentence.strip() else None
            if kind and not _evidence_supports(sentence, kind, action_evidence):
                dropped.append(sentence.strip())
                continue
            kept.append(sentence)
        out_lines.append(" ".join(kept))
    if not dropped:
        return response

    from loguru import logger
    logger.warning("[VECTOR][anti_fabrication] removed unsupported action claim(s) (no matching "
                   "execution/scheduling evidence): {}", dropped)
    result = "\n".join(out_lines)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return f"{result}\n\n{ACTION_CLAIM_NOTE}" if result else ACTION_CLAIM_NOTE


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    _ok = defabricate_llm_answer(
        "✅ Stored permanently: favorite color = teal.", "store my favorite color"
    ) != "✅ Stored permanently: favorite color = teal."
    print("✅ anti_fabrication.py OK" if _ok else "❌ FAILED")
