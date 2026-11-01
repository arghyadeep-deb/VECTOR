"""Conservative, syntax-only and count-only checks for explicit HUD deliverables."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from loguru import logger

from core.config import CONFIG

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20,
}
_NUMBER = r"(?:\d+|" + "|".join(_NUMBER_WORDS) + r")"
_FENCE = re.compile(r"^\s*```([^\n`]*)\n(.*?)^\s*```\s*$", re.MULTILINE | re.DOTALL)
_REFUSAL = re.compile(
    r"^(?:Sorry[,!.]?\s*(?:but\s+)?)?"
    r"(?:I (?:can['’]t|cannot|won['’]t|am unable to)|I['’]m unable to) (?:help|assist|provide|write)",
    re.IGNORECASE,
)
# A conservative opt-out: any explicit "don't run/execute" instruction in the
# request disables sandboxed test execution entirely, even when the request
# also declares an exact unittest count. Erring toward skipping execution on
# an ambiguous phrasing is always safe -- the alternative (running anyway) is not.
_NO_EXECUTE = re.compile(
    r"\b(?:do not|don['’]t|never|without)\s+(?:actually\s+)?"
    r"(?:running|executing|run|execute)\b",
    re.IGNORECASE,
)


def _instructions(text: str) -> str:
    text = re.sub(r"```.*?```|`[^`]*`", " ", text, flags=re.DOTALL)
    return re.sub(r'''"[^"\n]*"|“[^”\n]*”|(?<!\w)'[^'\n]+'(?!\w)''', " ", text)


def _integer(value: str) -> int:
    return int(value) if value.isdecimal() else _NUMBER_WORDS[value.lower()]


def _strip_main_guard(source: str) -> str:
    """Drop any top-level ``if __name__ == "__main__":`` block so a single,
    controlled test driver can be appended without double-running the
    candidate's own entry point (which may call ``unittest.main()`` and
    ``sys.exit()`` before our driver ever runs)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    def _is_main_guard(node: ast.stmt) -> bool:
        return (
            isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__"
            and len(node.test.ops) == 1 and isinstance(node.test.ops[0], ast.Eq)
            and len(node.test.comparators) == 1
            and isinstance(node.test.comparators[0], ast.Constant)
            and node.test.comparators[0].value == "__main__"
        )

    tree.body = [node for node in tree.body if not _is_main_guard(node)]
    return ast.unparse(tree)


# Appended once, after every candidate's own `__main__` guard has been
# stripped, so exactly one controlled test run happens regardless of what
# the candidate itself declared.
_TEST_DRIVER_SUFFIX = (
    "\n\nimport unittest as _vector_unittest, sys as _vector_sys\n"
    "_vector_suite = _vector_unittest.TestLoader().loadTestsFromModule("
    "_vector_sys.modules['__main__'])\n"
    "_vector_result = _vector_unittest.TextTestRunner("
    "stream=_vector_sys.stderr, verbosity=2).run(_vector_suite)\n"
    "_vector_sys.exit(0 if _vector_result.wasSuccessful() else 1)\n"
)


def build_test_driver(sources: list[str]) -> str:
    """Combine every validated Python source block into one module and
    append a single controlled unittest run. Only called on sources that
    already parsed/compiled cleanly (see ``OutputContract.failures``)."""
    return "\n\n".join(_strip_main_guard(source) for source in sources) + _TEST_DRIVER_SUFFIX


@dataclass(frozen=True)
class OutputContract:
    python: bool = False
    word_range: tuple[int, int] | None = None
    dialogue_lines: int | None = None
    unittest_tests: int | None = None

    @property
    def active(self) -> bool:
        return self.python or self.word_range is not None or self.dialogue_lines is not None

    def checks_apply(self, answer: str) -> bool:
        return self.active and not _REFUSAL.match(answer.strip())

    def failures(self, answer: str) -> list[str]:
        if not self.checks_apply(answer):
            return []
        max_chars = CONFIG.get("hud_chat", {}).get("max_validation_chars", 120000)
        if len(answer) > max_chars:
            return [f"output exceeds validation limit of {max_chars} characters; validation unavailable"]
        failures = []
        if self.python:
            sources = python_sources(answer)
            syntax_trees = []
            if not sources:
                failures.append("Python syntax: no complete Python code block or source was returned")
            for index, source in enumerate(sources, start=1):
                try:
                    syntax_tree = ast.parse(source)
                    compile(syntax_tree, "<generated>", "exec")
                    syntax_trees.append(syntax_tree)
                except (SyntaxError, ValueError, OverflowError, RecursionError) as error:
                    detail = error.msg if isinstance(error, SyntaxError) else type(error).__name__
                    line = getattr(error, "lineno", None)
                    failures.append(f"Python syntax in block {index}, line {line or '?'}: {detail}")
            if self.unittest_tests is not None and sources and len(syntax_trees) == len(sources):
                count = _unittest_method_count(syntax_trees)
                if count != self.unittest_tests:
                    failures.append(
                        f"unittest test count: {count} declared test methods; required exactly {self.unittest_tests}",
                    )
        if self.word_range is not None:
            count = sum(bool(re.search(r"\w", word)) for word in answer.split())
            lower, upper = self.word_range
            if not lower <= count <= upper:
                failures.append(f"word count: {count} words; required {lower}-{upper}")
        if self.dialogue_lines is not None:
            count = sum(_is_dialogue_line(line) for line in answer.splitlines())
            if count != self.dialogue_lines:
                failures.append(f"dialogue count: {count} dialogue lines; required exactly {self.dialogue_lines}")
        return failures

    def needs_code_review(self, request: str, answer: str) -> bool:
        if not self.python or not self.checks_apply(answer):
            return False
        config = CONFIG.get("hud_chat", {})
        if not config.get("code_review_enabled", True):
            return False
        lines = sum(len(source.splitlines()) for source in python_sources(answer))
        return lines >= config.get("code_review_min_lines", 12) or bool(re.search(
            r"\b(?:streaming|concurrent|concurrency|async|asynchronous|bounded memory|"
            r"edge cases|thread.safe|debug|refactor)\b",
            _instructions(request), re.IGNORECASE,
        ))

    def wants_sandboxed_execution(self, request: str, answer: str) -> bool:
        """Whether this answer's OWN declared unittest tests should actually
        run, in an isolated, network-less container, rather than only being
        syntax-checked. Deliberately narrow: only an explicit "exactly N
        tests" contract (``unittest_tests``) qualifies -- never arbitrary
        generated code with no declared test contract -- and an explicit
        "don't run/execute" instruction anywhere in the original request
        always disables it, even if a test count was also requested."""
        if not self.python or self.unittest_tests is None or not self.checks_apply(answer):
            return False
        if not CONFIG.get("hud_chat", {}).get("sandbox_execution_enabled", True):
            return False
        return not _NO_EXECUTE.search(_instructions(request))

    async def run_sandboxed_tests(self, answer: str, timeout: float | None = None) -> tuple[bool, list[str]]:
        """Actually run the answer's declared unittest tests inside
        ``core.sandbox.vector_sandbox.VectorSandbox`` (network-less container
        when available, warned local-subprocess fallback otherwise). Callers
        must only invoke this after ``failures(answer)`` is already empty
        (valid syntax, matching declared test count) -- this never executes
        code that failed static validation first.

        Returns ``(executed, failures)``. ``executed`` is False whenever the
        sandbox could not actually complete a run (unavailable or timed
        out) -- callers must never claim verification in that case, and a
        timeout/unavailability is deliberately NOT reported as a candidate
        failure (it reflects sandbox infrastructure, not the candidate)."""
        config = CONFIG.get("hud_chat", {})
        budget = timeout if timeout is not None else float(config.get("sandbox_execution_timeout_sec", 20.0))
        if budget <= 0:
            return False, []
        driver = build_test_driver(python_sources(answer))
        try:
            from core.sandbox.vector_sandbox import get_sandbox
            sandbox_result = await get_sandbox().run_python(driver, timeout=budget)
        except Exception as error:
            logger.warning("[VECTOR][output_contracts] sandboxed test execution unavailable: {}", error)
            return False, []
        if sandbox_result.timed_out:
            logger.warning("[VECTOR][output_contracts] sandboxed test run timed out after {:.0f}s", budget)
            return False, []
        if sandbox_result.success:
            return True, []
        detail = (sandbox_result.stderr or sandbox_result.stdout or "").strip()[:2000]
        return True, [f"sandboxed unittest run failed (exit {sandbox_result.exit_code}): {detail}"
                      if detail else f"sandboxed unittest run failed (exit {sandbox_result.exit_code})"]


def _unittest_method_count(syntax_trees: list[ast.Module]) -> int:
    module_names = set()
    base_names = set()
    test_bases = {"TestCase", "IsolatedAsyncioTestCase"}
    classes = {}
    for syntax_tree in syntax_trees:
        for node in syntax_tree.body:
            if isinstance(node, ast.Import):
                module_names.update(alias.asname or alias.name for alias in node.names if alias.name == "unittest")
            elif isinstance(node, ast.ImportFrom) and node.module == "unittest":
                base_names.update(alias.asname or alias.name for alias in node.names if alias.name in test_bases)
            elif isinstance(node, ast.ClassDef):
                classes[node.name] = node
    count = 0
    for node in classes.values():
        is_test_case = any(
            (isinstance(base, ast.Name) and base.id in base_names)
            or (isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name)
                and base.value.id in module_names and base.attr in test_bases)
            for base in node.bases
        )
        if is_test_case:
            count += len({method.name for method in node.body
                          if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                          and method.name.startswith("test_")})
    return count


def _is_dialogue_line(line: str) -> bool:
    line = re.sub(r"^\s*(?:[-*]\s+|\d+[.)]\s+)?", "", line).strip()
    if not line:
        return False
    if re.match(r'''^["“‘']''', line):
        return True
    if re.match(r"^[A-Za-z][\w .'-]{0,60}:\s*\S", line):
        return True
    return bool(re.search(r'''["“][^"”]+["”]''', line))


def python_sources(answer: str) -> list[str]:
    matches = list(_FENCE.finditer(answer))
    if matches:
        sources = [match[2].strip() for match in matches
                   if match[1].strip().lower() in ("", "python", "py", "python3")]
        if answer.count("```") != len(matches) * 2:
            return []
        return [source for source in sources if source]
    if "```" in answer:
        return []
    return [answer.strip()] if answer.strip() else []


def parse_output_contract(request: str, answer: str = "") -> OutputContract:
    instructions = _instructions(request)
    later_deliverable = re.search(
        r"(?:\bthen\b|\band\b|[.!?\n])\s*(?:please\s+)?"
        r"(?:write|generate|implement|provide|produce|create|rewrite|fix|correct|debug|repair|refactor)\b",
        instructions, re.IGNORECASE,
    )
    if re.match(r"^\s*(?:explain|describe|why|what|how)\b", instructions, re.IGNORECASE) and not later_deliverable:
        return OutputContract()
    generation = re.search(
        r"\b(?:write|generate|implement|provide|produce|create|return|rewrite|fix|correct|debug|repair|refactor)\b",
        instructions, re.IGNORECASE,
    )
    python_language = re.search(r"\bpython(?:\s+\d+(?:\.\d+)*)?\b", instructions, re.IGNORECASE)
    python_negated = re.search(
        r"\b(?:not|without|no)\s+(?:using\s+)?python\b|"
        r"\b(?:do not|don['’]t)\s+(?:use|write)\s+python\b", instructions, re.IGNORECASE,
    )
    python_fence = re.search(r"^\s*```(?:python|py|python3)\s*$", answer, re.MULTILINE | re.IGNORECASE)
    code_deliverable = re.search(
        r"\b(?:code|function|program|parser|generator|implementation|script|class)\b", instructions, re.IGNORECASE,
    )
    python = bool(generation and (python_language or python_fence) and code_deliverable and not python_negated)
    creative = bool(not python and re.search(
        r"\b(?:write|generate|compose|create|produce|rewrite)\b[^.!?\n]{0,160}"
        r"\b(?:scene|story|poem|dialogue|fiction|narrative|monologue|vignette)\b",
        instructions, re.IGNORECASE,
    ))
    if not creative:
        exact_tests = re.search(
            rf"\bexactly\s+({_NUMBER})\s+(?:runnable\s+)?"
            r"(?:(?:unittest\s+)?(?:tests?|test\s+cases?)|unittest\s+(?:test[_ ]?)?methods?)\b",
            instructions, re.IGNORECASE,
        ) if python else None
        negated_tests = exact_tests and re.search(
            r"\b(?:do not|don['’]t|not|without|no)\s*(?:(?:include|add|write|provide|generate|create)\s+)?$",
            instructions[:exact_tests.start()], re.IGNORECASE,
        )
        unittest_requested = re.search(r"\bunittest\b", instructions, re.IGNORECASE)
        unittest_candidate = any(re.search(
            r"^\s*(?:import\s+unittest\b|from\s+unittest\s+import\b)", source, re.MULTILINE,
        ) for source in python_sources(answer)) if exact_tests else False
        return OutputContract(
            python=python,
            unittest_tests=(_integer(exact_tests[1]) if exact_tests and not negated_tests
                            and (unittest_requested or unittest_candidate) else None),
        )
    word_range = None
    range_match = re.search(r"\b(\d+)\s*[-–—]\s*(\d+)\s*[- ]?words?\b", instructions, re.IGNORECASE)
    if not range_match:
        range_match = re.search(r"\b(?:between\s+)?(\d+)\s+(?:and|to)\s+(\d+)\s+words?\b", instructions, re.IGNORECASE)
    if range_match:
        lower, upper = map(int, range_match.groups())
        if lower <= upper:
            word_range = (lower, upper)
    else:
        exact = re.search(r"\b(\d+)\s*[- ]\s*words?\b", instructions, re.IGNORECASE)
        approximate = re.search(
            r"\b(?:about|roughly|approximately|around|at least|at most|under|over)\s*$",
            instructions[:exact.start()] if exact else "", re.IGNORECASE,
        )
        if exact and not approximate:
            word_range = (int(exact[1]), int(exact[1]))
    dialogue = re.search(
        rf"\bexactly\s+({_NUMBER})\s+(?:physical\s+)?(?:dialogue[-\s]+lines?|lines?\s+of\s+dialogue)\b",
        instructions, re.IGNORECASE,
    )
    return OutputContract(word_range=word_range,
                          dialogue_lines=_integer(dialogue[1]) if dialogue else None)


if __name__ == "__main__":
    contract = parse_output_contract("Write a scene of 20-30 words with exactly two lines of dialogue.")
    assert contract.failures("Rain fell.") == [
        "word count: 2 words; required 20-30",
        "dialogue count: 0 dialogue lines; required exactly 2",
    ]
    assert OutputContract(python=True).failures("def broken(")
