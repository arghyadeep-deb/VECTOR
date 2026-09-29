import sys
import ast
import uuid
import asyncio
import datetime
from pathlib import Path

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from loguru import logger

_REASONING = CONFIG["models"]["reasoning"]
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_DOCS_DIR = _BASE_DIR / "docs"


class TechnicalWriter(AgentBase):
    """
    Auto-generates developer documentation for VECTOR's own modules.
    Scans Python files with `ast`, produces markdown docs, writes to docs/ and Obsidian.
    RULE 11: vector-reasoning (local), not Claude API.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="TechnicalWriter",
            district="documentation",
            generation=generation,
        )
        self.capabilities = ["api_reference", "district_readme", "docs", "document_module", "documentation", "generate_docs", "write"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        _DOCS_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"[VECTOR][technical_writer] ready gen={generation}")

    # ── Parsing ────────────────────────────────────────────────────────────────

    def scan_module(self, file_path: str) -> dict:
        """
        Read a Python file and extract classes, functions, and docstrings using ast.
        Returns a structured dict safe to pass to the LLM.
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"[VECTOR][technical_writer] file not found: {file_path}")
            return {"error": f"file not found: {file_path}"}

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except SyntaxError as e:
            logger.warning(f"[VECTOR][technical_writer] syntax error in {file_path}: {e}")
            return {"error": str(e), "file": str(path)}

        module_doc = ast.get_docstring(tree) or ""
        classes: list[dict] = []
        functions: list[dict] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = []
                for item in ast.walk(node):
                    if isinstance(item, ast.FunctionDef) and item.col_offset > node.col_offset:
                        args = [a.arg for a in item.args.args]
                        methods.append({
                            "name": item.name,
                            "args": args,
                            "docstring": ast.get_docstring(item) or "",
                            "lineno": item.lineno,
                        })
                classes.append({
                    "name": node.name,
                    "docstring": ast.get_docstring(node) or "",
                    "methods": methods,
                    "lineno": node.lineno,
                    "bases": [
                        (b.id if isinstance(b, ast.Name) else ast.unparse(b))
                        for b in node.bases
                    ],
                })
            elif isinstance(node, ast.FunctionDef) and node.col_offset == 0:
                args = [a.arg for a in node.args.args]
                functions.append({
                    "name": node.name,
                    "args": args,
                    "docstring": ast.get_docstring(node) or "",
                    "lineno": node.lineno,
                })

        return {
            "file": str(path.relative_to(_BASE_DIR) if path.is_relative_to(_BASE_DIR) else path),
            "module_docstring": module_doc,
            "classes": classes,
            "functions": functions,
            "lines": len(source.splitlines()),
        }

    # ── LLM calls ─────────────────────────────────────────────────────────────

    def _llm(self, prompt: str, system: str = "") -> str:
        """Thin wrapper — always hydrates context first (RULE 1)."""
        from core.prompt_library import get_library as _gl
        _lib = _gl().get_for_agent("technical_writer") or ""
        hydration = system or self._context.session_hydration_prompt()
        if _lib:
            hydration = (hydration + "\n\n" + _lib).strip()
        try:
            from core.inference.vectorcode_llm import chat
            text = chat(
                model=_REASONING,
                messages=[
                    {"role": "system", "content": hydration},
                    {"role": "user", "content": prompt},
                ],
                timeout=90.0,
            )
            if not text:
                raise ValueError("empty LLM response")
            return text
        except Exception as e:
            logger.warning(f"[VECTOR][technical_writer] LLM unavailable: {e}")
            return ""

    def generate_module_docs(self, module_path: str) -> str:
        """
        LLM call → produce clean markdown documentation for a single module.
        Returns the markdown string.
        """
        scan = self.scan_module(module_path)
        if "error" in scan:
            return f"# Error\n\n{scan['error']}"

        prompt = (
            f"Generate clean developer markdown documentation for this Python module.\n\n"
            f"File: `{scan['file']}`\n"
            f"Lines: {scan['lines']}\n"
            f"Module docstring: {scan['module_docstring'] or '(none)'}\n\n"
            f"Classes: {scan['classes']}\n\n"
            f"Top-level functions: {scan['functions']}\n\n"
            "Format: ## Overview, ## Classes (with method tables), ## Functions, ## Usage Example"
        )
        text = self._llm(prompt)
        if not text:
            # Fallback: structured but plain
            lines = [f"# `{scan['file']}`\n", f"{scan['module_docstring']}\n"]
            for cls in scan["classes"]:
                lines.append(f"\n## class `{cls['name']}`\n\n{cls['docstring']}\n")
                for m in cls["methods"]:
                    lines.append(f"- `{m['name']}({', '.join(m['args'])})` — {m['docstring'] or 'no docstring'}\n")
            for fn in scan["functions"]:
                lines.append(f"\n## `{fn['name']}({', '.join(fn['args'])})`\n\n{fn['docstring'] or 'no docstring'}\n")
            text = "".join(lines)
        return text

    def generate_api_reference(self) -> str:
        """
        Scan the entire core/ directory and produce a consolidated API reference markdown.
        """
        core_dir = _BASE_DIR / "core"
        if not core_dir.exists():
            return "# API Reference\n\n*core/ directory not found.*"

        py_files = sorted(core_dir.rglob("*.py"))
        sections: list[str] = ["# VECTOR API Reference\n\n*Auto-generated by TechnicalWriter*\n"]
        hydration = self._context.session_hydration_prompt()
        from core.prompt_library import get_library as _gl
        _tw_lib = _gl().get_for_agent("technical_writer") or ""
        if _tw_lib:
            hydration = (hydration + "\n\n" + _tw_lib).strip()

        for py in py_files:
            if "__pycache__" in py.parts or py.name.startswith("_"):
                continue
            scan = self.scan_module(str(py))
            if "error" in scan or (not scan["classes"] and not scan["functions"]):
                continue
            rel = scan["file"]
            sections.append(f"\n---\n\n## `{rel}`\n\n")
            for cls in scan["classes"]:
                sections.append(f"### class `{cls['name']}`\n\n{cls['docstring']}\n\n")
                for m in cls["methods"]:
                    sections.append(
                        f"- **`{m['name']}({', '.join(m['args'])})`** — {m['docstring'] or 'no docstring'}\n"
                    )
                sections.append("\n")
            for fn in scan["functions"]:
                sections.append(
                    f"### `{fn['name']}({', '.join(fn['args'])})`\n\n{fn['docstring'] or 'no docstring'}\n\n"
                )

        # LLM pass: summarise each section header
        try:
            from core.inference.vectorcode_llm import chat
            raw = "".join(sections)
            summary_prompt = (
                "Rewrite this API reference with a brief one-line description after each "
                "class/function header. Keep all existing content. Add a TOC at the top.\n\n"
                f"{raw[:6000]}"  # keep prompt manageable
            )
            improved = chat(
                model=_REASONING,
                messages=[
                    {"role": "system", "content": hydration},
                    {"role": "user", "content": summary_prompt},
                ],
                timeout=120.0,
            )
            if improved:
                return improved + "\n\n---\n*More modules truncated for readability.*\n"
        except Exception as e:
            logger.warning(f"[VECTOR][technical_writer] LLM pass failed: {e}")

        return "".join(sections)

    def generate_readme_section(self, district: str) -> str:
        """
        LLM call → document what a district does and which agents it contains.
        """
        district_dir = _BASE_DIR / "agents" / "districts" / district
        agent_files: list[str] = []
        if district_dir.exists():
            agent_files = [f.stem for f in district_dir.glob("*.py") if not f.name.startswith("_")]

        prompt = (
            f"Write a README section for the VECTOR '{district}' district.\n\n"
            f"Known agent files: {agent_files or ['(none yet)']}\n\n"
            "Format:\n"
            "## District: {district_name}\n"
            "**Purpose:** one sentence\n"
            "**Agents:**\n"
            "- AgentName — what it does\n\n"
            "**Integration points:** how it connects to other districts\n"
        )
        text = self._llm(prompt)
        if not text:
            agents_md = "\n".join(f"- `{a}`" for a in agent_files) or "*(none)*"
            text = (
                f"## District: {district}\n\n"
                f"**Agents:**\n{agents_md}\n"
            )
        return text

    # ── Write ──────────────────────────────────────────────────────────────────

    def write_docs(self, content: str, filename: str) -> bool:
        """
        Write content to docs/ folder and also push to Obsidian Research/ folder.
        Returns True on success.
        """
        # Write to docs/ on disk
        out_path = _DOCS_DIR / filename
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            logger.info(f"[VECTOR][technical_writer] wrote {out_path}")
        except Exception as e:
            logger.error(f"[VECTOR][technical_writer] disk write failed: {e}")
            return False

        # Mirror to Obsidian Research/ folder
        title = Path(filename).stem.replace("_", " ").title()
        try:
            self._obsidian.write_note(
                title=title,
                content=content,
                folder="Research",
                tags=["documentation", "auto-generated", "vector"],
            )
        except Exception as e:
            logger.warning(f"[VECTOR][technical_writer] obsidian mirror failed: {e}")
            # Not fatal — disk write succeeded

        return True

    # ── run ───────────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        """
        task["type"]:
          "document_module"  → params["module_path"] required
          "api_reference"    → scans all of core/
          "district_readme"  → params["district"] required
        """
        task_type = task.get("type", "")
        params = task.get("params", {})

        try:
            if task_type == "document_module":
                module_path = params.get("module_path", "")
                if not module_path:
                    return {"status": "error", "reason": "module_path required"}
                content = self.generate_module_docs(module_path)
                filename = Path(module_path).stem + "_docs.md"
                ok = self.write_docs(content, filename)
                if ok:
                    self._memory.store(
                        event_type="doc_generated",
                        content=f"Module docs written for {module_path}",
                        tags=["documentation", "module"],
                        source="technical_writer",
                    )
                    self._memory.store_chain(
                        situation="document_module",
                        goal_ids=["documentation"],
                        steps=["scan_module", "llm_generate", "write_docs"],
                        action="generate_module_docs",
                        outcome=f"docs written: {filename}",
                        reward=0.8,
                    )
                    self.award_points(50, f"module docs: {filename}")
                    return {"status": "ok", "file": filename}
                else:
                    self.deduct_points(30, "module doc write failed")
                    return {"status": "error", "reason": "write failed"}

            elif task_type == "api_reference":
                content = self.generate_api_reference()
                ok = self.write_docs(content, "api_reference.md")
                if ok:
                    self._memory.store(
                        event_type="doc_generated",
                        content="Full API reference generated",
                        tags=["documentation", "api_reference"],
                        source="technical_writer",
                    )
                    self.award_points(50, "api_reference generated")
                    return {"status": "ok", "file": "api_reference.md"}
                else:
                    self.deduct_points(30, "api_reference write failed")
                    return {"status": "error", "reason": "write failed"}

            elif task_type == "district_readme":
                district = params.get("district", "")
                if not district:
                    return {"status": "error", "reason": "district required"}
                content = self.generate_readme_section(district)
                filename = f"district_{district}_readme.md"
                ok = self.write_docs(content, filename)
                if ok:
                    self._memory.store(
                        event_type="doc_generated",
                        content=f"District README generated for {district}",
                        tags=["documentation", "district_readme", district],
                        source="technical_writer",
                    )
                    self.award_points(50, f"district readme: {district}")
                    return {"status": "ok", "file": filename}
                else:
                    self.deduct_points(30, "district readme write failed")
                    return {"status": "error", "reason": "write failed"}

            else:
                return {"status": "error", "reason": f"unknown task type: {task_type}"}

        except Exception as e:
            logger.error(f"[VECTOR][technical_writer] run error: {e}")
            self.deduct_points(30, f"run exception: {e}")
            return {"status": "error", "reason": str(e)}

    async def run_forever(self) -> None:
        logger.info("[VECTOR][technical_writer] run_forever — event-driven")
        while self.is_alive:
            try:
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"[VECTOR][technical_writer] tick: {e}")
        logger.warning("[VECTOR][technical_writer] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile

    agent = TechnicalWriter()
    assert agent.health_points == 500, f"expected 500 HP, got {agent.health_points}"

    # Smoke test: scan this file itself
    scan = agent.scan_module(__file__)
    assert "error" not in scan, f"scan_module failed: {scan}"
    assert any(c["name"] == "TechnicalWriter" for c in scan["classes"]), "class not found in scan"

    # Smoke test: write_docs to temp dir
    with tempfile.TemporaryDirectory() as tmp:
        _DOCS_DIR_orig = _DOCS_DIR
        import districts.qa.technical_writer as _self_mod
        _self_mod._DOCS_DIR = Path(tmp)
        ok = agent.write_docs("# Test\n\nContent.", "test_doc.md")
        _self_mod._DOCS_DIR = _DOCS_DIR_orig
        assert ok, "write_docs returned False"

    print(f"✅ technical_writer.py OK HP={agent.health_points}")
