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

__all__ = ["defabricate_llm_answer"]

_CHECKMARK_RE = re.compile(r"[✅✔️☑]\s*")

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
