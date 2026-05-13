"""Load agent definitions from YAML/TOML files, and from legacy agent_types.py."""
import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))  # project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # vectorcode package

try:
    from core.config import CONFIG  # noqa: F401
except Exception:
    CONFIG = {}

from loguru import logger

# Import AgentDefinition without triggering circular imports through __init__
try:
    from agents.registry import AgentDefinition
except ImportError:
    from registry import AgentDefinition  # type: ignore[no-reuse-declaration]


def load_yaml_definition(path: Path) -> "AgentDefinition":
    """Load a single YAML file into an AgentDefinition.

    The YAML must be a mapping with keys: name, class_name, district, description.
    Optional keys: model, hp, capabilities, config.
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required: pip install pyyaml")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to parse YAML from {path}: {e}") from e

    if not isinstance(raw, dict):
        raise ValueError(f"{path} must be a YAML mapping (got {type(raw).__name__})")

    required = ("name", "class_name", "district", "description")
    missing = [k for k in required if k not in raw]
    if missing:
        raise ValueError(f"{path} missing required keys: {missing}")

    return AgentDefinition(
        name=raw["name"],
        class_name=raw["class_name"],
        district=raw["district"],
        description=raw["description"],
        model=raw.get("model", "vector-fast"),
        hp=int(raw.get("hp", 500)),
        capabilities=list(raw.get("capabilities", [])),
        config=dict(raw.get("config", {})),
    )


def load_toml_definition(path: Path) -> "AgentDefinition":
    """Load a TOML file with an [agent] section into an AgentDefinition.

    Required keys under [agent]: name, class_name, district, description.
    Optional keys: model, hp, capabilities, config.
    """
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-reuse-declaration]
        except ImportError:
            raise ImportError("TOML support requires Python 3.11+ or 'pip install tomli'")

    try:
        raw = tomllib.loads(path.read_bytes().decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to parse TOML from {path}: {e}") from e

    section = raw.get("agent", raw)

    required = ("name", "class_name", "district", "description")
    missing = [k for k in required if k not in section]
    if missing:
        raise ValueError(f"{path} [agent] missing required keys: {missing}")

    return AgentDefinition(
        name=section["name"],
        class_name=section["class_name"],
        district=section["district"],
        description=section["description"],
        model=section.get("model", "vector-fast"),
        hp=int(section.get("hp", 500)),
        capabilities=list(section.get("capabilities", [])),
        config=dict(section.get("config", {})),
    )


# ── Model → model name heuristic ─────────────────────────────────────────────

_DOMAIN_MODELS: dict[str, str] = {
    "core":     "vector-coder",
    "security": "vector-reasoning",
    "devops":   "vector-coder",
    "research": "vector-deep",
    "support":  "vector-focus",
}


def definitions_from_agent_types() -> list["AgentDefinition"]:
    """Convert the hardcoded agent_types.py into a list of AgentDefinition objects.

    Reads agent_types module, inspects every class ending in 'Agent' that
    is not AgentBase, and produces definitions from its attributes.
    """
    results: list[AgentDefinition] = []

    try:
        import agent_types as at
        import inspect
        agent_classes = [
            (name, cls)
            for name, cls in inspect.getmembers(at, inspect.isclass)
            if name.endswith("Agent") and name != "AgentBase"
        ]
    except Exception as e:
        logger.warning(f"[VECTOR][loader] could not import agent_types: {e}")
        return results

    for class_name, cls in agent_classes:
        try:
            # Instantiate to read domain + model attributes
            instance = cls()
            domain = getattr(instance, "domain", "core")
            model = getattr(instance, "model", _DOMAIN_MODELS.get(domain, "vector-fast"))
            agent_name = _class_name_to_slug(class_name)
            results.append(AgentDefinition(
                name=agent_name,
                class_name=class_name,
                district=domain,
                description=f"{class_name} — {domain} domain",
                model=model,
                hp=getattr(instance, "hp", 500),
                capabilities=[domain],
            ))
        except Exception as e:
            logger.debug(f"[VECTOR][loader] skipping {class_name}: {e}")

    logger.info(f"[VECTOR][loader] extracted {len(results)} definitions from agent_types.py")
    return results


def _class_name_to_slug(class_name: str) -> str:
    """Convert 'CoderAgent' → 'coder', 'SecurityAuditorAgent' → 'security_auditor'."""
    name = class_name
    if name.endswith("Agent"):
        name = name[:-5]
    # Insert underscore before uppercase-lowercase boundaries
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()


# ── Self-test ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    assert _class_name_to_slug("CoderAgent") == "coder"
    assert _class_name_to_slug("SecurityAuditorAgent") == "security_auditor"
    assert _class_name_to_slug("GitBotAgent") == "git_bot"
    assert _class_name_to_slug("MLEngineerAgent") == "ml_engineer"

    # Test definitions_from_agent_types (tolerates import failure gracefully)
    defns = definitions_from_agent_types()
    print(f"  definitions_from_agent_types: {len(defns)} agents loaded")

    print("agents/loader.py OK")
