"""
Full honest audit of both absorbed repos.
Checks: imports, stubs, wiring, missing deps, real functionality.
"""
import subprocess
import inspect
from pathlib import Path


results = []


def _audit_exit_code(failures: int) -> int:
    """Return a failing process status when the audit found any failure."""
    return 1 if failures else 0

def check(label: str, ok: bool, detail: str = ""):
    status = "PASS" if ok else "FAIL"
    results.append((status, label, detail))
    print(f"  {status:4}  {label}" + (f" — {detail}" if detail else ""))


# ══════════════════════════════════════════════════════════════════════════════
# 1. STUBS — things that are stubs not real implementations
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== STUBS (not real implementations) ===")

# Check TTS stub
try:
    from core.coding_assistant.core.tts import MistralTTSClient
    src = inspect.getsource(MistralTTSClient.speak)
    is_explicit_fallback = "audio_data=b\"\"" in src and "not available" in src
    check(
        "TTS MistralTTSClient explicit fallback",
        is_explicit_fallback,
        "legacy adapter unavailable; use core/voice/tts.py" if is_explicit_fallback else "fallback contract missing",
    )
except Exception as e:
    check("TTS MistralTTSClient fallback contract", False, str(e)[:60])

# Check Transcribe stub
try:
    from core.coding_assistant.core.transcribe import MistralTranscribeClient
    src = inspect.getsource(MistralTranscribeClient.transcribe)
    is_explicit_fallback = "NotImplementedError" in src and "core/voice/stt.py" in src
    check(
        "Transcribe MistralTranscribeClient explicit fallback",
        is_explicit_fallback,
        "legacy adapter unavailable; use core/voice/stt.py" if is_explicit_fallback else "fallback contract missing",
    )
except Exception as e:
    check("Transcribe MistralTranscribeClient fallback contract", False, str(e)[:60])

# Check ACP availability
try:
    from core.coding_assistant.acp.acp_agent_loop import _ACP_AVAILABLE
    acp_source = Path("core/coding_assistant/acp/acp_agent_loop.py").read_text(encoding="utf-8")
    guarded = "except (ImportError, AttributeError)" in acp_source and "_ACP_AVAILABLE = False" in acp_source
    check(
        "ACP protocol optional dependency guard",
        guarded,
        "unavailable in this environment; guarded for explicit NEEDS_CONFIG state"
        if guarded and not _ACP_AVAILABLE else "available",
    )
except Exception as e:
    check("ACP protocol dependency guard", False, str(e)[:60])

# Check telemetry stubs
try:
    from core.coding_assistant.core.agent_loop import AgentLoop
    import inspect
    # Check TelemetryClient is the noop
    from core.coding_assistant.core import agent_loop as al
    tc = getattr(al, 'TelemetryClient', None)
    is_noop = tc is not None and hasattr(tc, '__getattr__') and 'noop' in str(tc).lower()
    check("Telemetry is intentionally no-op", is_noop,
          "NoopTelemetry — VECTOR never sends telemetry (privacy rule)")
except Exception as e:
    check("Telemetry no-op", False, str(e)[:60])

# ══════════════════════════════════════════════════════════════════════════════
# 2. REAL FUNCTIONALITY — what actually works
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== REAL FUNCTIONALITY (no stubs) ===")

# search_replace
try:
    from core.coding_assistant.core.tools.builtins.search_replace import (
        SearchReplaceBlock, SEARCH_REPLACE_BLOCK_RE
    )
    test_input = "<<<<<<< SEARCH\nold text\n=======\nnew text\n>>>>>>> REPLACE"
    matches = SEARCH_REPLACE_BLOCK_RE.findall(test_input)
    check("search_replace SEARCH_REPLACE_BLOCK_RE works", len(matches) >= 1,
          f"found {len(matches)} match(es)")
except Exception as e:
    check("search_replace", False, str(e)[:60])

# hooks system
try:
    from core.coding_assistant.core.hooks.manager import HooksManager
    from core.coding_assistant.core.hooks.models import HookType
    check("HooksManager importable", True)
except Exception as e:
    check("HooksManager", False, str(e)[:60])

# skills parser
try:
    from core.coding_assistant.core.skills.parser import parse_skill_markdown
    from core.coding_assistant.core.skills.models import SkillInfo
    check("skills parser importable", True)
except Exception as e:
    check("skills parser", False, str(e)[:60])

# session management
try:
    from core.coding_assistant.core.session.session_loader import SessionLoader
    check("SessionLoader importable", True)
except Exception as e:
    check("SessionLoader", False, str(e)[:60])

# rewind manager
try:
    from core.coding_assistant.core.rewind.manager import RewindManager
    check("RewindManager importable", True)
except Exception as e:
    check("RewindManager", False, str(e)[:60])

# middleware
try:
    from core.coding_assistant.core.middleware import (
        MiddlewarePipeline, AutoCompactMiddleware
    )
    check("MiddlewarePipeline importable", True)
except Exception as e:
    check("MiddlewarePipeline", False, str(e)[:60])

# LLM backend generic (Ollama-compatible)
try:
    from core.coding_assistant.core.llm.backend.generic import GenericBackend
    check("GenericBackend (Ollama-compatible) importable", True)
except Exception as e:
    check("GenericBackend", False, str(e)[:60])

# file indexer
try:
    from core.coding_assistant.core.autocompletion.file_indexer.indexer import FileIndexer
    check("FileIndexer importable", True)
except Exception as e:
    check("FileIndexer", False, str(e)[:60])

# agent loop
try:
    from core.coding_assistant.core.agent_loop import AgentLoop
    check("AgentLoop importable", True)
except Exception as e:
    check("AgentLoop", False, str(e)[:60])

# ══════════════════════════════════════════════════════════════════════════════
# 3. VECTOR WIRING — is coding_assistant hooked into VECTOR properly?
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== VECTOR WIRING (coding_assistant) ===")

# Governor routing for coding_assistant tools
gov = Path("core/city/governor.py").read_text(encoding="utf-8")
check("Governor routes search_replace", "search_replace" in gov,
      "NOT in governor — coding_assistant tools not routed")
check("Governor routes bash tool", "bash_execute" in gov or "bash_tool" in gov,
      "NOT in governor — bash_execute not routed")

# coding district uses coding_assistant
coding_hub = Path("districts/coding")
hub_files = list(coding_hub.rglob("*.py"))
ca_refs = sum(1 for f in hub_files
              if "coding_assistant" in f.read_text(encoding="utf-8", errors="replace"))
check("coding/ district uses coding_assistant", ca_refs > 0,
      f"{ca_refs} files reference it" if ca_refs else "NOT wired into coding district")

# ══════════════════════════════════════════════════════════════════════════════
# 4. RESEARCH ENGINE WIRING
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== VECTOR WIRING (research_engine) ===")

# research_api.py exists and imports from research_engine
rap = Path("districts/research/research_api.py")
check("research_api.py exists", rap.exists())
if rap.exists():
    content = rap.read_text(encoding="utf-8")
    check("research_api imports from core.research_engine", "core.research_engine" in content)

# deep_researcher.py exists
dr = Path("districts/research/deep_researcher.py")
check("deep_researcher.py exists", dr.exists())

# governor routes research tasks
check("Governor routes deep_research", "deep_research" in gov)
check("Governor routes research_report", "research_report" in gov)

# MCP tools wired: inspect the actual registration function rather than the
# server's import line. The tools are defined in core/mcp_tools/research.py and
# registered by add_research_tools(mcp).
try:
    from core.mcp_tools.research import add_research_tools

    research_source = inspect.getsource(add_research_tools)
    check("MCP: research_quick tool", "def research_quick" in research_source)
    check("MCP: research_report tool", "def research_report" in research_source)
    check("MCP: research_papers tool", "def research_papers" in research_source)
except Exception as e:
    check("MCP: research registration", False, str(e)[:60])

# ══════════════════════════════════════════════════════════════════════════════
# 5. MISSING DEPENDENCIES
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== MISSING DEPENDENCIES ===")

deps_to_check = [
    ("sqlalchemy", "research_engine settings DB"),
    ("alembic", "research_engine migrations"),
    ("bs4", "HTML parsing (beautifulsoup4)"),
    ("langchain_ollama", "Ollama LangChain"),
    ("langchain_community", "DuckDuckGo search"),
    ("arxiv", "ArXiv search engine"),
    ("wikipedia", "Wikipedia search engine"),
    ("trafilatura", "web content extraction"),
    ("platformdirs", "platform paths"),
    ("tomli_w", "TOML writer"),
    ("tree_sitter", "bash syntax analysis (optional)"),
    ("tree_sitter_bash", "bash grammar (optional)"),
]

import importlib.util
for pkg, purpose in deps_to_check:
    pkg_import = pkg.replace("-", "_")
    found = importlib.util.find_spec(pkg_import) is not None
    check(f"dep: {pkg}", found,
          f"MISSING — needed for {purpose}" if not found else "installed")

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*60)
passes = sum(1 for s,_,_ in results if s == "PASS")
fails  = sum(1 for s,_,_ in results if s == "FAIL")
print(f"PASS: {passes}  FAIL: {fails}  TOTAL: {len(results)}")

if fails:
    print(f"\nFailing checks ({fails}):")
    for s, label, detail in results:
        if s == "FAIL":
            print(f"  [{label}]" + (f" — {detail}" if detail else ""))

raise SystemExit(_audit_exit_code(fails))
