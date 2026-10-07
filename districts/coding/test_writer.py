import sys
import uuid
import ast
import re
import json
import subprocess
from pathlib import Path
from districts.coding.path_security import is_path_within
from typing import Optional

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase

# write_tests_for_file() reads a caller-supplied path and sends its content
# into an LLM prompt (_build_llm_prompt) with no confinement at all --
# reachable via Governor dispatch (run()'s p["file"]). Same bug class fixed
# in architect_bot.py/bug_hunter.py/code_explorer.py this cycle.
_ROOT = Path(__file__).resolve().parents[2]


class TestWriter(AgentBase):
    """
    Scans the codebase for untested Python files and writes pytest unit tests.
    Uses LLM to generate contextually appropriate test cases.
    """

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "TestWriter", "coding")
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = [
            "write_tests", "generate_tests", "test_coverage", "find_untested",
        ]
        if ghost:
            self.inherit_ghost(ghost)
        self._test_dir = Path(CONFIG.get("coding", {}).get("repo_path", ".")) / "tests"
        self._test_dir.mkdir(parents=True, exist_ok=True)
        self._test_cache: dict[str, bool] = {}
        logger.info("[VECTOR][test_writer] TestWriter initialized")

    def scan_for_untested_modules(self) -> list[dict]:
        """
        Scan the codebase for Python files that lack corresponding test files.
        Returns list of dicts with {file_path, module_name, reasons}.
        """
        repo_path = Path(CONFIG.get("coding", {}).get("repo_path", "."))
        untested = []
        tested_modules = set()

        if self._test_dir.exists():
            for test_file in self._test_dir.rglob("test_*.py"):
                module_name = test_file.stem.replace("test_", "")
                tested_modules.add(module_name)

        for py_file in repo_path.rglob("*.py"):
            if "venv" in str(py_file) or "__pycache__" in str(py_file):
                continue
            if py_file.name.startswith("test_"):
                continue

            module_name = py_file.stem
            test_file = self._test_dir / f"test_{module_name}.py"

            if module_name not in tested_modules and not test_file.exists():
                try:
                    with open(py_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    tree = ast.parse(content)
                    functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
                    classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

                    if functions or classes:
                        untested.append({
                            "file_path": str(py_file),
                            "module_name": module_name,
                            "functions": functions,
                            "classes": classes,
                            "line_count": len(content.splitlines()),
                            "priority": self._calculate_priority(functions, classes)
                        })
                except SyntaxError:
                    logger.warning(f"[VECTOR][test_writer] Skipping syntax error in {py_file}")
                    continue

        untested.sort(key=lambda x: x["priority"], reverse=True)
        logger.info(f"[VECTOR][test_writer] Found {len(untested)} untested modules")
        return untested

    def _calculate_priority(self, functions: list, classes: list) -> int:
        """Calculate test priority based on code complexity."""
        priority = 0
        priority += len([f for f in functions if not f.startswith("_")]) * 2
        priority += len(classes) * 5
        priority += len([f for f in functions if f.startswith("test_") or f.startswith("_")])
        return priority

    def write_tests_for_file(self, filepath: str, output_dir: Optional[Path] = None) -> Path:
        """
        Write pytest test file for a given Python source file.
        Generates comprehensive tests using AST analysis and LLM suggestions.
        """
        source_path = Path(filepath).resolve()
        if not is_path_within(source_path, _ROOT) or source_path.suffix != ".py":
            raise ValueError(f"Path outside repo or not .py: {filepath}")
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {filepath}")

        with open(source_path, "r", encoding="utf-8") as f:
            source_code = f.read()

        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            logger.error(f"[VECTOR][test_writer] Cannot parse {filepath}: {e}")
            raise

        test_cases = self._extract_test_cases(tree, source_code)
        test_code = self._generate_test_code(source_path.stem, test_cases, source_code)

        output_path = (output_dir or self._test_dir) / f"test_{source_path.stem}.py"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(test_code, encoding="utf-8")

        self._test_cache[str(source_path)] = True
        self.award_points(10, f"tests_written_for_{source_path.stem}")
        logger.info(f"[VECTOR][test_writer] Wrote tests to {output_path}")
        return output_path

    def _extract_test_cases(self, tree: ast.AST, source_code: str) -> list[dict]:
        """Extract functions and classes that need testing."""
        test_cases = []
        lines = source_code.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
                public_methods = [m for m in methods if not m.name.startswith("_")]

                for method in public_methods:
                    args = [arg.arg for arg in method.args.args if arg.arg != "self"]
                    test_cases.append({
                        "type": "method",
                        "class_name": node.name,
                        "name": method.name,
                        "args": args,
                        "decorators": [d for d in method.decorator_list if isinstance(d, ast.Name)],
                        "has_return": method.returns is not None
                    })

            elif isinstance(node, ast.FunctionDef):
                if not node.name.startswith("_"):
                    args = [arg.arg for arg in node.args.args]
                    test_cases.append({
                        "type": "function",
                        "name": node.name,
                        "args": args,
                        "decorators": [d for d in node.decorator_list if isinstance(d, ast.Name)],
                        "has_return": node.returns is not None
                    })

        return test_cases

    def _generate_test_code(self, module_name: str, test_cases: list[dict], source_code: str) -> str:
        """Generate pytest test code from extracted test cases."""
        imports = [
            "import pytest",
            "import sys",
            "from pathlib import Path",
            f"sys.path.insert(0, str(Path(__file__).parent.parent))",
            f"from {module_name} import *",
            "",
        ]

        fixtures = self._generate_fixtures(module_name)
        test_functions = []

        for i, case in enumerate(test_cases):
            if case["type"] == "class":
                test_functions.append(self._generate_class_tests(case, i))
            else:
                test_functions.append(self._generate_function_tests(case, i))

        prompt = self._build_llm_prompt(module_name, test_cases, source_code)
        llm_suggestions = self._get_llm_test_suggestions(prompt)

        code = [
            f'"""',
            f"Generated tests for {module_name}",
            f"Auto-generated by VECTOR TestWriter Agent",
            f'"""',
            "",
        ]
        code.extend(imports)
        code.append("")
        code.extend(fixtures)
        code.append("")
        code.extend(test_functions)

        if llm_suggestions:
            code.append("")
            code.append("# LLM-generated additional tests")
            code.append(llm_suggestions)

        return "\n".join(code)

    def _generate_fixtures(self, module_name: str) -> list[str]:
        """Generate pytest fixtures for the test module."""
        return [
            "@pytest.fixture",
            f"def {module_name}_module():",
            f'    """Fixture to provide module context."""',
            f"    return sys.modules.get('{module_name}')",
            "",
            "@pytest.fixture",
            "def sample_data():",
            '    """Fixture to provide sample test data."""',
            "    return {",
            '        "string_data": "test_string",',
            '        "int_data": 42,',
            '        "float_data": 3.14,',
            '        "list_data": [1, 2, 3],',
            '        "dict_data": {"key": "value"}',
            "    }",
            "",
            "@pytest.fixture",
            "def temp_file(tmp_path):",
            '    """Fixture to provide a temporary file path."""',
            "    return tmp_path / 'test_file.txt'",
        ]

    def _generate_class_tests(self, case: dict, index: int) -> list[str]:
        """Generate test methods for a class."""
        class_name = case["class_name"]
        method_name = case["name"]
        args = case["args"]

        tests = [
            f"class Test{class_name}:",
            f'    """Tests for {class_name} class."""',
            "",
            f"    def test_{method_name}_success(self):",
            f'        """Test {method_name} with valid input."""',
            f"        instance = {class_name}()",
        ]

        if args:
            tests.append(f"        result = instance.{method_name}({', '.join(repr(a) for a in args[:2])}")
            tests[-1] += ")"
        else:
            tests.append(f"        result = instance.{method_name}()")

        if case["has_return"]:
            tests.append("        assert result is not None")
        else:
            tests.append("        assert True")

        tests.extend([
            "",
            f"    def test_{method_name}_raises_on_invalid_input(self):",
            f'        """Test {method_name} raises exception on invalid input."""',
            f"        instance = {class_name}()",
            f"        with pytest.raises((ValueError, TypeError)):",
            f"            instance.{method_name}(None)",
        ])

        return tests

    def _generate_function_tests(self, case: dict, index: int) -> list[str]:
        """Generate test function for a standalone function."""
        func_name = case["name"]
        args = case["args"]

        tests = [
            f"def test_{func_name}_basic():",
            f'    """Test {func_name} with basic input."""',
        ]

        if args:
            test_args = ", ".join(repr(a) for a in args[:2])
            tests.append(f"    result = {func_name}({test_args})")
        else:
            tests.append(f"    result = {func_name}()")

        if case["has_return"]:
            tests.append("    assert result is not None")
        else:
            tests.append("    assert True")

        tests.extend([
            "",
            f"@pytest.mark.parametrize('input_value,expected', [",
            f"    ({repr(args[0]) if args else 'None'}, True),",
            f"    ({repr(args[1]) if len(args) > 1 else 'None'}, True),",
            f"])",
            f"def test_{func_name}_parametrized(input_value, expected):",
            f'    """Parametrized test for {func_name}."""',
            f"    result = {func_name}(input_value) if input_value else {func_name}()",
            "    assert result is not None",
        ])

        return tests

    def _build_llm_prompt(self, module_name: str, test_cases: list[dict], source_code: str) -> str:
        """Build prompt for LLM to suggest additional test cases."""
        case_summary = "\n".join([
            f"- {c['type']}: {c.get('class_name', '')}.{c['name']}({', '.join(c['args'])})"
            for c in test_cases[:10]
        ])

        return f"""Analyze this Python module '{module_name}' and suggest additional pytest test cases.

Existing code structure:
{case_summary}

Source code (first 100 lines):
{source_code[:4000]}

Generate additional edge case tests and integration tests that would be valuable.
Return pytest code only, no explanations.
"""

    def _get_llm_test_suggestions(self, prompt: str) -> str:
        """Get additional test suggestions from LLM."""
        try:
            import asyncio as _asyncio
            import concurrent.futures as _cf
            from core.inference.provider_client import ProviderClient as _PC
            from core.loop.context_engine import ContextEngine
            async def _call():
                # RULE 1: session_hydration_prompt() before every LLM call.
                hydration = ContextEngine().session_hydration_prompt({"query": prompt})
                r = await _PC().chat(
                    messages=[{"role": "system", "content": hydration},
                              {"role": "user", "content": prompt}],
                    model="domain:coding.generation",
                    tier="coding", temperature=0.3, max_tokens=600,
                    caller_id="test_writer",
                )
                return r.content
            with _cf.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(_asyncio.run, _call()).result(timeout=90)
        except Exception as e:
            logger.warning(f"[VECTOR][test_writer] LLM suggestion failed: {e}")
            return ""

    def run_test_coverage(self, module_name: str) -> dict:
        """
        Run pytest with coverage on a specific module.
        Returns coverage report as dict.
        """
        try:
            result = subprocess.run(
                [
                    "pytest",
                    f"--cov={module_name}",
                    "--cov-report=json",
                    "--cov-report=term",
                    str(self._test_dir / f"test_{module_name}.py"),
                    "-v"
                ],
                capture_output=True,
                text=True,
                timeout=120
            )

            coverage_file = Path("coverage.json")
            coverage_data = {}
            if coverage_file.exists():
                coverage_data = json.loads(coverage_file.read_text(encoding="utf-8"))

            return {
                "passed": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "coverage": coverage_data
            }
        except FileNotFoundError:
            logger.error("[VECTOR][test_writer] pytest not installed")
            return {"passed": False, "error": "pytest not found"}
        except subprocess.TimeoutExpired:
            return {"passed": False, "error": "test timeout"}
        except Exception as e:
            logger.error(f"[VECTOR][test_writer] Test run failed: {e}")
            return {"passed": False, "error": str(e)}


    async def _answer_query(self, query: str) -> str:
        """Answer a free-text question directly, grounded in TestWriter's
        role. Used by run() when a real chat message arrives instead of a
        file to write tests for — 2026-07-29 sweep, same bug class as
        #1/#14/#15/#21/#33 (wrong hardcoded default action — a full repo
        scan — instead of the real question). run() is already async, so
        this awaits ProviderClient directly (unlike _get_llm_test_suggestions,
        which needs the thread+asyncio.run workaround because it's called
        from a sync context)."""
        try:
            from core.inference.provider_client import ProviderClient as _PC
            from core.loop.context_engine import ContextEngine
            # RULE 1: session_hydration_prompt() before every LLM call.
            hydration = ContextEngine().session_hydration_prompt({"query": query})
            r = await _PC().chat(
                messages=[
                    {"role": "system", "content": hydration},
                    {"role": "system", "content": (
                        "You are TestWriter, VECTOR's pytest test-generation agent. "
                        "You scan the codebase for untested Python files and write "
                        "pytest unit tests using AST analysis and LLM suggestions. "
                        "Answer the user's question directly and concisely."
                    )},
                    {"role": "user", "content": query},
                ],
                model="domain:coding.generation",
                tier="coding", temperature=0.3, max_tokens=600,
                caller_id="test_writer",
            )
            return r.content
        except Exception as e:
            logger.warning(f"[VECTOR][test_writer] _answer_query failed: {e}")
            return f"Error answering question: {e}"

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        if p.get("file"):
            out = self.write_tests_for_file(p["file"])
            return {"status": "ok", "output": str(out)}

        query = (
            p.get("query") or p.get("content") or task.get("query")
            or task.get("prompt") or ""
        )
        if query.strip():
            answer = await self._answer_query(query)
            return {"status": "ok", "response": answer, "agent": self.name}

        modules = self.scan_for_untested_modules()
        return {"status": "ok", "untested": modules, "count": len(modules)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    writer = TestWriter()

    untested = writer.scan_for_untested_modules()
    print(f"Found {len(untested)} untested modules")

    if untested:
        top_module = untested[0]
        print(f"Writing tests for: {top_module['module_name']}")
        test_path = writer.write_tests_for_file(top_module["file_path"])
        print(f"Test file created: {test_path}")

    print("✅ test_writer.py OK")
