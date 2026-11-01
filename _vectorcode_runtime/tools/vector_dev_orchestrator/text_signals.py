"""Shared deterministic negation-aware phrase matching.

Used by approval.py (risky-keyword detection) and router.py (task-category
classification) so both apply the SAME narrow, explicitly-scoped negation
heuristic rather than maintaining two divergent copies. See approval.py's
original docstring/comments for the full rationale: this deliberately does
NOT attempt general NLP. It only suppresses a phrase match when a
recognized negation lead-in ("do not", "never", ...) precedes it within the
same sentence, with no coordinating "but/however/..." reset in between.
Anything outside that narrow shape fails closed (still matches), by design.
"""

from __future__ import annotations

import re

NEGATION_LEAD_INS: tuple[str, ...] = (
    "do not",
    "don't",
    "does not",
    "doesn't",
    "must not",
    "mustn't",
    "should not",
    "shouldn't",
    "never",
    "avoid",
)

NEGATION_RESET_WORDS: tuple[str, ...] = (
    "but",
    "however",
    "except",
    "unless",
    "although",
    "though",
)

_SENTENCE_SPLIT_RE = re.compile(r"[.!?;]+")
_STATE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def norm_repo_path(path: str) -> str:
    """Forward-slash a repo-relative path and drop only leading "./" prefixes.

    Never `lstrip("./")`: that strips *characters*, turning "../x" into "x"
    and ".claude/x" into "claude/x".
    """

    text = path.replace("\\", "/").strip()

    while text.startswith("./"):
        text = text[2:]

    return text


def safe_state_id(value: str, *, field: str) -> str:
    """Validate an identifier before using it as a state-file name."""

    if not isinstance(value, str) or not _STATE_ID_RE.fullmatch(value):
        raise ValueError(f"{field} must be a plain state identifier")
    if value in {".", ".."}:
        raise ValueError(f"{field} must not be a relative path component")
    return value


def normalize(text: str) -> str:
    """Lowercase and collapse whitespace, matching approval.py's original."""

    return " ".join(text.lower().split())


def split_sentences(normalized_text: str) -> list[str]:
    """Split normalized text into sentences on . ! ? ;"""

    return _SENTENCE_SPLIT_RE.split(normalized_text)


def is_negated_occurrence(
    sentence: str,
    phrase_start: int,
) -> bool:
    """Whether the phrase at phrase_start is inside a negated clause."""

    prefix = sentence[:phrase_start]

    last_negation_end = -1

    for lead_in in NEGATION_LEAD_INS:
        idx = prefix.rfind(lead_in)

        if idx == -1:
            continue

        # Require a whole-word negation lead-in (not a substring of a
        # longer word or contraction).
        if idx > 0 and (
            prefix[idx - 1].isalnum() or prefix[idx - 1] == "'"
        ):
            continue

        end = idx + len(lead_in)

        if end > last_negation_end:
            last_negation_end = end

    if last_negation_end == -1:
        return False

    between = prefix[last_negation_end:]

    return not any(
        reset in between
        for reset in NEGATION_RESET_WORDS
    )


def phrase_triggers(
    sentences: list[str],
    phrases: tuple[str, ...],
) -> bool:
    """Whether any phrase occurs in any sentence outside a negated clause."""

    for phrase in phrases:
        for sentence in sentences:
            start = 0
            while True:
                idx = sentence.find(phrase, start)
                if idx == -1:
                    break
                if not is_negated_occurrence(sentence, idx):
                    return True
                start = idx + 1
    return False


def text_triggers(
    text: str,
    phrases: tuple[str, ...],
) -> bool:
    """Convenience: normalize + split + phrase_triggers in one call."""

    normalized = normalize(text)
    sentences = split_sentences(normalized)
    return phrase_triggers(sentences, phrases)


def _self_test() -> None:
    # Regression: lstrip("./") ate leading dots ("../x" -> "x", ".claude/x" -> "claude/x").
    assert norm_repo_path("../x.py") == "../x.py"
    assert norm_repo_path(".claude/settings.json") == ".claude/settings.json"
    assert norm_repo_path("./core\\a.py") == "core/a.py"
    assert norm_repo_path("././a.py") == "a.py"
    assert norm_repo_path("/abs/x") == "/abs/x"
    assert text_triggers(
        "Change authentication security and deploy to production.",
        ("security",),
    )

    assert not text_triggers(
        "Do not change dependencies, architecture, permissions, "
        "security code, database schema, or production configuration.",
        ("architecture",),
    )

    assert not text_triggers(
        "Do not change dependencies, architecture, permissions, "
        "security code, database schema, or production configuration.",
        ("security",),
    )

    assert text_triggers(
        "Do not skip the review. Deploy to production now.",
        ("production",),
    )

    assert text_triggers(
        "Do not deploy to production, but please push to master now.",
        ("push to master",),
    )

    assert not text_triggers(
        "Do not deploy to production, but please push to master now.",
        ("production",),
    )

    assert not text_triggers(
        "",
        ("anything",),
    )


if __name__ == "__main__":
    _self_test()
