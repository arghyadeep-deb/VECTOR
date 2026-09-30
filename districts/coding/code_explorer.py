"""
Code Explorer — deep code reading, execution path tracing, architecture mapping.
Loaded from: vectorcode/agents/vector-code-explorer.md
District: coding
"""
import asyncio
import ast
from pathlib import Path

from loguru import logger
from core.city.prompt_agent import PromptAgent


class CodeExplorer(PromptAgent):
    """
    Deep code exploration: traces execution paths, maps dependencies,
    explains unfamiliar codebases. Different from codebase_onboarding_engineer —
    this is interactive exploration, not onboarding doc generation.
    Powered by vector-code-explorer.md system prompt.
    """

    def __init__(self):
        super().__init__("vector-code-explorer.md", "code_explorer_001", "coding")
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = ["explain", "structure"]

    def get_imports(self, filepath: str) -> list[str]:
        """Extract all imports from a Python file."""
        try:
            tree = ast.parse(Path(filepath).read_text(encoding="utf-8", errors="ignore"))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    imports.extend(f"{module}.{alias.name}" for alias in node.names)
            return sorted(set(imports))
        except Exception:
            return []

    def get_classes_and_functions(self, filepath: str) -> dict:
        """Extract top-level classes and functions from a Python file."""
        try:
            tree = ast.parse(Path(filepath).read_text(encoding="utf-8", errors="ignore"))
            result: dict = {"classes": [], "functions": []}
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    methods = [n.name for n in ast.walk(node) if isinstance(n, ast.FunctionDef)]
                    result["classes"].append({"name": node.name, "line": node.lineno, "methods": methods})
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result["functions"].append({"name": node.name, "line": node.lineno})
            return result
        except Exception:
            return {"classes": [], "functions": []}

    async def explain_file(self, filepath: str) -> dict:
        """Ask LLM to explain what a file does based on its structure."""
        try:
            content = Path(filepath).read_text(encoding="utf-8", errors="ignore")[:3000]
        except Exception as e:
            return {"status": "error", "error": str(e)}
        structure = self.get_classes_and_functions(filepath)
        query = (
            f"Explain what this Python file does in 3-5 sentences. "
            f"Be specific about its purpose in the VECTOR codebase.\n\n"
            f"File: {filepath}\n"
            f"Classes: {[c['name'] for c in structure['classes']]}\n"
            f"Functions: {[f['name'] for f in structure['functions']]}\n\n"
            f"```python\n{content}\n```"
        )
        explanation = await self.ask(query, timeout=30.0)
        return {
            "status": "ok",
            "file": filepath,
            "explanation": explanation,
            "structure": structure,
            "imports": self.get_imports(filepath)[:10],
        }

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- every branch
        # below read its arguments straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Flattening params into task once (params
        # values win on overlap) keeps every existing flat-shape
        # caller/test working unchanged while fixing all branches at once.
        task = {**task, **(task.get("params") or {})}
        task_type = task.get("type", "ask")
        try:
            if task_type == "explain":
                result = await self.explain_file(task.get("filepath", ""))
                self.award_points(20, "file_explained")
                return result
            elif task_type == "structure":
                filepath = task.get("filepath", "")
                structure = self.get_classes_and_functions(filepath)
                imports = self.get_imports(filepath)
                self.award_points(10, "structure_extracted")
                return {"status": "ok", "structure": structure, "imports": imports}
            else:
                return await super().run(task)
        except Exception as e:
            logger.error("[VECTOR][code_explorer] {}", e)
            self.deduct_points(30, "exploration_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")
    async def _smoke():
        agent = CodeExplorer()
        print(f"[OK] loaded: {agent.name}")
        structure = agent.get_classes_and_functions(__file__)
        print(f"[OK] structure: {len(structure['classes'])} classes, {len(structure['functions'])} functions")
        imports = agent.get_imports(__file__)
        print(f"[OK] imports: {len(imports)} found")
        print("code_explorer.py OK")
    asyncio.run(_smoke())
