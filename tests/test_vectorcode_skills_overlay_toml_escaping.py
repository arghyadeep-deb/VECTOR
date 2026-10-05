"""Regression for vectorcode/src/skills/overlay.py's write_overlay()/_escape():

_escape() only handled backslash, double-quote, \\n, \\r, \\t -- but TOML's
basic-string grammar forbids ANY unescaped control character (U+0000-U+0008,
U+000B-U+001F, U+007F), including things like a stray vertical tab (\\x0b)
that could plausibly show up in DSPy/GEPA-generated optimizer output
(skill_name/description/few_shot text). Writing such a character produced a
syntactically invalid TOML file. SkillOverlayLoader.load() then failed to
parse it and returned None (by design -- "never raises, bad overlay files
should not break skill loading"), silently and permanently losing that
optimization result with only a logged warning as the trace.

Also converted overlay.py's logging from stdlib `logging.getLogger` (correct
under %-style substitution, but violates this project's "loguru everywhere"
rule) to loguru with {}-style placeholders.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from skills.overlay import SkillOverlay, SkillOverlayLoader, write_overlay, _escape


def test_escape_handles_toml_illegal_control_characters():
    # Vertical tab (0x0b) is not one of the "common" escapes (\n \r \t) the
    # old implementation handled, but TOML forbids it unescaped.
    assert _escape("bad\x0bchar") == "bad\\u000bchar"
    # \b and \f have dedicated short escapes in the TOML spec.
    assert _escape("a\bb\fc") == "a\\bb\\fc"
    # DEL (0x7f) must also be escaped.
    assert _escape("x\x7fy") == "x\\u007fy"
    # Existing common-case behavior must be unchanged.
    assert _escape('back\\slash "quote" new\nline') == 'back\\\\slash \\"quote\\" new\\nline'


def test_overlay_round_trips_through_write_and_load_with_control_character():
    root = Path(tempfile.mkdtemp())
    overlay = SkillOverlay(
        skill_name="test-skill",
        optimizer="dspy",
        optimized_at="2026-04-08T14:30:00Z",
        trace_count=3,
        description="bad\x0bchar in optimizer output",
        few_shot=[{"input": "q\x0b", "output": "a"}],
    )
    write_overlay(overlay, root)

    loaded = SkillOverlayLoader(root).load("test-skill")

    assert loaded is not None, (
        "the overlay must survive a write/load round-trip even when the "
        "content contains a TOML-illegal control character"
    )
    assert loaded.description == "bad\x0bchar in optimizer output"
    assert loaded.few_shot == [{"input": "q\x0b", "output": "a"}]


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
