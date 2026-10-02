"""Regression for vectorcode/src/agents/registry.py's load_from_yaml():
had a nonsensical dead line (`defn = load_yaml_definition.__func__ if False
else None  # unreachable`) immediately overwritten on the next line -- zero
functional effect, but confusing dead code, plus an unused
load_yaml_definition import. Cleaned up; confirms load_from_yaml still
works correctly end to end.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vectorcode.src.agents.registry import AgentRegistry


def test_load_from_yaml_still_registers_entries(tmp_path):
    yaml_file = tmp_path / "agents.yaml"
    yaml_file.write_text(
        "- name: test_agent\n"
        "  class_name: TestAgent\n"
        "  district: coding\n"
        "  description: a test agent\n"
    )
    reg = AgentRegistry()
    count = reg.load_from_yaml(yaml_file)
    assert count == 1
    defn = reg.get("test_agent")
    assert defn is not None
    assert defn.class_name == "TestAgent"


def test_load_from_yaml_skips_bad_entries_without_crashing(tmp_path):
    yaml_file = tmp_path / "agents.yaml"
    yaml_file.write_text(
        "- name: good_agent\n"
        "  class_name: GoodAgent\n"
        "  district: coding\n"
        "  description: fine\n"
        "- class_name: MissingName\n"
        "  district: coding\n"
        "  description: missing the name key\n"
    )
    reg = AgentRegistry()
    count = reg.load_from_yaml(yaml_file)
    assert count == 1
    assert reg.get("good_agent") is not None


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
