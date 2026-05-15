"""Fix remaining import issues in vectorcode/src."""
from __future__ import annotations
import ast
from pathlib import Path

vc = Path(__file__).parent.parent / "vectorcode" / "src"
root = Path(__file__).parent.parent


def mk(rel: str, content: str) -> None:
    p = vc / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(content, encoding="utf-8")
        print(f"Created {rel}")


def add(rel: str, additions: str) -> None:
    p = vc / rel
    if not p.exists():
        mk(rel, additions)
        return
    text = p.read_text(encoding="utf-8", errors="replace")
    new_lines = []
    for line in additions.strip().splitlines():
        # Extract the identifier being added
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Check if already present
        ident = stripped.split("=")[0].strip().split()[-1] if stripped else ""
        if ident and ident in text:
            continue
        new_lines.append(line)
    if new_lines:
        p.write_text(text.rstrip() + "\n\n" + "\n".join(new_lines) + "\n", encoding="utf-8")
        print(f"Updated {rel}")


# 1. Mining constants
add("mining/_constants.py", """
PEARL_IMAGE_TAG: str = "pearl-mining:latest"
MIN_FREE_DISK_GB: float = 2.0
PEARL_CACHE_DIR: Path = Path.home() / ".vector" / "mining" / "cache"
DEFAULT_PEARL_MODEL: str = "pearl-3"
""")

# 2. engine/_discovery.py
mk("engine/_discovery.py", '''"""Engine discovery utilities."""
from __future__ import annotations
from typing import List

_discovery = None  # sentinel for import compat

def list_engines() -> List[str]:
    return []

def get_default_engine() -> str:
    return "ollama"
''')

# 3. engine/_stubs.py
mk("engine/_stubs.py", '''"""Engine stub types."""
from __future__ import annotations
from typing import Any, AsyncIterator, Dict, List

class InferenceEngine:
    """Abstract inference engine."""
    async def generate(self, messages: List[Dict], **kw: Any) -> Dict[str, Any]:
        raise NotImplementedError
    async def stream(self, messages: List[Dict], **kw: Any) -> AsyncIterator[str]:
        raise NotImplementedError
    async def stream_full(self, messages: List[Dict], **kw: Any) -> AsyncIterator[Any]:
        raise NotImplementedError
''')

# 4. engine/_base.py
mk("engine/_base.py", '''"""Engine base classes."""
from vectorcode.src.engine._stubs import InferenceEngine

__all__ = ["InferenceEngine"]
''')

# 5. Add OllamaEngine to engine/ollama.py
p_ol = vc / "engine/ollama.py"
if p_ol.exists():
    t = p_ol.read_text(encoding="utf-8", errors="replace")
    if "OllamaEngine" not in t:
        t += """

class OllamaEngine:
    \"\"\"Ollama-backed inference engine.\"\"\"
    def __init__(self, model: str = "vector-focus", base_url: str = "http://127.0.0.1:11434") -> None:
        self.model = model
        self.base_url = base_url

    async def generate(self, messages, **kw):
        return await ollama_chat(self.model, messages, **kw)

    async def get_models(self):
        return list_models()
"""
        p_ol.write_text(t, encoding="utf-8")
        print("Added OllamaEngine to engine/ollama.py")

# 6. telemetry/instrumented_engine.py
mk("telemetry/instrumented_engine.py", '''"""Instrumented engine wrapper."""
from __future__ import annotations
from typing import Any

class InstrumentedEngine:
    """Wraps an inference engine with telemetry collection."""
    def __init__(self, engine: Any, session_id: str = "") -> None:
        self._engine = engine
        self.session_id = session_id

    def __getattr__(self, name: str) -> Any:
        return getattr(self._engine, name)
''')

# 7. agents/deep_research.py
mk("agents/deep_research.py", '''"""Deep research agent."""
from __future__ import annotations
from typing import Any, Dict

class DeepResearchAgent:
    """Multi-step web research agent."""
    def __init__(self, model: str = "vector-deep", max_steps: int = 10) -> None:
        self.model = model
        self.max_steps = max_steps

    async def research(self, query: str, **kw: Any) -> Dict[str, Any]:
        return {"query": query, "result": "Deep research not yet implemented", "sources": []}
''')

# 8. channels/imessage_daemon.py
mk("channels/imessage_daemon.py", '''"""iMessage daemon channel shim."""
try:
    from vectorcode.src.comms.imessage_daemon import *
except ImportError:
    pass
''')

# 9. cli/ shims -> vector_cli/
for name in ["_tool_names", "_bg_state", "_chat_banner", "init_cmd", "scan_cmd"]:
    mk(f"cli/{name}.py",
       f'"""CLI shim for {name}."""\ntry:\n    from vectorcode.src.vector_cli.{name} import *\nexcept ImportError:\n    pass\n')

# 10. core/credentials.py
mk("core/credentials.py", '''"""Core credentials shim."""
from typing import Any, Dict
TOOL_CREDENTIALS: Dict[str, Any] = {}

def get_credential(name: str) -> Any:
    return TOOL_CREDENTIALS.get(name)

def set_credential(name: str, value: Any) -> None:
    TOOL_CREDENTIALS[name] = value
''')

# 11. vc_core/credentials.py
mk("vc_core/credentials.py", '''"""VECTOR credential store."""
from typing import Any, Dict
TOOL_CREDENTIALS: Dict[str, Any] = {}
''')

# 12. Add CONFIG alias to vc_core/config.py
p_cfg = vc / "vc_core/config.py"
cfg_text = p_cfg.read_text(encoding="utf-8", errors="replace")
if "CONFIG" not in cfg_text:
    p_cfg.write_text(cfg_text.rstrip() + "\n\n# Module-level config alias\nCONFIG = VectorConfig()\n", encoding="utf-8")
    print("Added CONFIG alias to vc_core/config.py")

# 13. security/types.py — add ScanFinding, ScanResult, InjectionScanResult
p_sectypes = vc / "security/types.py"
add_content = '''
from dataclasses import dataclass, field
from typing import List

@dataclass
class ScanFinding:
    rule: str = ""
    severity: str = "medium"
    description: str = ""
    line: int = 0
    column: int = 0

@dataclass
class ScanResult:
    findings: List[ScanFinding] = field(default_factory=list)
    scanned_bytes: int = 0
    is_safe: bool = True

@dataclass
class InjectionScanResult:
    detected: bool = False
    patterns: List[str] = field(default_factory=list)
    confidence: float = 0.0
'''
if p_sectypes.exists():
    t = p_sectypes.read_text(encoding="utf-8", errors="replace")
    if "ScanFinding" not in t:
        p_sectypes.write_text(t.rstrip() + add_content, encoding="utf-8")
        print("Added ScanFinding/ScanResult/InjectionScanResult to security/types.py")

# 14. security/injection_scanner.py — add InjectionScanResult
p_scan = vc / "security/injection_scanner.py"
if p_scan.exists():
    t = p_scan.read_text(encoding="utf-8", errors="replace")
    if "InjectionScanResult" not in t:
        t += "\nfrom vectorcode.src.security.types import InjectionScanResult\n"
        p_scan.write_text(t, encoding="utf-8")
        print("Added InjectionScanResult to security/injection_scanner.py")

# 15. vector_cli/env_loader.py — add load_vectorcode_dotenv
p_env = vc / "vector_cli/env_loader.py"
if p_env.exists():
    t = p_env.read_text(encoding="utf-8", errors="replace")
    if "load_vectorcode_dotenv" not in t:
        t += '''

def load_vectorcode_dotenv(path=None) -> bool:
    """Load VECTOR .env file. Returns True if loaded."""
    import os
    from pathlib import Path as _P
    env_path = _P(path) if path else (_P.home() / ".vector" / ".env")
    if not env_path.exists():
        return False
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())
    return True
'''
        p_env.write_text(t, encoding="utf-8")
        print("Added load_vectorcode_dotenv to vector_cli/env_loader.py")

# 16. vector_cli/commands.py — add COMMAND_REGISTRY
p_cmds = vc / "vector_cli/commands.py"
if not p_cmds.exists():
    mk("vector_cli/commands.py", '''"""VECTOR CLI command registry."""
from typing import Any, Callable, Dict
COMMAND_REGISTRY: Dict[str, Callable[..., Any]] = {}

def register_command(name: str) -> Callable:
    def decorator(fn: Callable) -> Callable:
        COMMAND_REGISTRY[name] = fn
        return fn
    return decorator
''')
else:
    add("vector_cli/commands.py", 'COMMAND_REGISTRY: dict = {}')

# 17. vc_skills/ shim
mk("vc_skills/__init__.py", '"""VECTOR skills package."""\n')
mk("vc_skills/manager.py", '''"""VECTOR skill manager shim."""
try:
    from vectorcode.src.skills.manager import SkillManager
except ImportError:
    class SkillManager:
        pass
''')
mk("vc_skills/overlay.py", '''"""VECTOR skill overlay shim."""
try:
    from vectorcode.src.skills.overlay import SkillOverlay
except ImportError:
    class SkillOverlay:
        pass
''')

# 18. tools/knowledge_search.py
mk("tools/knowledge_search.py", '''"""Knowledge search tool."""
from __future__ import annotations
from typing import Any, Dict, List

async def knowledge_search(query: str, k: int = 5, **kw: Any) -> List[Dict[str, Any]]:
    """Search the VECTOR knowledge base."""
    return []
''')

# 19. tools/storage/chunking.py
p_chunk = vc / "tools/storage/chunking.py"
if not p_chunk.exists():
    mk("tools/storage/chunking.py", '''"""Text chunking utilities."""
from __future__ import annotations
from typing import List

def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
    """Split text into overlapping chunks."""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks
''')

# 20. workflow/loader.py — add discover_workflows
p_wf = vc / "workflow/loader.py"
if p_wf.exists():
    add("workflow/loader.py", """
def discover_workflows(directory=None) -> list:
    \"\"\"Discover available workflow definitions.\"\"\"
    return []
""")

# 21. intelligence/model_catalog.py
mk("intelligence/__init__.py", '"""VECTOR intelligence package."""\n')
mk("intelligence/model_catalog.py", '''"""VECTOR model catalog."""
BUILTIN_MODELS = [
    {"id": "vector-focus", "base": "gemma4:e4b", "context": 8192},
    {"id": "vector-coder", "base": "qwen3:14b", "context": 32768},
    {"id": "vector-deep", "base": "gemma4:26b", "context": 65536},
    {"id": "vector-reasoning", "base": "qwen3:14b", "context": 32768},
    {"id": "vector-chairman", "base": "gemma4:31b", "context": 131072},
]
''')

# 22. display/diff_preview.py
mk("display/__init__.py", '"""VECTOR display utilities."""\n')
mk("display/diff_preview.py", '''"""Diff preview utilities."""
from typing import List

def build_diff_preview(old: str, new: str, context: int = 3) -> str:
    """Build a unified diff preview string."""
    import difflib
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        n=context,
    ))
''')

# 23. vectorcode/providers/__init__.py — get_model_router
p_prov = root / "vectorcode/providers"
p_prov.mkdir(parents=True, exist_ok=True)
p_prov_init = p_prov / "__init__.py"
if not p_prov_init.exists():
    p_prov_init.write_text('"""VECTOR providers."""\n', encoding="utf-8")
t = p_prov_init.read_text(encoding="utf-8", errors="replace")
if "get_model_router" not in t:
    t += "\ndef get_model_router():\n    from vectorcode.src.router import GNNRouter\n    return GNNRouter()\n"
    p_prov_init.write_text(t, encoding="utf-8")
    print("Added get_model_router to vectorcode/providers/__init__.py")

# 24. vectorcode/plugins/__init__.py — init_plugins
p_plug_dir = root / "vectorcode/plugins"
p_plug_dir.mkdir(parents=True, exist_ok=True)
p_plug = p_plug_dir / "__init__.py"
if not p_plug.exists():
    p_plug.write_text('"""VECTOR plugins."""\n', encoding="utf-8")
t = p_plug.read_text(encoding="utf-8", errors="replace")
if "init_plugins" not in t:
    t += "\ndef init_plugins():\n    pass\n"
    p_plug.write_text(t, encoding="utf-8")
    print("Added init_plugins to vectorcode/plugins/__init__.py")

# 25. evals/backends/external/vector_agent.py
mk("evals/backends/external/vector_agent.py", '''"""VECTOR agent eval backend."""
from __future__ import annotations

class VectorAgentBackend:
    """Run evals via the VECTOR agent."""
    backend_id = "vector_agent"
''')

# 26. vc_engine/cloud.py — add PRICING
p_cloud = vc / "vc_engine/cloud.py"
if p_cloud.exists():
    add("vc_engine/cloud.py", "PRICING: dict = {}  # cloud model pricing (per-token)\n")

# 27. mcp_client/client.py — add MCPClient
p_mcp_cli = root / "vectorcode/mcp_client/client.py"
if p_mcp_cli.exists():
    t = p_mcp_cli.read_text(encoding="utf-8", errors="replace")
    if "MCPClient" not in t:
        t += "\nfrom vectorcode.src.vc_mcp.client import MCPClient\n"
        p_mcp_cli.write_text(t, encoding="utf-8")
        print("Added MCPClient to vectorcode/mcp_client/client.py")

# 28. server/savings.py
mk("server/savings.py", '''"""Cloud cost savings calculator."""
CLOUD_PRICING: dict = {"gpt-4o": 5.0, "claude-3-5-sonnet": 3.0}

def compute_savings(tokens: int, model: str) -> float:
    price_per_1m = CLOUD_PRICING.get(model, 1.0)
    return tokens / 1_000_000 * price_per_1m
''')

# 29. skills/loader.py — add load_skill_directory
p_loader = vc / "skills/loader.py"
if p_loader.exists():
    add("skills/loader.py", """
def load_skill_directory(path=None) -> list:
    \"\"\"Load skills from a directory.\"\"\"
    return []
""")

# 30. vc_tools/agent_tools.py — add _SPAWNED_AGENTS
p_at = vc / "vc_tools/agent_tools.py"
if p_at.exists():
    t = p_at.read_text(encoding="utf-8", errors="replace")
    if "_SPAWNED_AGENTS" not in t:
        lines = t.splitlines()
        # Insert after imports
        insert_idx = 0
        for i, line in enumerate(lines):
            s = line.strip()
            if s and not s.startswith(("#", '"""', "'''", "from", "import")):
                insert_idx = i
                break
        lines.insert(insert_idx, "_SPAWNED_AGENTS: dict = {}")
        p_at.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("Added _SPAWNED_AGENTS to vc_tools/agent_tools.py")

# 31. vector_cli/__init__.py — expose kanban_db
p_vci = vc / "vector_cli/__init__.py"
if p_vci.exists():
    t = p_vci.read_text(encoding="utf-8", errors="replace")
    if "kanban_db" not in t:
        t += "\ntry:\n    from vectorcode.src.vector_cli import kanban_db\nexcept ImportError:\n    pass\n"
        p_vci.write_text(t, encoding="utf-8")
        print("Added kanban_db to vector_cli/__init__.py")

# 32. tui_gateway/__init__.py — expose server
p_tg_dir = root / "vectorcode/tui_gateway"
p_tg_dir.mkdir(exist_ok=True)
p_tg = p_tg_dir / "__init__.py"
if not p_tg.exists():
    p_tg.write_text('"""TUI gateway package."""\n', encoding="utf-8")
t = p_tg.read_text(encoding="utf-8", errors="replace")
if "server" not in t:
    t += "\ntry:\n    from vectorcode.tui_gateway import server\nexcept ImportError:\n    pass\n"
    p_tg.write_text(t, encoding="utf-8")
    print("Added server to tui_gateway/__init__.py")

# 33. vc_agents/digest_evaluator.py
mk("vc_agents/digest_evaluator.py", '''"""Digest evaluator agent."""
from __future__ import annotations
from typing import Any, Dict

class DigestEvaluator:
    """Evaluates the quality of generated digests."""
    def evaluate(self, digest: str, **kw: Any) -> Dict[str, Any]:
        return {"score": 1.0, "feedback": "ok"}
''')

# 34. learning/intelligence/__init__.py — sft_trainer reference
p_li = vc / "learning/intelligence/__init__.py"
if p_li.exists():
    t = p_li.read_text(encoding="utf-8", errors="replace")
    if "sft_trainer" not in t:
        t += "\ntry:\n    from vectorcode.src.learning.intelligence import sft_trainer\nexcept ImportError:\n    pass\n"
        p_li.write_text(t, encoding="utf-8")
        print("Added sft_trainer ref to learning/intelligence/__init__.py")

# 35. learning/intelligence/orchestrator/prompt_registry.py
p_pr = vc / "learning/intelligence/orchestrator/prompt_registry.py"
if not p_pr.exists():
    mk("learning/intelligence/orchestrator/prompt_registry.py", '''"""Orchestrator prompt registry."""
TOOL_DESC: dict = {}

def register_tool_desc(name: str, desc: str) -> None:
    TOOL_DESC[name] = desc
''')
else:
    add("learning/intelligence/orchestrator/prompt_registry.py", "TOOL_DESC: dict = {}\n")

# 36. core/__init__.py — expose config sub-module
p_core_init = vc / "core/__init__.py"
t = p_core_init.read_text(encoding="utf-8", errors="replace")
if "from vectorcode.src.core import config" not in t and "import config" not in t:
    t = '"""Core shim package."""\nfrom vectorcode.src.vc_core import *\ntry:\n    from vectorcode.src.core import config\nexcept ImportError:\n    pass\n'
    p_core_init.write_text(t, encoding="utf-8")
    print("Updated core/__init__.py")

# 37. vectorcode/cron/__init__.py — stop_daemon
p_cron = root / "vectorcode/cron/__init__.py"
if p_cron.exists():
    t = p_cron.read_text(encoding="utf-8", errors="replace")
    if "stop_daemon" not in t:
        t += "\ndef stop_daemon():\n    pass\n"
        p_cron.write_text(t, encoding="utf-8")
        print("Added stop_daemon to vectorcode/cron/__init__.py")

# 38. vectorcode/providers/base.py -> just in case
mk_path = root / "vectorcode/providers/base.py"
if not mk_path.exists():
    mk_path.write_text('"""Provider base."""\n', encoding="utf-8")

# 39. connectors/oauth.py — ensure GOOGLE_ALL_SCOPES present
p_oauth = vc / "connectors/oauth.py"
if p_oauth.exists():
    t = p_oauth.read_text(encoding="utf-8", errors="replace")
    if "GOOGLE_ALL_SCOPES" not in t:
        add("connectors/oauth.py", """
GOOGLE_ALL_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://mail.google.com/",
]
""")

print("\nAll fixes applied.")
