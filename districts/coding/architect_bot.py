
import sys
import ast
import asyncio
import uuid
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase

_SKIP_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv", "test_tmp", "renders",
    "models", ".claude", "_cleanup_trash_2026-07-28", "graphify-out",
})

# Same confinement pattern as districts/coding/code_reviewer.py's
# review_with_llm() fix this cycle: explain_module() reads a caller-supplied
# path and sends its contents into an LLM prompt with no confinement at all
# -- zero real callers today, but the fix is narrow/mechanical with no
# legitimate-caller risk, same bar this cycle used for worktree.py/
# direct_executor.py's dormant-but-fixed-anyway findings.
_ROOT = Path(__file__).resolve().parents[2]


def _iter_python_files(root_path: Path) -> list[Path]:
    """All .py files under root, pruning vendor/junk directories while walking."""
    import os

    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        found.extend(Path(dirpath, f) for f in filenames if f.endswith(".py"))
    return found


class ArchitectBot(AgentBase):
    """Analyzes codebase structure and answers architecture questions."""

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "ArchitectBot", "coding")
        # 2026-08-06: governor capability-based routing requires agents to
        # declare what task_types they handle. Without this, write_code /
        # read_code / code_question queries get "no agent declares the
        # capability" errors even though ArchitectBot.answer_question()
        # handles them fine. See governor.py:2151-2154 (capability lookup).
        self.capabilities = [
            "architecture", "write_code", "read_code", "code_question",
            "scan_codebase", "scan", "code_search", "ask_architecture",
        ]
        if ghost:
            self.inherit_ghost(ghost)
        logger.info("[VECTOR][architect_bot] ArchitectBot initialized")

    def scan_codebase(self, root: str = ".") -> dict:
        """
        Walk Python files: count files, lines, classes, functions.
        Detect: potential circular imports (static), missing __init__.py.
        Returns {files: int, lines: int, classes: int, functions: int, issues: list[str]}
        """
        try:
            root_path = Path(root).resolve()
            if not root_path.exists():
                logger.error(f"[VECTOR][architect_bot] Root path does not exist: {root}")
                return {"files": 0, "lines": 0, "classes": 0, "functions": 0, "issues": [f"Root not found: {root}"]}

            total_files = 0
            total_lines = 0
            total_classes = 0
            total_functions = 0
            issues = []

            # Map: module_path → set of imported modules (for circular import detection)
            import_map: dict[str, set] = {}

            py_files = _iter_python_files(root_path)

            for py_file in py_files:
                try:
                    source = py_file.read_text(encoding="utf-8", errors="replace")
                except Exception as read_err:
                    issues.append(f"Cannot read {py_file}: {read_err}")
                    continue

                lines = source.splitlines()
                total_files += 1
                total_lines += len(lines)

                # One parse + one walk: class/function counts and imports together.
                try:
                    tree = ast.parse(source)
                except SyntaxError:
                    issues.append(f"SyntaxError in {py_file.relative_to(root_path)}")
                    continue
                mod_key = str(py_file.relative_to(root_path))
                local_imports: set[str] = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        total_classes += 1
                    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        total_functions += 1
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and (node.level > 0 or node.module.startswith("core")):
                            local_imports.add(node.module)
                    elif isinstance(node, ast.Import):
                        for alias in node.names:
                            local_imports.add(alias.name)
                import_map[mod_key] = local_imports

            # --- Missing __init__.py detection ---
            all_dirs = {f.parent for f in py_files if f.name != "__init__.py"}
            for d in sorted(all_dirs):
                init = d / "__init__.py"
                if not init.exists():
                    rel = d.relative_to(root_path) if root_path in d.parents or d == root_path else d
                    issues.append(f"Missing __init__.py in: {rel}")

            # --- Static circular import detection (simple: A imports B, B imports A) ---
            # 2026-09-24: was an O(n^2) all-pairs substring scan (90-216s on this repo,
            # blocking the event loop). Now a token index: a module "imports" another when
            # the other's file stem is a dotted component of one of its imports.
            tokens = {m: {t for imp in imps for t in imp.split(".")} for m, imps in import_map.items()}
            by_stem: dict[str, list[str]] = {}
            for mod in import_map:
                by_stem.setdefault(Path(mod).stem, []).append(mod)
            for mod_a, toks_a in tokens.items():
                stem_a = Path(mod_a).stem
                for tok in toks_a:
                    for mod_b in by_stem.get(tok, ()):
                        if mod_a < mod_b and stem_a in tokens[mod_b]:
                            issues.append(f"Potential circular import: {mod_a} <-> {mod_b}")

            if issues:
                self.deduct_points(5, "scan_found_issues")
            else:
                self.award_points(15, "scan_clean")

            logger.info(
                f"[VECTOR][architect_bot] Scan complete: {total_files} files, "
                f"{total_lines} lines, {total_classes} classes, {total_functions} functions, "
                f"{len(issues)} issues"
            )
            return {
                "files": total_files,
                "lines": total_lines,
                "classes": total_classes,
                "functions": total_functions,
                "issues": issues,
            }
        except Exception as e:
            logger.error(f"[VECTOR][architect_bot] scan_codebase error: {e}")
            self.deduct_points(10, "scan_error")
            return {"files": 0, "lines": 0, "classes": 0, "functions": 0, "issues": [str(e)]}

    def scan_codebase_with_graph(self, root: str = ".") -> dict:
        """
        Enhanced scan using code-review-graph for blast-radius analysis
        and large function detection. Falls back to basic scan if CRG not installed.
        """
        basic = self.scan_codebase(root)
        try:
            from districts.coding.code_review_graph import build_graph, find_large_functions
            graph_result = build_graph(root)
            large_fns = find_large_functions(root, min_lines=50)
            basic["graph_built"] = graph_result.get("status") == "ok"
            basic["large_functions"] = large_fns[:10]  # top 10
            if large_fns:
                basic["issues"].append(f"{len(large_fns)} functions exceed 50 lines — refactor candidates")
        except Exception as e:
            logger.warning(f"[VECTOR][architect_bot] CRG scan failed: {e}")
        return basic

    async def explain_module(self, file_path: str) -> str:
        """
        RULE 1: session_hydration_prompt() first.
        Read file, call vector-coder: "Explain this module's role in VECTOR. 2 sentences."
        Returns explanation string or error string.
        """
        try:
            fpath = Path(file_path).resolve()
            if not fpath.is_relative_to(_ROOT) or fpath.suffix != ".py":
                logger.error(f"[VECTOR][architect_bot] Path outside repo or not .py: {file_path}")
                return f"Error: Path outside repo or not a .py file — {file_path}"
            if not fpath.exists():
                logger.error(f"[VECTOR][architect_bot] File not found: {file_path}")
                return f"Error: File not found — {file_path}"

            # RULE 1 — hydrate before LLM call
            from core.loop.context_engine import ContextEngine
            ctx = ContextEngine()
            hydration = ctx.session_hydration_prompt({"task": "explain_module", "file": file_path})

            source = fpath.read_text(encoding="utf-8", errors="replace")
            MAX_CHARS = 4000
            if len(source) > MAX_CHARS:
                source = source[:MAX_CHARS] + "\n\n[... truncated ...]"

            from core.prompt_library import get_library as _get_lib
            _sys = _get_lib().get_for_agent("architect_bot") or "You are a senior software architect. Be concise and specific."

            prompt = (
                f"{hydration}\n\n"
                f"=== MODULE: {fpath.name} ===\n```python\n{source}\n```\n\n"
                "Explain this module's role in the VECTOR autonomous AI system in exactly 2 sentences. "
                "Be specific about what it does and how it fits into VECTOR's architecture."
            )

            from core.inference.provider_client import ProviderClient as _PC
            _result = await _PC().chat(
                messages=[{"role": "system", "content": _sys}, {"role": "user", "content": prompt}],
                model="domain:coding.architecture",   # o3 → glm-4.7 → gpt-5 → ... → ollama
                tier="coding",
                temperature=0.4,
                max_tokens=200,
                caller_id="architect_bot",
            )
            explanation = _result.content.strip()

            self.award_points(10, f"explained_{fpath.name}")
            logger.info(f"[VECTOR][architect_bot] Explained {fpath.name}: {len(explanation)} chars")
            return explanation

        except Exception as e:
            logger.error(f"[VECTOR][architect_bot] explain_module error: {e}")
            self.deduct_points(10, "explain_failed")
            return f"Error explaining module: {e}"

    async def answer_question(self, query: str) -> str:
        """Answer a free-text architecture question directly (no filesystem
        scan). Used by run() when a real chat query is present but no scan
        was explicitly requested — 2026-07-29 sweep, same bug class as
        #1/#14/#15/#21/#33 (wrong hardcoded default action instead of the
        real question)."""
        try:
            from core.loop.context_engine import ContextEngine
            hydration = ContextEngine().session_hydration_prompt({"task": "architect_qa"})
            from core.prompt_library import get_library as _get_lib
            _sys = _get_lib().get_for_agent("architect_bot") or (
                "You are ArchitectBot, VECTOR's codebase architecture specialist. "
                "You scan codebases for file/line/class/function counts, detect "
                "circular imports, find missing __init__.py files, and explain "
                "module roles. Answer the user's question directly and concisely."
            )
            from core.inference.provider_client import ProviderClient as _PC
            result = await _PC().chat(
                messages=[{"role": "system", "content": f"{hydration}\n\n{_sys}"},
                          {"role": "user", "content": query}],
                model="domain:coding.architecture",
                tier="coding",
                temperature=0.4,
                max_tokens=500,
                caller_id="architect_bot",
            )
            self.award_points(10, "architect_qa_answered")
            return result.content.strip()
        except Exception as e:
            logger.error(f"[VECTOR][architect_bot] answer_question error: {e}")
            self.deduct_points(10, "architect_qa_failed")
            return f"Error answering question: {e}"

    async def run(self, task: dict) -> dict:
        p = task.get("params", {}) if isinstance(task.get("params"), dict) else {}
        root = p.get("root", task.get("root"))
        use_graph = p.get("use_graph", task.get("use_graph", True))
        task_type = task.get("type", task.get("task_type", ""))

        query = (
            p.get("query") or p.get("content") or task.get("query")
            or task.get("prompt") or ""
        )

        # 2026-07-29: run() used to always run a filesystem scan of "." for
        # ANY task, including real free-text chat questions with no scan
        # intent at all (governor._dispatch_to_district -> agent.run(task)
        # puts the real question at task["params"]["query"]). Only scan when
        # explicitly requested (a known scan task_type, or an explicit
        # root/use_graph param) or when there's no real question to answer.
        explicit_scan = bool(
            root is not None
            or task_type in ("scan", "scan_codebase", "architecture", "architect")
        )
        if not explicit_scan and query.strip():
            answer = await self.answer_question(query)
            return {"status": "ok", "response": answer, "agent": self.name}

        root = root or "."
        # Off the event loop: the scan is synchronous CPU/file work.
        if use_graph:
            result = await asyncio.to_thread(self.scan_codebase_with_graph, root)
        else:
            result = await asyncio.to_thread(self.scan_codebase, root)
        # Phase 2C: if complex spec detected, request research help
        tech_stack = result.get("tech_stack") or result.get("languages", [])
        if tech_stack:
            # ResearchHub is the agent's actual registered .name (PascalCase
            # class name), not the manifest's lowercase "research_hub" key —
            # request_agent_help looks up by .name, not manifest key.
            #
            # 2026-09-26: this is a request for HELP, not a step the scan depends on, so it runs in the background.
            # It used to be awaited, which only looked harmless because DeepResearcher rejected "deep_research" as an
            # unknown type instantly; now that the advertised type is real (a 1-3 minute web research call), awaiting it
            # here held every scan/read_code action for minutes and pushed it past the Governor's timeout.
            self._spawn_research_help(tech_stack)
        return {"status": "ok", **result}

    def _spawn_research_help(self, tech_stack) -> None:
        async def _ask() -> None:
            try:
                await self.request_agent_help("ResearchHub", {
                    "type": "deep_research",
                    "params": {"query": f"best practices for {tech_stack}"},
                })
            except Exception as e:
                logger.debug(f"[VECTOR][architect_bot] request_agent_help failed: {e}")

        try:
            task = asyncio.get_running_loop().create_task(_ask())
        except RuntimeError:
            return  # no running loop (sync caller): skip the optional help request
        pending = self.__dict__.setdefault("_help_tasks", set())
        pending.add(task)  # hold a reference so the task is not garbage-collected mid-flight
        task.add_done_callback(pending.discard)

    async def run_forever(self) -> None:
        """RULE 2 — never stops. ArchitectBot is event-driven; this keeps the agent alive."""
        logger.info("[VECTOR][architect_bot] run_forever started — event-driven mode")
        while self.is_alive:
            try:
                for _ in range(60):
                    if not self.is_alive:
                        break
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"[VECTOR][architect_bot] tick error: {e}")
                self.deduct_points(5, "tick_error")
        logger.warning("[VECTOR][architect_bot] died — HP=0")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import asyncio

    bot = ArchitectBot()

    # Smoke test 1: scan the coding district itself
    DISTRICT_PATH = str(Path(__file__).parent.resolve())
    scan_result = bot.scan_codebase(DISTRICT_PATH)
    scan_ok = (
        isinstance(scan_result, dict)
        and "files" in scan_result
        and "lines" in scan_result
        and "classes" in scan_result
        and "functions" in scan_result
        and "issues" in scan_result
        and scan_result["files"] > 0
        and scan_result["classes"] >= 1
    )
    print(
        f"  scan_codebase(coding district): files={scan_result['files']}, "
        f"lines={scan_result['lines']}, classes={scan_result['classes']}, "
        f"functions={scan_result['functions']}, issues={len(scan_result['issues'])}"
    )

    # Smoke test 2: scan a single file to verify line/class counting
    SINGLE_FILE_DIR = str(Path(__file__).parent.parent.parent.parent / "core" / "city")
    single_result = bot.scan_codebase(SINGLE_FILE_DIR)
    single_ok = isinstance(single_result, dict) and single_result["files"] >= 1

    # Smoke test 3: agent state
    agent_ok = bot.health_points > 0 and bot.name == "ArchitectBot"

    all_ok = scan_ok and single_ok and agent_ok
    print("✅ architect_bot.py OK" if all_ok else "❌ FAILED")
