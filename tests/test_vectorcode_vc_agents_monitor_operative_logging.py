"""Regression for vectorcode/src/vc_agents/monitor_operative.py:

the file used pure stdlib ``logging`` (never loguru) throughout, in
violation of CLAUDE.md's "loguru everywhere" rule, with %-style
placeholders that would silently break if/when this file is ever unified
with loguru (as its sibling operative.py already was). Also: 6
``except Exception:`` handlers discarded the real exception entirely,
logging only a generic "could not do X for operator Y" message.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

_PATH = "vectorcode/src/vc_agents/monitor_operative.py"
_SRC = Path(_PATH).read_text(encoding="utf-8")


def test_uses_loguru_not_stdlib_logging():
    assert "from loguru import logger" in _SRC
    assert "import logging" not in _SRC
    assert not re.search(r"^logger\s*=\s*logging\.getLogger", _SRC, re.MULTILINE)


def test_no_leftover_percent_style_placeholders_anywhere_including_multiline():
    found = []
    for m in re.finditer(r"logger\.(?:info|warning|error|debug|critical)\(", _SRC):
        start = m.start()
        depth = 0
        i = m.end() - 1
        while True:
            if _SRC[i] == "(":
                depth += 1
            elif _SRC[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        call = _SRC[start : i + 1]
        if re.search(r"%[sdr]", call):
            found.append(call)
    assert found == []


def test_except_blocks_capture_the_real_exception():
    bare_swallows = re.findall(r"except Exception:\n\s+logger\.debug\(", _SRC)
    assert bare_swallows == []
    assert _SRC.count("except Exception as e:") >= 5


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
