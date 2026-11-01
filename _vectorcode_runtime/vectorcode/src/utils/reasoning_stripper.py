"""Strip <think>...</think> and <REASONING_SCRATCHPAD>...</REASONING_SCRATCHPAD> tags
from model output before it is shown to the user.

Preserves the reasoning content for trajectory saving.
"""
import re

try:
    from core.config import CONFIG  # noqa: F401
except Exception:
    CONFIG = {}


# ── Compiled patterns ─────────────────────────────────────────────────────────

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_SCRATCHPAD_RE = re.compile(
    r"<REASONING_SCRATCHPAD>.*?</REASONING_SCRATCHPAD>", re.DOTALL
)
_OPEN_THINK_RE = re.compile(r"<think>.*$", re.DOTALL)   # incomplete tag (streaming)
_THINK_CONTENT_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)
_SCRATCHPAD_CONTENT_RE = re.compile(
    r"<REASONING_SCRATCHPAD>(.*?)</REASONING_SCRATCHPAD>", re.DOTALL
)


# ── Public API ─────────────────────────────────────────────────────────────────

def strip_reasoning(text: str) -> str:
    """Remove <think> and <REASONING_SCRATCHPAD> blocks from *text*.

    Collapses resulting excess whitespace to at most two consecutive newlines.
    """
    cleaned = _THINK_RE.sub("", text)
    cleaned = _SCRATCHPAD_RE.sub("", cleaned)
    # Collapse runs of blank lines left behind by tag removal
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def extract_reasoning(text: str) -> tuple[str, str]:
    """Return (clean_text, reasoning_content).

    *clean_text* has all reasoning tags removed.
    *reasoning_content* contains the concatenated content of every reasoning
    block found, separated by newlines.
    """
    think_parts = _THINK_CONTENT_RE.findall(text)
    scratchpad_parts = _SCRATCHPAD_CONTENT_RE.findall(text)
    reasoning = "\n".join(think_parts + scratchpad_parts).strip()
    return strip_reasoning(text), reasoning


def has_incomplete_reasoning(text: str) -> bool:
    """Return True if the text contains an opening <think> without a closing </think>.

    Useful during streaming to detect that the model is mid-reasoning and the
    output should not yet be shown to the user.
    """
    open_count = text.count("<think>")
    close_count = text.count("</think>")
    return open_count > close_count


def convert_scratchpad_to_think(text: str) -> str:
    """Replace REASONING_SCRATCHPAD tags with think tags.

    Used when saving trajectories in a canonical format for LLM training.
    """
    converted = text.replace(
        "<REASONING_SCRATCHPAD>", "<think>"
    ).replace(
        "</REASONING_SCRATCHPAD>", "</think>"
    )
    return converted


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # strip_reasoning — think tags
    sample1 = "Hello <think>I should say something helpful</think> world"
    assert strip_reasoning(sample1) == "Hello  world".strip() or "Hello" in strip_reasoning(sample1)

    result = strip_reasoning(sample1)
    assert "<think>" not in result
    assert "I should say something helpful" not in result
    assert "world" in result

    # strip_reasoning — scratchpad tags
    sample2 = "Answer: 42 <REASONING_SCRATCHPAD>Because the universe</REASONING_SCRATCHPAD>"
    result2 = strip_reasoning(sample2)
    assert "<REASONING_SCRATCHPAD>" not in result2
    assert "42" in result2

    # strip_reasoning — no tags
    plain = "Just a plain response."
    assert strip_reasoning(plain) == plain

    # extract_reasoning
    sample3 = "<think>step 1\nstep 2</think>\nFinal answer."
    clean, reasoning = extract_reasoning(sample3)
    assert "Final answer" in clean
    assert "step 1" in reasoning
    assert "<think>" not in clean

    # has_incomplete_reasoning
    assert has_incomplete_reasoning("<think>still thinking") is True
    assert has_incomplete_reasoning("<think>done</think>") is False
    assert has_incomplete_reasoning("no tags here") is False

    # convert_scratchpad_to_think
    sample4 = "<REASONING_SCRATCHPAD>my thoughts</REASONING_SCRATCHPAD>"
    converted = convert_scratchpad_to_think(sample4)
    assert "<think>" in converted
    assert "<REASONING_SCRATCHPAD>" not in converted

    # Multi-block strip
    multi = "<think>A</think> text <think>B</think> end"
    assert strip_reasoning(multi) == "text  end" or "text" in strip_reasoning(multi)
    assert "<think>" not in strip_reasoning(multi)

    print("utils/reasoning_stripper.py OK")
