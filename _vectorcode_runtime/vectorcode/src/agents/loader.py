"""Load agent definitions from YAML/TOML files, and from legacy agent_types.py."""
import re
from pathlib import Path

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
        model=raw.get("model", "vector-focus"),
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
        model=section.get("model", "vector-focus"),
        hp=int(section.get("hp", 500)),
        capabilities=list(section.get("capabilities", [])),
        config=dict(section.get("config", {})),
    )

# ── Model → model name heuristic ─────────────────────────────────────────────

_DOMAIN_MODELS: dict[str, str] = {
    "core":     "vector-coder",
    "security": "vector-reasoning",
    "devops":   "vector-coder",
    "research": "vector-reasoning",
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
            model = getattr(instance, "model", _DOMAIN_MODELS.get(domain, "vector-focus"))
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

# ── Markdown-frontmatter agent loader ────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

def _extract_frontmatter(text: str) -> dict | None:
    """Pull the YAML frontmatter from a markdown file (between leading ``---`` markers).

    Returns the parsed dict, or None if no frontmatter is present or YAML is missing.
    """
    # Skip any leading HTML comment block before frontmatter
    if text.lstrip().startswith("<!--"):
        end = text.find("-->")
        if end != -1:
            text = text[end + 3 :]
    m = _FRONTMATTER_RE.match(text.lstrip())
    if not m:
        return None
    try:
        import yaml
    except ImportError:
        logger.warning("[VECTOR][loader] PyYAML not installed — cannot parse markdown frontmatter")
        return None
    try:
        return yaml.safe_load(m.group(1)) or {}
    except Exception as e:
        logger.debug(f"[VECTOR][loader] frontmatter parse error: {e}")
        return None

def _slug_to_class_name(slug: str) -> str:
    """Convert 'vector-coder' → 'VectorCoderAgent', 'planner' → 'PlannerAgent'."""
    parts = re.split(r"[-_]", slug)
    return "".join(p.capitalize() for p in parts if p) + "Agent"

def _district_from_name(slug: str, description: str = "") -> str:
    """Infer a district from the agent slug or description.

    Maps known prefixes/keywords to existing VECTOR district names.
    Defaults to 'core' when no signal is found.
    """
    slug_lower = slug.lower()
    desc_lower = (description or "").lower()
    haystack = f"{slug_lower} {desc_lower}"

    rules = [
        ("security",   ("security", "auditor", "compliance", "vulnerab")),
        ("research",   ("research", "scout", "investigat", "explor", "intel")),
        ("comms",      ("comm", "messag", "telegram", "slack", "email", "phone")),
        ("ops",        ("devops", "deploy", "incident", "infra", "release")),
        ("planning",   ("plan", "architect", "strategist", "chief")),
        ("review",     ("review", "qa", "test", "lint", "quality")),
        ("ml",         ("ml-", "ai-", "engineer-ai", "ml_", "neural")),
        ("creative",   ("design", "creator", "writer", "marketing", "content")),
        ("finance",    ("finance", "tax", "investment", "budget", "trading")),
        ("project",    ("project-manager", "pm-", "project_manager")),
    ]
    for district, keywords in rules:
        if any(k in haystack for k in keywords):
            return district
    return "coding"  # safe default — most ingested agents are dev-flavored

def _model_from_frontmatter(model_value: object) -> str:
    """Map Claude/Anthropic model names to VECTOR Ollama models, pass-through otherwise."""
    if not model_value:
        return "vector-coder"
    raw = str(model_value).lower()
    mapping = {
        "opus": "vector-reasoning",
        "sonnet": "vector-coder",
        "haiku": "vector-focus",
        "claude-opus": "vector-reasoning",
        "claude-sonnet": "vector-coder",
        "claude-haiku": "vector-focus",
    }
    for needle, target in mapping.items():
        if needle in raw:
            return target
    # If already a vector-* model, keep it
    if raw.startswith("vector-"):
        return raw
    return "vector-coder"  # default fallback

def definitions_from_markdown_dir(dir: Path) -> list["AgentDefinition"]:
    """Walk *dir* and convert every ``*.md`` file with YAML frontmatter into
    :class:`AgentDefinition` records.

    Expected frontmatter keys (Claude-Code-compatible):
        name        — agent slug (default: filename stem)
        description — one-line description
        model       — model name (auto-mapped to vector-* if Claude-style)
        tools       — list of tool names (becomes capabilities)

    Files without YAML frontmatter are silently skipped.
    """
    results: list[AgentDefinition] = []
    if not dir.is_dir():
        logger.debug(f"[VECTOR][loader] markdown agent dir not found: {dir}")
        return results

    for md_file in sorted(dir.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"[VECTOR][loader] cannot read {md_file}: {e}")
            continue

        front = _extract_frontmatter(text)
        if not front:
            continue

        try:
            slug = str(front.get("name") or md_file.stem).strip()
            description = str(front.get("description") or f"Markdown-defined agent {slug}").strip()
            model = _model_from_frontmatter(front.get("model"))

            # Tools list → capabilities (lowercase, deduped)
            tools = front.get("tools") or []
            if isinstance(tools, str):
                tools = [t.strip() for t in tools.split(",") if t.strip()]
            capabilities = sorted({str(t).lower() for t in tools})

            defn = AgentDefinition(
                name=slug,
                class_name=_slug_to_class_name(slug),
                district=_district_from_name(slug, description),
                description=description,
                model=model,
                hp=int(front.get("hp", 500)),
                capabilities=capabilities,
                config={
                    "source": "markdown",
                    "source_path": str(md_file).replace("\\", "/"),
                },
            )
        except Exception as e:
            # One malformed frontmatter field (e.g. a non-numeric `hp:`) must
            # not take down every other agent in this directory -- this used
            # to raise uncaught, which propagates out of this function and
            # causes the caller (registry.py's get_registry()) to drop the
            # ENTIRE markdown-agent batch, not just this file.
            logger.warning(f"[VECTOR][loader] skipping malformed agent frontmatter in {md_file}: {e}")
            continue

        results.append(defn)

    logger.info(f"[VECTOR][loader] loaded {len(results)} agents from markdown ({dir})")
    return results

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
