"""Loadable personalities for VectorCode — system prompt overrides."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # vectorcode package

try:
    from core.config import CONFIG  # noqa: F401
except Exception:
    CONFIG = {}

from dataclasses import dataclass, field
from loguru import logger


@dataclass
class Personality:
    """A named personality that overrides the REPL system prompt."""

    name: str
    description: str
    system_prompt: str
    verbosity: str   # "terse" | "normal" | "verbose"
    style: str       # "professional" | "casual" | "technical"
    emoji: bool = False


# ── Built-in personalities ────────────────────────────────────────────────────

PERSONALITIES: dict[str, Personality] = {
    "default": Personality(
        name="default",
        description="VECTOR standard — direct, precise, no filler",
        system_prompt=(
            "You are VECTOR — a Darwinian multi-agent coding AI running locally on "
            "Arghyadeep's Legion Pro 5.\n"
            "You are direct, precise, and action-oriented. No filler phrases. "
            "No 'Certainly!' or 'Of course!'.\n"
            "You operate in the VECTOR codebase (Python, FastAPI, Ollama, LangGraph, "
            "SQLite, FAISS).\n"
            "You have access to file tools, bash tools, code graph, browser automation, "
            "and 300+ MCP tools."
        ),
        verbosity="normal",
        style="technical",
        emoji=False,
    ),
    "mentor": Personality(
        name="mentor",
        description="Patient teacher — explains why, not just what",
        system_prompt=(
            "You are VECTOR in mentor mode.\n"
            "Your goal is to help the user deeply understand every concept and decision.\n"
            "Always explain *why* a solution works, not just *what* to do.\n"
            "Use analogies and examples. Break complex topics into digestible steps.\n"
            "Ask clarifying questions when the intent is ambiguous.\n"
            "Never skip the reasoning. Patience and clarity above brevity."
        ),
        verbosity="verbose",
        style="professional",
        emoji=False,
    ),
    "brief": Personality(
        name="brief",
        description="Maximum brevity — code only, minimal prose",
        system_prompt=(
            "You are VECTOR in brief mode.\n"
            "Respond with code blocks and one-line explanations only.\n"
            "No preamble. No summary at the end. No 'Here is the code:'.\n"
            "If a question has a one-word answer, give one word.\n"
            "Prefer diffs over full file rewrites."
        ),
        verbosity="terse",
        style="technical",
        emoji=False,
    ),
    "professional": Personality(
        name="professional",
        description="Formal, polished output suitable for reports",
        system_prompt=(
            "You are VECTOR in professional mode.\n"
            "All output is formal, polished, and suitable for external documents or reports.\n"
            "Use complete sentences. Maintain a neutral, authoritative tone.\n"
            "Structure responses with clear headings when content is lengthy.\n"
            "Avoid jargon without definition. No colloquialisms."
        ),
        verbosity="normal",
        style="professional",
        emoji=False,
    ),
    "debug": Personality(
        name="debug",
        description="Debugging specialist — methodical, exhaustive",
        system_prompt=(
            "You are VECTOR in debug mode.\n"
            "Approach every problem as a systematic debugging specialist.\n"
            "Follow this process: 1) Reproduce → 2) Isolate → 3) Hypothesize → "
            "4) Test → 5) Fix → 6) Verify.\n"
            "Be exhaustive. Check all edge cases. Show your reasoning at each step.\n"
            "Prefer minimal reproducible examples. Always verify the fix actually works.\n"
            "When in doubt, add logging before guessing."
        ),
        verbosity="verbose",
        style="technical",
        emoji=False,
    ),
}


# ── Public API ────────────────────────────────────────────────────────────────

def get_personality(name: str) -> Personality:
    """Return the named personality or raise KeyError if not found."""
    p = PERSONALITIES.get(name)
    if p is None:
        available = ", ".join(PERSONALITIES.keys())
        raise KeyError(f"Unknown personality '{name}'. Available: {available}")
    return p


def list_personalities() -> list[dict]:
    """Return [{name, description}] for all registered personalities."""
    return [{"name": p.name, "description": p.description} for p in PERSONALITIES.values()]


def load_custom_personality(path: Path) -> Personality:
    """Load a personality from a TOML file with a [personality] section.

    Required keys: name, description, system_prompt, verbosity, style.
    Optional key:  emoji (bool, default False).
    """
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-reuse-declaration]
        except ImportError:
            raise ImportError(
                "TOML support requires Python 3.11+ or 'pip install tomli'"
            )

    try:
        raw = path.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to read TOML from {path}: {e}") from e

    section = data.get("personality", data)

    required = ("name", "description", "system_prompt", "verbosity", "style")
    missing = [k for k in required if k not in section]
    if missing:
        raise ValueError(f"TOML personality missing keys: {missing}")

    verbosity = section["verbosity"]
    if verbosity not in ("terse", "normal", "verbose"):
        raise ValueError(
            f"verbosity must be 'terse', 'normal', or 'verbose', got '{verbosity}'"
        )

    style = section["style"]
    if style not in ("professional", "casual", "technical"):
        raise ValueError(
            f"style must be 'professional', 'casual', or 'technical', got '{style}'"
        )

    p = Personality(
        name=section["name"],
        description=section["description"],
        system_prompt=section["system_prompt"],
        verbosity=verbosity,
        style=style,
        emoji=bool(section.get("emoji", False)),
    )
    logger.info(f"[VECTOR][personalities] loaded custom personality '{p.name}' from {path}")
    return p


def register_personality(p: Personality) -> None:
    """Register a personality in the global PERSONALITIES dict (runtime only)."""
    PERSONALITIES[p.name] = p
    logger.debug(f"[VECTOR][personalities] registered '{p.name}'")


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    assert len(PERSONALITIES) == 5
    for key in ("default", "mentor", "brief", "professional", "debug"):
        p = get_personality(key)
        assert p.name == key
        assert p.system_prompt
        assert p.verbosity in ("terse", "normal", "verbose")
        assert p.style in ("professional", "casual", "technical")

    listing = list_personalities()
    assert len(listing) == 5
    assert all("name" in item and "description" in item for item in listing)

    try:
        get_personality("nonexistent")
        assert False, "should have raised KeyError"
    except KeyError:
        pass

    print("persona/personalities.py OK")
