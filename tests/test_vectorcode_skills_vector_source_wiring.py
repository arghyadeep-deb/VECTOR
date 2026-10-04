"""Regression: cli/skill_cmd.py's _get_resolver("vector") was wired to the
wrong VectorSkillResolver.

vectorcode/src/skills/sources/vector.py (now deleted) defined a stub
VectorSkillResolver that didn't even inherit from SourceResolver -- it had
only a resolve() method that unconditionally returned None, with no
sync()/list_skills()/cache_dir(). vectorcode/src/skills/sources/vector_source.py
defines a second, fully-functional class with the exact same name
(VectorSkillResolver(SourceResolver)) -- a complete implementation with a
real sync()/list_skills()/cache_dir(). cli/skill_cmd.py imported from the
first (broken) module, so the "vector" skill source was 100% non-functional
in production (any call to .sync() or .list_skills() raised AttributeError)
while the correct implementation sat unreachable. Fixed the import to
point at vector_source instead, and deleted the dead stub file.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))


def test_vector_source_module_no_longer_exists():
    assert not (
        Path(__file__).parent.parent
        / "vectorcode" / "src" / "skills" / "sources" / "vector.py"
    ).exists()


def test_cli_skill_cmd_resolves_vector_to_the_real_implementation():
    # Import through the same fully-qualified path cli/skill_cmd.py itself
    # uses (vectorcode.src...), not the bare "skills..." path -- Python
    # treats those as two distinct module objects for the same file, which
    # would make an isinstance() check below fail for an unrelated reason.
    from cli.skill_cmd import _get_resolver
    from vectorcode.src.skills.sources.vector_source import VectorSkillResolver
    from vectorcode.src.skills.sources.base import SourceResolver

    resolver = _get_resolver("vector")
    assert isinstance(resolver, VectorSkillResolver)
    assert isinstance(resolver, SourceResolver)
    # The real implementation exposes the full SourceResolver interface --
    # the broken stub this replaces had none of these.
    assert hasattr(resolver, "sync")
    assert hasattr(resolver, "list_skills")
    assert callable(resolver.cache_dir)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
