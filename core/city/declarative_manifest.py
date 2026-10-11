"""Declarative agent manifest loader for VECTOR.

Reads config/agent_manifest.yaml and materialises AgentDefinition objects
for the agent registry. Session 1 of the RunVectorRefactor plan — the
manifest YAML + this loader exist so bootstrap_agents() can be migrated
to manifest-driven loading in Session 2.

Usage:
    loader = ManifestLoader()
    definitions = loader.load("config/agent_manifest.yaml")
    loader.register_all(definitions, registry)
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from core.city.agent_base import AgentBase
    from vectorcode.src.agents.registry import AgentRegistry


_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


class ManifestLoader:
    """Load agent definitions from config/agent_manifest.yaml."""

    def __init__(self) -> None:
        self._district_names: tuple[str, ...] = ()

    def load(self, path: str | Path | None = None) -> list[dict]:
        """Load and validate the agent manifest YAML.

        Returns a flat list of agent dicts, each with at minimum:
            name, class, model, district, description, capabilities
        """
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML is required: pip install pyyaml")

        manifest_path = Path(path) if path else _PROJECT_ROOT / "config" / "agent_manifest.yaml"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Agent manifest not found: {manifest_path}")

        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        self.validate(raw)
        self._district_names = tuple(sorted(raw.get("districts", {}).keys()))

        agents: list[dict] = []
        for district_name, district_agents in raw.get("districts", {}).items():
            if not isinstance(district_agents, list):
                continue
            for entry in district_agents:
                agent = dict(entry)
                agent.setdefault("district", district_name)
                agent.setdefault("capabilities", [])
                agent.setdefault("description", "")
                agent.setdefault("hp_gate", 0)
                agents.append(agent)

        logger.info(
            "[VECTOR][manifest] loaded {} agents across {} districts from {}",
            len(agents),
            len(raw.get("districts", {})),
            manifest_path.name,
        )
        return agents

    def inventory(self, path: str | Path | None = None) -> dict:
        """Return canonical agent/district counts from the loaded manifest."""
        agents = self.load(path)
        return self.summarize(agents, district_names=self._district_names)

    @staticmethod
    def summarize(
        agents: list[dict], *, district_names: tuple[str, ...] = ()
    ) -> dict:
        """Summarize a flat manifest without instantiating agents."""
        from core.runtime.manifest_inventory import summarize_agents

        return summarize_agents(agents, district_names=district_names)

    def validate(self, raw: dict) -> None:
        """Raise ValueError on malformed manifest."""
        if not isinstance(raw, dict):
            raise ValueError("Manifest must be a YAML mapping at the top level")
        if "version" not in raw:
            raise ValueError("Manifest missing 'version' field")
        if "districts" not in raw:
            raise ValueError("Manifest missing 'districts' section")

        for district_name, entries in raw["districts"].items():
            if not isinstance(entries, list):
                raise ValueError(f"District '{district_name}' must be a list of agents")
            for i, entry in enumerate(entries):
                if "name" not in entry:
                    raise ValueError(f"Agent #{i} in '{district_name}' missing 'name'")
                if "class" not in entry:
                    raise ValueError(
                        f"Agent '{entry.get('name', i)}' in '{district_name}' missing 'class'"
                    )

    def instantiate_all(self, agents: list[dict]) -> list["AgentBase"]:
        """Import + instantiate each agent class.

        Skips agents whose class cannot be imported (logs a warning, never crashes).
        Returns only successfully instantiated instances.
        """
        instances: list["AgentBase"] = []
        for entry in agents:
            name = entry.get("name", "?")
            class_path: str = entry.get("class", "")
            if not class_path or "." not in class_path:
                logger.warning("[VECTOR][manifest] agent '{}' has invalid class path: {}", name, class_path)
                continue
            module_path, cls_name = class_path.rsplit(".", 1)
            try:
                module = importlib.import_module(module_path)
                cls = getattr(module, cls_name)
                instance = cls()
                instance.capabilities = list(entry.get("capabilities", []))
                instances.append(instance)
            except Exception as e:
                logger.debug("[VECTOR][manifest] skip '{}': {}", name, e)

        return instances

    def register_all(self, agents: list[dict], registry: "AgentRegistry") -> int:
        """Instantiate all agents from manifest dicts and register them.

        Returns the count of newly registered agents.
        """
        instances = self.instantiate_all(agents)
        registered = 0
        for agent in instances:
            if not registry.get(agent.id):
                registry.register(agent)
                registered += 1
        return registered


if __name__ == "__main__":
    loader = ManifestLoader()
    try:
        agents = loader.load()
        print(f"OK — {len(agents)} agents defined across all districts")
        for a in agents[:5]:
            print(f"  {a['district']}/{a['name']} -> {a['class']}")
        if len(agents) > 5:
            print(f"  ... and {len(agents) - 5} more")
    except Exception as e:
        print(f"FAILED: {e}")
