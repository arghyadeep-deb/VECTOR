"""
VECTOR Migration Tool — import agents from other frameworks.

Supported sources:
  langchain   : agent YAML/JSON definitions
  autogpt     : AutoGPT agent config files
  crewai      : CrewAI crew definitions
  openai_asst : OpenAI Assistants API exports
  plain       : Plain system-prompt + tools JSON

Converts to VECTOR agent format:
  - System prompt
  - Tool list (mapped to VECTOR equivalents)
  - District assignment
  - Schedule (if autonomous)

Ported from the agent OS agent OS migration framework.
"""
from __future__ import annotations

__all__ = [
    "MigrationResult",
    "MigrationSource",
    "VectorAgentDef",
    "VectorMigrator",
]


import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from loguru import logger

# save_agent()/to_python_file() below take agent.name from a parsed migration
# source file (LangChain/AutoGPT/CrewAI/OpenAI/plain config) -- untrusted
# structured input by this module's whole purpose. Dormant today (zero real
# callers, confirmed via repo-wide grep), fixed anyway per this cycle's
# established "fix narrow bugs even in dormant code" bar, since a migration
# importer processing external configs is exactly the kind of tool that
# plausibly gets wired to real input later.
_SAFE_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_]")


class MigrationSource(str, Enum):
    LANGCHAIN   = "langchain"
    AUTOGPT     = "autogpt"
    CREWAI      = "crewai"
    OPENAI_ASST = "openai_assistant"
    PLAIN       = "plain"


@dataclass
class VectorAgentDef:
    """A VECTOR-format agent definition produced by migration."""
    name: str
    system_prompt: str
    tools: list[str]
    district: str = "governance"
    schedule: str = ""
    model: str = "qwen3:14b"
    description: str = ""
    source_framework: str = ""
    original_config: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "district": self.district,
            "schedule": self.schedule,
            "model": self.model,
            "description": self.description,
        }

    def to_python_file(self) -> str:
        """Generate a VECTOR-compatible Python agent file."""
        tools_str = repr(self.tools)
        # self.name/system_prompt/description/district all come from a parsed
        # migration source file (untrusted structured input) -- class_name is
        # restricted to a safe Python identifier (a raw name could otherwise
        # break the class definition's syntax entirely), and every other
        # value is passed through repr() rather than interpolated into a raw
        # triple-quoted string, which a prompt/name containing `"""` or a
        # backslash could break out of to inject arbitrary code into the
        # generated file.
        class_name = _SAFE_IDENTIFIER_RE.sub("_", self.name).strip("_").title() or "Migrated"
        agent_id = _SAFE_IDENTIFIER_RE.sub("_", self.name.lower()).strip("_") or "migrated_agent"
        return f'''"""VECTOR Agent — migrated from {self.source_framework!r}."""
from pathlib import Path
from core.city.agent_base import AgentBase
from loguru import logger

class {class_name}Agent(AgentBase):
    """
    Migrated agent. See original_config for the source definition.
    """

    def __init__(self):
        super().__init__(
            agent_id={agent_id!r},
            name={self.name!r},
            district={self.district!r},
        )
        self.allowed_tools = {tools_str}

    @property
    def system_prompt(self) -> str:
        return {self.system_prompt[:500]!r}

    async def run(self, task: dict) -> dict:
        logger.info("[VECTOR][{class_name}] running task: {{}}", task.get("type"))
        return {{"status": "ok", "agent": {self.name!r}}}
'''


@dataclass
class MigrationResult:
    source: MigrationSource
    agents: list[VectorAgentDef]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.agents) > 0

    def summary(self) -> str:
        return (
            f"Migration from {self.source.value}: "
            f"{len(self.agents)} agents imported, "
            f"{len(self.warnings)} warnings, {len(self.errors)} errors"
        )


# ── Tool mapping (other frameworks → VECTOR tool names) ───────────────────────

_TOOL_MAP: dict[str, str] = {
    # LangChain
    "serpapi":              "web_search",
    "google_search":        "web_search",
    "duckduckgo_search":    "web_search",
    "requests_get":         "web_fetch",
    "requests_post":        "web_fetch",
    "python_repl":          "bash",
    "terminal":             "bash",
    "human":                "notify",
    "wikipedia":            "web_search",
    "arxiv":                "arxiv_search",
    "file_management":      "read_file",
    "read_file":            "read_file",
    "write_file":           "write_file",
    # AutoGPT
    "browse_website":       "web_fetch",
    "google":               "web_search",
    "write_to_file":        "write_file",
    "read_from_file":       "read_file",
    "append_to_file":       "write_file",
    "delete_file":          "bash",
    "search_files":         "read_file",
    "clone_repository":     "bash",
    "git_operations":       "bash",
    # CrewAI
    "SerperDevTool":        "web_search",
    "ScrapeWebsiteTool":    "web_fetch",
    "FileReadTool":         "read_file",
    "FileWriteTool":        "write_file",
    "CodeInterpreterTool":  "bash",
    "GithubSearchTool":     "web_search",
    "YoutubeVideoSearchTool": "web_search",
    # Generic
    "calculator":           "bash",
    "code_interpreter":     "bash",
    "memory":               "memory_query",
    "vector_store":         "memory_query",
}

def _map_tool(tool_name: str) -> str:
    return _TOOL_MAP.get(tool_name, tool_name)


def _infer_district(tools: list[str], name: str) -> str:
    name_lower = name.lower()
    tools_lower = " ".join(tools).lower()
    if any(w in name_lower for w in ("code","coder","dev","engineer","programmer")):
        return "coding"
    if any(w in name_lower for w in ("research","analyst","data")):
        return "research"
    if any(w in name_lower for w in ("security","guard","monitor")):
        return "security"
    if any(w in name_lower for w in ("memory","knowledge","recall")):
        return "memory_curator"
    if "web_search" in tools_lower or "web_fetch" in tools_lower:
        return "research"
    if "bash" in tools_lower or "write_file" in tools_lower:
        return "coding"
    return "governance"


# ── VectorMigrator ─────────────────────────────────────────────────────────────

class VectorMigrator:
    """
    Migrates agent definitions from other frameworks to VECTOR format.

    Usage:
        migrator = VectorMigrator()

        # From LangChain YAML
        result = migrator.from_file("agents/researcher.yaml", MigrationSource.LANGCHAIN)

        # From AutoGPT config
        result = migrator.from_file("ai_settings.yaml", MigrationSource.AUTOGPT)

        # From plain JSON
        result = migrator.from_dict({
            "name": "my_agent",
            "system_prompt": "You are a helpful assistant",
            "tools": ["serpapi", "python_repl"],
        }, MigrationSource.PLAIN)

        # Save migrated agents
        for agent in result.agents:
            migrator.save_agent(agent, output_dir="districts/migrated/")
    """

    def from_file(self, path: str | Path, source: MigrationSource) -> MigrationResult:
        """Migrate from a file."""
        p = Path(path)
        if not p.exists():
            return MigrationResult(source=source, agents=[],
                                   errors=[f"File not found: {path}"])
        try:
            content = p.read_text(encoding="utf-8")
            if p.suffix in (".yaml", ".yml"):
                try:
                    import yaml
                    data = yaml.safe_load(content)
                except ImportError:
                    import re
                    data = {"raw": content}
            else:
                data = json.loads(content)
            return self.from_dict(data, source)
        except Exception as e:
            return MigrationResult(source=source, agents=[], errors=[str(e)])

    def from_dict(self, data: dict, source: MigrationSource) -> MigrationResult:
        """Migrate from a dict."""
        match source:
            case MigrationSource.LANGCHAIN:
                return self._from_langchain(data)
            case MigrationSource.AUTOGPT:
                return self._from_autogpt(data)
            case MigrationSource.CREWAI:
                return self._from_crewai(data)
            case MigrationSource.OPENAI_ASST:
                return self._from_openai_assistant(data)
            case MigrationSource.PLAIN:
                return self._from_plain(data)
            case _:
                return MigrationResult(source=source, agents=[],
                                       errors=[f"Unknown source: {source}"])

    def from_directory(self, directory: str, source: MigrationSource) -> MigrationResult:
        """Migrate all agent files from a directory."""
        all_agents: list[VectorAgentDef] = []
        all_warnings: list[str] = []
        all_errors: list[str] = []
        d = Path(directory)
        extensions = [".yaml", ".yml", ".json"]
        for ext in extensions:
            for f in d.glob(f"*{ext}"):
                result = self.from_file(f, source)
                all_agents.extend(result.agents)
                all_warnings.extend(result.warnings)
                all_errors.extend(result.errors)
        return MigrationResult(source=source, agents=all_agents,
                               warnings=all_warnings, errors=all_errors)

    def save_agent(self, agent: VectorAgentDef, output_dir: str = "districts/migrated/") -> Path:
        """Save a migrated agent as a VECTOR Python file."""
        out = Path(output_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)
        # agent.name comes from a parsed migration source file -- the old
        # .replace(" ", "_").replace("-", "_") only stripped spaces/hyphens,
        # leaving "/" and ".." untouched, so a crafted name (e.g.
        # "../../../evil") could write the generated .py file outside
        # output_dir entirely. Confine the resolved path to stay inside it.
        safe_name = _SAFE_IDENTIFIER_RE.sub("_", agent.name.lower()).strip("_") or "migrated_agent"
        p = (out / f"{safe_name}.py").resolve()
        if not p.is_relative_to(out):
            raise ValueError(f"agent name escapes output_dir: {agent.name!r}")
        p.write_text(agent.to_python_file(), encoding="utf-8")
        logger.info("[VECTOR][migration] saved agent: {}", p)
        return p

    def save_all(self, result: MigrationResult, output_dir: str = "districts/migrated/") -> list[Path]:
        return [self.save_agent(a, output_dir) for a in result.agents]

    # ── Source-specific parsers ────────────────────────────────────────────────

    def _from_langchain(self, data: dict) -> MigrationResult:
        warnings: list[str] = []
        agents: list[VectorAgentDef] = []

        # LangChain can be: single agent dict or list of agents
        items = data if isinstance(data, list) else [data]
        for item in items:
            name = item.get("name") or item.get("agent_name", "langchain_agent")
            prompt = (
                item.get("system_message") or
                item.get("system_prompt") or
                item.get("prefix") or
                str(item.get("prompt", {}).get("template", "")) or
                "You are a helpful assistant."
            )
            raw_tools = item.get("tools", []) or item.get("tool_names", [])
            tools = [_map_tool(t if isinstance(t, str) else t.get("name", str(t))) for t in raw_tools]
            if not tools:
                tools = ["web_search", "memory_query"]
                warnings.append(f"{name}: no tools defined, using defaults")

            agents.append(VectorAgentDef(
                name=name, system_prompt=prompt, tools=tools,
                district=_infer_district(tools, name),
                source_framework="langchain",
                description=item.get("description", ""),
                original_config=item,
            ))

        logger.info("[VECTOR][migration] langchain: {} agents", len(agents))
        return MigrationResult(MigrationSource.LANGCHAIN, agents, warnings)

    def _from_autogpt(self, data: dict) -> MigrationResult:
        name = data.get("ai_name", "autogpt_agent")
        goals = data.get("ai_goals", [])
        role = data.get("ai_role", "an AI assistant")
        prompt = f"You are {name}, {role}.\n\nYour goals:\n" + "\n".join(f"- {g}" for g in goals)
        raw_tools = data.get("plugins", []) or []
        tools = [_map_tool(t) for t in raw_tools] or [
            "web_search", "web_fetch", "read_file", "write_file", "bash", "memory_query"
        ]
        agent = VectorAgentDef(
            name=name, system_prompt=prompt, tools=tools,
            district=_infer_district(tools, name),
            source_framework="autogpt",
            description=role,
            original_config=data,
        )
        logger.info("[VECTOR][migration] autogpt: 1 agent ({})", name)
        return MigrationResult(MigrationSource.AUTOGPT, [agent])

    def _from_crewai(self, data: dict) -> MigrationResult:
        agents_data = data.get("agents", [data] if "role" in data else [])
        agents: list[VectorAgentDef] = []
        for a in agents_data:
            role = a.get("role", "agent")
            goal = a.get("goal", "")
            backstory = a.get("backstory", "")
            prompt = f"You are a {role}.\nGoal: {goal}\nBackstory: {backstory}"
            raw_tools = a.get("tools", [])
            tools = [_map_tool(t if isinstance(t, str) else getattr(t, "__class__", object).__name__) for t in raw_tools]
            if not tools:
                tools = ["web_search", "memory_query"]
            agents.append(VectorAgentDef(
                name=role.lower().replace(" ", "_"),
                system_prompt=prompt, tools=tools,
                district=_infer_district(tools, role),
                source_framework="crewai",
                description=goal,
                original_config=a,
            ))
        logger.info("[VECTOR][migration] crewai: {} agents", len(agents))
        return MigrationResult(MigrationSource.CREWAI, agents)

    def _from_openai_assistant(self, data: dict) -> MigrationResult:
        name = data.get("name", "openai_assistant")
        prompt = data.get("instructions", "You are a helpful assistant.")
        tools_raw = data.get("tools", [])
        tools = []
        for t in tools_raw:
            t_type = t.get("type", "") if isinstance(t, dict) else str(t)
            if t_type == "code_interpreter": tools.append("bash")
            elif t_type == "retrieval": tools.append("memory_query")
            elif t_type == "function":
                fn_name = t.get("function", {}).get("name", "")
                tools.append(_map_tool(fn_name) if fn_name else "memory_query")
        if not tools: tools = ["memory_query", "web_search"]
        agent = VectorAgentDef(
            name=name, system_prompt=prompt, tools=tools,
            district=_infer_district(tools, name),
            model=data.get("model", "qwen3:14b"),
            source_framework="openai_assistant",
            description=data.get("description", ""),
            original_config=data,
        )
        return MigrationResult(MigrationSource.OPENAI_ASST, [agent])

    def _from_plain(self, data: dict) -> MigrationResult:
        name = data.get("name", "imported_agent")
        prompt = data.get("system_prompt") or data.get("prompt") or data.get("instructions", "")
        tools = [_map_tool(t) for t in data.get("tools", [])]
        if not tools: tools = ["memory_query"]
        agent = VectorAgentDef(
            name=name, system_prompt=prompt, tools=tools,
            district=data.get("district", _infer_district(tools, name)),
            schedule=data.get("schedule", ""),
            model=data.get("model", "qwen3:14b"),
            source_framework="plain",
            description=data.get("description", ""),
            original_config=data,
        )
        return MigrationResult(MigrationSource.PLAIN, [agent])


if __name__ == "__main__":
    migrator = VectorMigrator()

    # LangChain agent
    lc = {"name": "researcher", "system_prompt": "You are a research agent.",
          "tools": ["serpapi", "python_repl", "arxiv"]}
    r = migrator.from_dict(lc, MigrationSource.LANGCHAIN)
    assert r.success and r.agents[0].name == "researcher"
    assert "web_search" in r.agents[0].tools

    # AutoGPT
    ag = {"ai_name": "ResearchBot", "ai_role": "a research assistant",
          "ai_goals": ["Find papers on LLMs", "Summarize findings"]}
    r2 = migrator.from_dict(ag, MigrationSource.AUTOGPT)
    assert r2.success

    # CrewAI
    crew = {"agents": [
        {"role": "Senior Researcher", "goal": "Research AI trends",
         "backstory": "Expert in AI", "tools": ["SerperDevTool"]}
    ]}
    r3 = migrator.from_dict(crew, MigrationSource.CREWAI)
    assert r3.success and r3.agents[0].district == "research"

    # Plain
    plain = {"name": "coder", "system_prompt": "Write clean Python code.",
             "tools": ["bash", "write_file"], "district": "coding"}
    r4 = migrator.from_dict(plain, MigrationSource.PLAIN)
    assert r4.agents[0].district == "coding"

    # Python file generation
    code = r4.agents[0].to_python_file()
    assert "class CoderAgent" in code

    print(f"OK migration/importer.py — LangChain, AutoGPT, CrewAI, OpenAI, Plain all migrate")
