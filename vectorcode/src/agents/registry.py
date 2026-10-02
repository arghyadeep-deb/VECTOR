"""Runtime agent registry — register/get/list agents by name."""
from pathlib import Path

try:
    from core.config import CONFIG  # noqa: F401
except Exception:
    CONFIG = {}

from dataclasses import dataclass, field
from typing import Optional
from loguru import logger

@dataclass
class AgentDefinition:
    """Metadata for a single VECTOR agent."""

    name: str
    class_name: str
    district: str
    description: str
    model: str = "vector-fast"
    hp: int = 500
    capabilities: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)

class AgentRegistry:
    """Registry that stores and queries AgentDefinition objects by name."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentDefinition] = {}

    def register(self, defn: AgentDefinition) -> None:
        """Register (or overwrite) an agent definition."""
        self._agents[defn.name] = defn
        logger.debug(f"[VECTOR][registry] registered agent '{defn.name}' ({defn.class_name})")

    def get(self, name: str) -> Optional[AgentDefinition]:
        """Return the AgentDefinition for *name*, or None if not found."""
        return self._agents.get(name)

    def list_all(self) -> list[AgentDefinition]:
        """Return all registered agents sorted by name."""
        return sorted(self._agents.values(), key=lambda d: d.name)

    def search(self, query: str) -> list[AgentDefinition]:
        """Return agents whose name, class_name, district, description, or capabilities
        contain *query* as a case-insensitive keyword."""
        q = query.lower()
        results = []
        for defn in self._agents.values():
            haystack = " ".join([
                defn.name,
                defn.class_name,
                defn.district,
                defn.description,
                " ".join(defn.capabilities),
            ]).lower()
            if q in haystack:
                results.append(defn)
        return sorted(results, key=lambda d: d.name)

    def load_from_yaml(self, path: Path) -> int:
        """Load agent definitions from a YAML file (list of dicts).

        Returns the number of definitions loaded.
        """
        try:
            import yaml
            raw_list = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(raw_list, list):
                logger.warning(f"[VECTOR][registry] {path} must be a YAML list")
                return 0
            count = 0
            for item in raw_list:
                try:
                    defn = AgentDefinition(
                        name=item["name"],
                        class_name=item["class_name"],
                        district=item["district"],
                        description=item.get("description", ""),
                        model=item.get("model", "vector-fast"),
                        hp=int(item.get("hp", 500)),
                        capabilities=list(item.get("capabilities", [])),
                        config=dict(item.get("config", {})),
                    )
                    self.register(defn)
                    count += 1
                except Exception as e:
                    logger.warning(f"[VECTOR][registry] skip bad entry in {path}: {e}")
            return count
        except Exception as e:
            logger.error(f"[VECTOR][registry] load_from_yaml failed ({path}): {e}")
            return 0

    def load_from_directory(self, dir: Path) -> int:
        """Load all *.yaml and *.yml files from *dir*.

        Returns total number of definitions loaded.
        """
        total = 0
        if not dir.is_dir():
            logger.warning(f"[VECTOR][registry] directory not found: {dir}")
            return 0
        for yaml_file in sorted(dir.glob("*.yaml")) + sorted(dir.glob("*.yml")):
            total += self.load_from_yaml(yaml_file)
        logger.info(f"[VECTOR][registry] loaded {total} agent definitions from {dir}")
        return total

# ── Singleton ─────────────────────────────────────────────────────────────────

_registry: Optional[AgentRegistry] = None

_DEFINITIONS_DIR = Path(__file__).parent / "definitions"

def get_registry() -> AgentRegistry:
    """Return the global AgentRegistry singleton.

    On first call, auto-loads definitions from agents/definitions/ and from
    the hardcoded agent_types.py so the old and new systems are unified.
    """
    global _registry
    if _registry is not None:
        return _registry

    _registry = AgentRegistry()

    # Auto-load YAML definitions shipped with VectorCode
    if _DEFINITIONS_DIR.is_dir():
        _registry.load_from_directory(_DEFINITIONS_DIR)

    # Auto-load markdown-frontmatter agent definitions from vectorcode/agents/
    # (ingested from Claude Code via scripts/ingest_claude_assets.py)
    try:
        from agents.loader import definitions_from_markdown_dir
    except ImportError:
        try:
            from loader import definitions_from_markdown_dir  # type: ignore[no-reuse-declaration]
        except ImportError:
            definitions_from_markdown_dir = None

    if definitions_from_markdown_dir is not None:
        # vectorcode/agents/ lives at <repo>/vectorcode/agents/, two levels up from this file
        _MARKDOWN_AGENTS_DIR = Path(__file__).parent.parent.parent / "agents"
        try:
            md_count = 0
            for defn in definitions_from_markdown_dir(_MARKDOWN_AGENTS_DIR):
                if _registry.get(defn.name) is None:  # YAML wins over markdown
                    _registry.register(defn)
                    md_count += 1
            if md_count:
                logger.info(f"[VECTOR][registry] registered {md_count} markdown agents from {_MARKDOWN_AGENTS_DIR}")
        except Exception as e:
            logger.warning(f"[VECTOR][registry] markdown agents skipped: {e}")

    # Convert legacy agent_types.py hardcoded classes
    try:
        from agents.loader import definitions_from_agent_types
    except ImportError:
        try:
            from loader import definitions_from_agent_types  # type: ignore[no-reuse-declaration]
        except ImportError:
            definitions_from_agent_types = None

    if definitions_from_agent_types is not None:
        try:
            for defn in definitions_from_agent_types():
                if _registry.get(defn.name) is None:  # YAML wins over hardcoded
                    _registry.register(defn)
        except Exception as e:
            logger.warning(f"[VECTOR][registry] agent_types import skipped: {e}")

    return _registry

# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    reg = AgentRegistry()

    defn = AgentDefinition(
        name="test_coder",
        class_name="CoderAgent",
        district="coding",
        description="Writes Python code",
        model="vector-coder",
        hp=500,
        capabilities=["python", "typescript"],
    )
    reg.register(defn)

    assert reg.get("test_coder") is not None
    assert reg.get("nonexistent") is None
    assert len(reg.list_all()) == 1

    results = reg.search("python")
    assert len(results) == 1

    results = reg.search("xyz_no_match")
    assert len(results) == 0

    print("agents/registry.py OK")
