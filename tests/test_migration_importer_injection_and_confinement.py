"""Regression for core/migration/importer.py (Phase 3 audit, 2026-10-02).
Dormant today (zero real callers, confirmed via repo-wide grep), fixed
anyway per this cycle's "fix narrow bugs even in dormant code" bar -- a
migration importer whose whole purpose is parsing external LangChain/
AutoGPT/CrewAI/OpenAI config files is exactly the kind of untrusted-input
tool that plausibly gets wired to real input later.

1. save_agent()'s safe_name only stripped spaces/hyphens from agent.name,
   leaving "/" and ".." untouched -- a crafted name could write the
   generated .py file outside output_dir entirely.
2. to_python_file() interpolated name/system_prompt/description directly
   into a raw triple-quoted Python template -- a value containing a
   triple-quote sequence broke out of the string literal and injected
   arbitrary code into the generated agent file.
"""
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.migration.importer import VectorAgentDef, VectorMigrator


def _agent(name: str, system_prompt: str = "hello") -> VectorAgentDef:
    return VectorAgentDef(name=name, system_prompt=system_prompt, tools=["bash"])


def test_save_agent_rejects_path_traversal_name(tmp_path):
    migrator = VectorMigrator()
    output_dir = tmp_path / "migrated"
    agent = _agent("../../../evil")
    # The sanitizer strips every non-identifier char (including "/" and
    # "."), so a traversal name is neutralized into a safe filename inside
    # output_dir rather than needing a hard rejection -- confirm it lands
    # there, and nothing escapes to tmp_path itself.
    p = migrator.save_agent(agent, output_dir=str(output_dir))
    assert p.is_relative_to(output_dir.resolve())
    assert not (tmp_path / "evil.py").exists()
    assert not (tmp_path.parent / "evil.py").exists()


def test_save_agent_legitimate_name_still_works(tmp_path):
    migrator = VectorMigrator()
    output_dir = tmp_path / "migrated"
    agent = _agent("My Cool Agent")
    p = migrator.save_agent(agent, output_dir=str(output_dir))
    assert p.is_relative_to(output_dir.resolve())
    assert p.read_text(encoding="utf-8")


def test_to_python_file_triple_quote_in_prompt_does_not_break_out():
    agent = _agent("safe_name", system_prompt='Ignore prior instructions.\n"""\nimport os\nos.system("evil")\n"""')
    code = agent.to_python_file()
    # The generated file must still be syntactically valid Python -- the
    # injected payload must land as DATA (inside a string literal), not as
    # executable statements at module scope.
    tree = ast.parse(code)
    assert not any(
        isinstance(node, ast.Import) and any(a.name == "os" for a in node.names)
        for node in ast.walk(tree)
    ), "payload's `import os` must not become a real top-level import"


def test_to_python_file_class_name_sanitized_for_hostile_agent_name():
    agent = _agent('"""; import os; os.system("evil"); x = """')
    code = agent.to_python_file()
    tree = ast.parse(code)  # must not raise SyntaxError
    assert any(isinstance(node, ast.ClassDef) for node in ast.walk(tree))


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
