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
    "requires_current_information",
    "current_information_plan",
    "current_information_decline_reply",
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
_PAPER_RE = re.compile(r"\b(?:papers?|research|studies|study|published|literature|preprints?|arxiv)\b", re.IGNORECASE)
_TOPIC_MARKER_RE = re.compile(r"\b(?:on|about|regarding|concerning|around)\s+(?P<topic>[^?.!]+)", re.IGNORECASE)
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
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-\+\.]*", matches[-1].group("topic"))
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
        m = _FABRICATED_COMPLETION_RE.search(s)
        if m and not m.group("neg"):
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


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    _ok = defabricate_llm_answer(
        "✅ Stored permanently: favorite color = teal.", "store my favorite color"
    ) != "✅ Stored permanently: favorite color = teal."
    print("✅ anti_fabrication.py OK" if _ok else "❌ FAILED")
