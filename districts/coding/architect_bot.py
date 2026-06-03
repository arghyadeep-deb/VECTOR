
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import sys
import ast
import uuid
from pathlib import Path

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


class ArchitectBot(AgentBase):
    """Analyzes codebase structure and answers architecture questions."""

    def __init__(self, ghost: dict = None):
        super().__init__(str(uuid.uuid4()), "ArchitectBot", "coding")
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

            py_files = list(root_path.rglob("*.py"))

            for py_file in py_files:
                try:
                    source = py_file.read_text(encoding="utf-8", errors="replace")
                except Exception as read_err:
                    issues.append(f"Cannot read {py_file}: {read_err}")
                    continue

                lines = source.splitlines()
                total_files += 1
                total_lines += len(lines)

                # AST walk for class/function counts
                try:
                    tree = ast.parse(source)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            total_classes += 1
                        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            total_functions += 1
                except SyntaxError:
                    issues.append(f"SyntaxError in {py_file.relative_to(root_path)}")
                    continue

                # Collect imports for circular detection
                mod_key = str(py_file.relative_to(root_path))
                local_imports: set[str] = set()
                try:
                    for node in ast.walk(ast.parse(source)):
                        if isinstance(node, ast.ImportFrom):
                            if node.module:
                                is_relative = node.level > 0
                                is_local_absolute = node.module.startswith("core")
                                if is_relative or is_local_absolute:
                                    local_imports.add(node.module)
                        elif isinstance(node, ast.Import):
                            for alias in node.names:
                                local_imports.add(alias.name)
                except Exception:
                    logger.debug("[VECTOR] suppressed exception", exc_info=True)
                import_map[mod_key] = local_imports

            # --- Missing __init__.py detection ---
            all_dirs = {f.parent for f in py_files if f.name != "__init__.py"}
            for d in sorted(all_dirs):
                init = d / "__init__.py"
                if not init.exists():
                    rel = d.relative_to(root_path) if root_path in d.parents or d == root_path else d
                    issues.append(f"Missing __init__.py in: {rel}")

            # --- Static circular import detection (simple: A imports B, B imports A) ---
            # Build reverse map for quick lookup
            for mod_a, imports_a in import_map.items():
                for mod_b, imports_b in import_map.items():
                    if mod_a >= mod_b:
                        continue
                    # Check if any import name from A appears in B's file path prefix and vice versa
                    stem_a = Path(mod_a).stem
                    stem_b = Path(mod_b).stem
                    a_imports_b = any(stem_b in imp for imp in imports_a)
                    b_imports_a = any(stem_a in imp for imp in imports_b)
                    if a_imports_b and b_imports_a:
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
            fpath = Path(file_path)
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

            model = CONFIG["models"].get("coder", "vector-coder")
            ollama_host = CONFIG.get("ollama_host", "http://127.0.0.1:11434")

            prompt = (
                f"{hydration}\n\n"
                f"=== MODULE: {fpath.name} ===\n```python\n{source}\n```\n\n"
                "Explain this module's role in the VECTOR autonomous AI system in exactly 2 sentences. "
                "Be specific about what it does and how it fits into VECTOR's architecture."
            )

            import httpx
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{ollama_host}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                )
                resp.raise_for_status()
                explanation = resp.json().get("response", "").strip()

            self.award_points(10, f"explained_{fpath.name}")
            logger.info(f"[VECTOR][architect_bot] Explained {fpath.name}: {len(explanation)} chars")
            return explanation

        except Exception as e:
            logger.error(f"[VECTOR][architect_bot] explain_module error: {e}")
            self.deduct_points(10, "explain_failed")
            return f"Error explaining module: {e}"


    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        root = p.get("root", ".")
        use_graph = p.get("use_graph", True)
        if use_graph:
            result = self.scan_codebase_with_graph(root)
        else:
            result = self.scan_codebase(root)
        # Phase 2C: if complex spec detected, request research help
        tech_stack = result.get("tech_stack") or result.get("languages", [])
        if tech_stack:
            try:
                await self.request_agent_help("research_hub", {
                    "type": "deep_research",
                    "params": {"query": f"best practices for {tech_stack}"},
                })
            except Exception as e:
                logger.debug(f"[VECTOR][architect_bot] request_agent_help failed: {e}")
        return {"status": "ok", **result}

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
