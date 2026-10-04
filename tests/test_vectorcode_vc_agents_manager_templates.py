"""Regression for vectorcode/src/vc_agents/manager.py's AgentManager.list_templates():

the built-in-templates loader used
``importlib.resources.files("vector.agents") / "templates"`` -- but package
"vector.agents" does not exist anywhere in this repo (confirmed:
ModuleNotFoundError every single time). The broad ``except Exception`` around
it silently swallowed this, logged only at debug level, and returned zero
built-in templates on every call, forever. The real templates
(code_reviewer.toml, inbox_triager.toml, personal_deep_research.toml,
research_monitor.toml) live in vc_agents/templates/, right next to this file.
Fixed by resolving the directory relative to ``__file__`` instead of a
package resource lookup that never worked.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_list_templates_finds_the_real_builtin_templates():
    from vectorcode.src.vc_agents.manager import AgentManager

    templates = AgentManager.list_templates()
    ids = {t.get("id") for t in templates}
    builtin = [t for t in templates if t.get("source") == "built-in"]

    assert len(builtin) >= 4, "expected at least the 4 known built-in templates"
    assert {"code_reviewer", "inbox_triager", "personal_deep_research", "research_monitor"} <= ids


def test_templates_dir_resolves_next_to_manager_py():
    tpl_dir = Path("vectorcode/src/vc_agents/templates")
    assert tpl_dir.is_dir()
    toml_files = list(tpl_dir.glob("*.toml"))
    assert len(toml_files) >= 4


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
