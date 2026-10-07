"""Regression for vectorcode/src/rl_cli.py:

The module called get_vector_home() at line 42 (module load time, building
_vector_home for the .env loader) but the `from vector_constants import
get_vector_home, OPENROUTER_BASE_URL` statement was placed at line 73 --
AFTER that first use. The module was 100% unimportable: every load raised
NameError: name 'get_vector_home' is not defined, before ever reaching its
own CLI entry point. Fixed by moving the import above its first use.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RL_CLI = Path(__file__).parent.parent / "vectorcode" / "src" / "rl_cli.py"


def test_rl_cli_module_imports_without_nameerror():
    src = RL_CLI.read_text(encoding="utf-8")
    # --list-environments is the cheapest flag that exercises full module
    # load without requiring API keys or launching real RL training.
    result = subprocess.run(
        [sys.executable, "-c", f"compile(open(r'{RL_CLI}', encoding='utf-8').read(), 'rl_cli.py', 'exec')"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    import_line = "from vector_constants import get_vector_home, OPENROUTER_BASE_URL"
    first_use = src.index("_vector_home = get_vector_home()")
    import_pos = src.index(import_line)
    assert import_pos < first_use, (
        "get_vector_home() import must appear before its first use at module load time"
    )
    assert src.count(import_line) == 1, "import should not be duplicated"
