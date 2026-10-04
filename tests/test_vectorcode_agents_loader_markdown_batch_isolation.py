"""Regression for vectorcode/src/agents/loader.py's definitions_from_markdown_dir():

only the file-read step was wrapped in try/except -- building the
AgentDefinition itself (specifically int(front.get("hp", 500)) for a
non-numeric hp value) was not. One malformed agent .md file raised
uncaught out of the function entirely, and the caller (registry.py's
get_registry()) catches that at the batch level -- meaning the WHOLE
markdown-agent directory silently disappears from the registry, not just
the one bad file. Fixed: each file's AgentDefinition construction is now
isolated in its own try/except, so a bad file is skipped (with a warning)
and every other agent in the directory still loads.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

from agents.loader import definitions_from_markdown_dir


def _write(dir_: Path, filename: str, frontmatter: str) -> None:
    (dir_ / filename).write_text(f"---\n{frontmatter}\n---\n\nBody.\n", encoding="utf-8")


def test_one_malformed_file_does_not_drop_the_rest(tmp_path):
    _write(tmp_path, "good-one.md", "name: good-one\ndescription: A fine agent\n")
    _write(tmp_path, "bad.md", "name: bad\ndescription: Has a bogus hp\nhp: not-a-number\n")
    _write(tmp_path, "good-two.md", "name: good-two\ndescription: Another fine agent\n")

    results = definitions_from_markdown_dir(tmp_path)
    names = {d.name for d in results}

    assert "good-one" in names
    assert "good-two" in names
    assert "bad" not in names
    assert len(results) == 2


def test_all_good_files_load_normally(tmp_path):
    _write(tmp_path, "a.md", "name: a\ndescription: Agent A\n")
    _write(tmp_path, "b.md", "name: b\ndescription: Agent B\nhp: 700\n")

    results = definitions_from_markdown_dir(tmp_path)
    assert {d.name for d in results} == {"a", "b"}
    b = next(d for d in results if d.name == "b")
    assert b.hp == 700


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
