"""
CodebaseOnboardingEngineer — Helps navigate unfamiliar repos.

Reads source code, traces execution paths, maps architecture, produces
onboarding documents. Only states facts grounded in code.
"""

import asyncio
import ast
import datetime
import re
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat

# Extensions considered as "source" files (not docs/assets)
_SOURCE_EXTS = {".py", ".ts", ".js", ".go", ".rs", ".java", ".c", ".cpp", ".h"}

# Well-known entry point filenames to detect automatically
_ENTRY_POINTS = [
    "main.py", "run.py", "app.py", "server.py", "cli.py",
    "run_vector.py", "__main__.py", "index.py",
    "main.ts", "index.ts", "index.js", "main.js",
]

# Max files to trace in an import chain before stopping (avoid infinite loops)
_MAX_TRACE_DEPTH = 20

def _find_readme(repo_path: Path) -> str:
    """Return first 500 chars of README if it exists, else empty string."""
    for name in ("README.md", "README.rst", "README.txt", "README"):
        candidate = repo_path / name
        if candidate.exists():
            try:
                return candidate.read_text(encoding="utf-8", errors="replace")[:500]
            except Exception as e:
                logger.debug("[VECTOR][codebase_onboarding_engineer] failed to read {}: {}", candidate, e)
    return ""

def _count_py_files(repo_path: Path) -> int:
    try:
        return sum(1 for _ in repo_path.rglob("*.py") if ".venv" not in str(_) and "__pycache__" not in str(_))
    except Exception:
        return 0

class CodebaseOnboardingEngineer(AgentBase):
    """Maps unfamiliar repos — architecture scan, import tracing, onboarding docs."""

    def __init__(self):
        super().__init__(
            agent_id="onboarding_001",
            name="CodebaseOnboardingEngineer",
            district="coding",
        )
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = ["scan", "trace", "onboard"]
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        logger.info("[VECTOR][codebase_onboarding_engineer] initialized")

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def quick_scan(self, repo_path: str) -> dict:
        """Scan top-level structure: dirs, key files, entry points, py count, README.

        Returns:
            {
                root: str,
                top_level_dirs: list[str],
                top_level_files: list[str],
                entry_points: list[str],
                source_file_count: int,
                readme_snippet: str,
                key_configs: list[str],
                timestamp: str,
            }
        Never raises.
        """
        try:
            root = Path(repo_path).resolve()
            if not root.exists():
                logger.error(f"[VECTOR][onboarding] repo_path not found: {repo_path}")
                return {"root": str(root), "error": "path not found"}

            # Top-level dirs and files (skip hidden + __pycache__)
            top_dirs = sorted([
                p.name for p in root.iterdir()
                if p.is_dir() and not p.name.startswith(".") and p.name != "__pycache__"
            ])
            top_files = sorted([
                p.name for p in root.iterdir()
                if p.is_file() and not p.name.startswith(".")
            ])

            # Detect entry points
            entry_points = [f for f in _ENTRY_POINTS if (root / f).exists()]

            # Key config files
            config_names = {
                "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
                "Makefile", "Dockerfile", "docker-compose.yml", "wrangler.toml",
                ".env.example", "fly.toml", "package.json", "tsconfig.json",
            }
            key_configs = sorted([f for f in top_files if f in config_names])

            py_count = _count_py_files(root)
            readme = _find_readme(root)

            result = {
                "root": str(root),
                "top_level_dirs": top_dirs,
                "top_level_files": top_files[:30],  # cap at 30
                "entry_points": entry_points,
                "source_file_count": py_count,
                "readme_snippet": readme,
                "key_configs": key_configs,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }

            self._get_memory().store(
                event_type="quick_scan",
                content=f"root={str(root)} dirs={len(top_dirs)} py_files={py_count}",
                tags=["onboarding", "quick_scan"],
                source="codebase_onboarding_engineer",
            )

            self.award_points(20, "quick_scan_done")
            logger.info(
                f"[VECTOR][onboarding] quick_scan: root={root.name} "
                f"dirs={len(top_dirs)} py_files={py_count}"
            )
            return result

        except Exception as e:
            logger.error(f"[VECTOR][onboarding] quick_scan error: {e}")
            self.deduct_points(30, "task_failed")
            return {"root": repo_path, "error": str(e)}

    def trace_execution_path(self, entry_point: str, repo_path: str) -> list[str]:
        """Follow import chain from entry_point, return ordered list of key files.

        Only follows imports that resolve to local files inside repo_path.
        Stops at _MAX_TRACE_DEPTH. Never raises.
        """
        try:
            root = Path(repo_path).resolve()
            ep = Path(entry_point).resolve()
            if not ep.exists():
                # Try relative to repo_path
                ep = (root / entry_point).resolve()
            if not ep.exists():
                logger.warning(f"[VECTOR][onboarding] entry point not found: {entry_point}")
                return [str(entry_point)]

            visited: list[str] = []
            queue: list[Path] = [ep]
            seen: set[str] = set()

            while queue and len(visited) < _MAX_TRACE_DEPTH:
                current = queue.pop(0)
                key = str(current)
                if key in seen:
                    continue
                seen.add(key)
                visited.append(str(current.relative_to(root)) if root in current.parents else str(current))

                # Parse imports from current file
                try:
                    source = current.read_text(encoding="utf-8", errors="replace")
                    tree = ast.parse(source)
                except Exception:
                    continue

                for node in ast.walk(tree):
                    module_name: str | None = None
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            module_name = alias.name
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        module_name = node.module

                    if not module_name:
                        continue

                    # Convert module dotted path to file path
                    module_rel = module_name.replace(".", "/")
                    candidates = [
                        root / f"{module_rel}.py",
                        root / module_rel / "__init__.py",
                    ]
                    for cand in candidates:
                        if cand.exists() and str(cand) not in seen:
                            queue.append(cand)

            logger.info(
                f"[VECTOR][onboarding] trace_execution_path: "
                f"entry={ep.name} depth={len(visited)}"
            )
            self._get_memory().store(
                event_type="trace_execution_path",
                content=f"entry={entry_point} traced={len(visited)} files",
                tags=["onboarding", "trace"],
                source="codebase_onboarding_engineer",
            )
            self.award_points(20, "trace_done")
            return visited

        except Exception as e:
            logger.error(f"[VECTOR][onboarding] trace_execution_path error: {e}")
            self.deduct_points(30, "task_failed")
            return [f"error: {e}"]

    def generate_onboarding_doc(self, repo_path: str, context: str = "") -> str:
        """Produce a structured onboarding document grounded in the actual repo.

        Sections: 1-line summary, 5-min overview, deep-dive, key dependencies.
        Uses LLM (local Ollama) with repo facts. Never raises.
        """
        try:
            scan = self.quick_scan(repo_path)
            root = Path(repo_path).resolve()

            # Gather facts from scan
            dirs_str = ", ".join(scan.get("top_level_dirs", [])[:12]) or "(none found)"
            configs_str = ", ".join(scan.get("key_configs", [])) or "(none)"
            entries_str = ", ".join(scan.get("entry_points", [])) or "(not detected)"
            py_count = scan.get("source_file_count", 0)
            readme = scan.get("readme_snippet", "")[:300]

            # Attempt import trace for first entry point
            trace_lines: list[str] = []
            entry_pts = scan.get("entry_points", [])
            if entry_pts:
                trace_lines = self.trace_execution_path(entry_pts[0], repo_path)

            trace_str = "\n".join(f"  {i+1}. {f}" for i, f in enumerate(trace_lines[:10]))

            system_prompt = (
                "You are CodebaseOnboardingEngineer. Generate a concise onboarding document "
                "using ONLY the facts provided. Do NOT invent features, filenames, or behaviors "
                "not present in the facts. Structure:\n"
                "# [Repo Name] — 1-line summary\n"
                "## 5-Minute Overview\n"
                "## Deep Dive\n"
                "## Key Dependencies\n"
                "## Where to Start\n"
            )
            user_msg = (
                f"REPO: {root.name}\n"
                f"DIRECTORIES: {dirs_str}\n"
                f"ENTRY POINTS: {entries_str}\n"
                f"CONFIG FILES: {configs_str}\n"
                f"PYTHON FILE COUNT: {py_count}\n"
                f"README SNIPPET:\n{readme}\n"
                f"EXECUTION PATH (from {entries_str.split(',')[0].strip()}):\n{trace_str}\n"
                f"EXTRA CONTEXT: {context}\n\n"
                "Write the onboarding document now."
            )

            from core.prompt_library import get_library as _gl
            _lib = _gl().get_for_agent("codebase_onboarding_engineer") or ""
            _sys_final = (system_prompt + "\n\n" + _lib).strip() if _lib else system_prompt
            messages = [
                {"role": "system", "content": _sys_final},
                {"role": "user", "content": user_msg},
            ]

            doc = chat(model=self._model, messages=messages, timeout=30.0)

            if not doc:
                # Fallback: template-based doc without LLM
                doc = (
                    f"# {root.name} — Onboarding Guide\n\n"
                    f"## 5-Minute Overview\n"
                    f"- **Root:** `{root}`\n"
                    f"- **Top-level dirs:** {dirs_str}\n"
                    f"- **Entry points:** {entries_str}\n"
                    f"- **Python files:** {py_count}\n\n"
                    f"## Execution Path\n{trace_str}\n\n"
                    f"## Key Config Files\n{configs_str}\n\n"
                    f"## README\n{readme}\n"
                )
                logger.warning("[VECTOR][onboarding] LLM unavailable — template fallback used")

            self._get_memory().store(
                event_type="generate_onboarding_doc",
                content=f"repo={root.name} doc_len={len(doc)}",
                tags=["onboarding", "doc_generated"],
                source="codebase_onboarding_engineer",
            )
            self.award_points(30, "onboarding_doc_generated")
            logger.info(
                f"[VECTOR][onboarding] generate_onboarding_doc: "
                f"repo={root.name} doc_len={len(doc)}"
            )
            return doc

        except Exception as e:
            logger.error(f"[VECTOR][onboarding] generate_onboarding_doc error: {e}")
            self.deduct_points(30, "task_failed")
            return f"# Onboarding Error\n\nCould not generate document: {e}"

    # ------------------------------------------------------------------
    # run() — multi-task dispatcher
    # ------------------------------------------------------------------

    async def answer_question(self, query: str) -> str:
        """Answer a free-text onboarding/architecture question directly (no
        filesystem scan). Used by run() when a real chat query is present
        but no scan/trace/onboard was explicitly requested — 2026-07-29
        sweep, same bug class as #1/#14/#15/#21/#33 (wrong hardcoded default
        action instead of the real question)."""
        try:
            sys_prompt = (
                "You are CodebaseOnboardingEngineer, VECTOR's repo-navigation "
                "specialist. You scan repo structure, trace import chains from "
                "entry points, and generate onboarding docs grounded only in real "
                "facts from the code. Answer the user's question directly and "
                "concisely."
            )
            from core.prompt_library import get_library as _gl
            _lib = _gl().get_for_agent("codebase_onboarding_engineer") or ""
            _sys_final = (sys_prompt + "\n\n" + _lib).strip() if _lib else sys_prompt
            answer = chat(
                model=self._model,
                messages=[{"role": "system", "content": _sys_final}, {"role": "user", "content": query}],
                timeout=30.0,
            )
            self.award_points(10, "onboarding_qa_answered")
            return answer or "I don't have enough information to answer that right now."
        except Exception as e:
            logger.error(f"[VECTOR][onboarding] answer_question error: {e}")
            self.deduct_points(10, "task_failed")
            return f"Error answering question: {e}"

    async def run(self, task: dict) -> dict:
        """Dispatch task types: scan | trace | onboard | status."""
        try:
            task_type = task.get("type", "")
            p = task.get("params", {}) if isinstance(task.get("params"), dict) else {}
            repo_path = task.get("repo_path", task.get("path", p.get("repo_path", p.get("path", str(Path.cwd())))))

            query = (
                p.get("query") or p.get("content") or task.get("query")
                or task.get("prompt") or ""
            )
            if task_type not in ("scan", "trace", "onboard") and query.strip():
                answer = await self.answer_question(query)
                return {"status": "ok", "response": answer, "agent": self.name}

            if not task_type:
                task_type = "scan"

            if task_type == "scan":
                result = self.quick_scan(repo_path)
                self.award_points(30, "task_done")
                return {"status": "ok", **result}

            elif task_type == "trace":
                entry = task.get("entry_point", task.get("entry", ""))
                if not entry:
                    # Auto-detect
                    root = Path(repo_path)
                    for ep in _ENTRY_POINTS:
                        if (root / ep).exists():
                            entry = ep
                            break
                if not entry:
                    return {"status": "error", "error": "No entry point found or provided"}
                path_list = self.trace_execution_path(entry, repo_path)
                self.award_points(30, "task_done")
                return {"status": "ok", "path": path_list, "depth": len(path_list)}

            elif task_type == "onboard":
                context = task.get("context", "")
                doc = self.generate_onboarding_doc(repo_path, context)
                self.award_points(30, "task_done")
                return {"status": "ok", "document": doc, "doc_length": len(doc)}

            else:
                # Default: quick scan of current directory
                result = self.quick_scan(str(Path.cwd()))
                return {"status": "ok", **result}

        except Exception as e:
            logger.error(f"[VECTOR][onboarding] run error: {e}")
            self.deduct_points(30, "task_failed")
            return {"status": "error", "error": str(e)}

# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = CodebaseOnboardingEngineer()
        # Use the VECTOR codebase root as test target
        vector_root = str(Path(__file__).parent.parent.parent.parent.resolve())

        # 1. quick_scan
        result = await agent.run({"type": "scan", "repo_path": vector_root})
        assert result["status"] == "ok", f"scan failed: {result}"
        assert "top_level_dirs" in result
        assert isinstance(result["source_file_count"], int)
        print(f"[OK] scan: dirs={len(result['top_level_dirs'])} py_files={result['source_file_count']}")

        # 2. trace
        result2 = await agent.run({
            "type": "trace",
            "repo_path": vector_root,
            "entry_point": "run_vector.py",
        })
        assert result2["status"] == "ok", f"trace failed: {result2}"
        assert isinstance(result2["path"], list)
        print(f"[OK] trace: depth={result2['depth']} first={result2['path'][0] if result2['path'] else 'none'}")

        # 3. status (default type)
        result3 = await agent.run({"type": "status"})
        assert result3["status"] == "ok"
        print(f"[OK] run: status={result3['status']}")
        print("codebase_onboarding_engineer.py OK")

    asyncio.run(_smoke())
