import sys
import uuid
import ast
import re
import hashlib
import subprocess
from pathlib import Path
from districts.coding.path_security import is_path_within
from typing import Optional

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase

# Same confinement pattern as districts/coding/code_reviewer.py's/
# architect_bot.py's fixes this cycle: scan_file()/analyze_with_llm() read
# any caller-supplied path with no confinement -- scan_file() is directly
# Governor-dispatchable via run()'s p["file"], and a secret-shaped pattern
# match (SECURITY_PATTERNS) in the scanned file would leak up to 50 chars
# of the match back in the response; analyze_with_llm() (zero real callers
# today, confirmed via repo-wide grep) sends the full file content to a
# cloud LLM provider, same severity as the already-fixed code_reviewer.py
# finding.
_ROOT = Path(__file__).resolve().parents[2]


def _confine_py_path(filepath: str) -> Path:
    """Resolve filepath and require it stay inside the repo root as a .py
    file. Raises FileNotFoundError (the same exception type scan_file()/
    find_pattern_issues()/analyze_with_llm() already raise for a missing
    file) so existing callers' error handling is unaffected."""
    resolved = Path(filepath).resolve()
    if not is_path_within(resolved, _ROOT) or resolved.suffix != ".py":
        raise FileNotFoundError(f"Path outside repo or not a .py file: {filepath}")
    return resolved


class BugHunter(AgentBase):
    """
    Finds bugs in Python code using AST-based static analysis,
    regex pattern matching, and LLM-powered code review via Ollama.
    """

    COMMON_BUG_PATTERNS = [
        (r"except\s*:\s*pass", "Bare except clause - catches all exceptions including SystemExit"),
        (r"except\s+\w+:\s*pass", "Empty except block - silent failure"),
        (r"print\s*\(", "Print statement found - should use logging"),
        (r"eval\s*\(", "Use of eval() - potential code injection risk"),
        (r"exec\s*\(", "Use of exec() - potential code injection risk"),
        (r"os\.system\s*\(", "Use of os.system() - shell injection risk"),
        (r"subprocess\.call\s*\([^,]+shell\s*=\s*True", "Shell=True in subprocess - security risk"),
        (r"\.format\s*\(", "str.format() usage - prefer f-strings or f-strings with safety"),
        (r"\[-0\]", "Negative indexing without bounds check"),
        (r"while\s+True:\s*(?:\s*\n\s*break)*\s*$", "Potential infinite while loop without break"),
        (r"global\s+\w+", "Global variable usage - consider class or module state"),
        (r"from\s+\w+\s+import\s+\*", "Wildcard import - namespace pollution risk"),
        (r"==\s*(?:None|True|False)", "Direct comparison to singleton - use 'is'"),
        (r"if\s+.*\s+==\s+True", "Redundant comparison to True"),
        (r"if\s+len\s*\(\s*\w+\s*\)\s*==\s*0", "Use 'if not iterable' instead of len check"),
        (r"isinstance\s*\([^,]+,\s*bool\)", "Type checking for bool - consider using truthiness"),
        (r"'\w+'\s*\+\s*'\w+'", "String concatenation - use join() for multiple strings"),
        (r"list\s*\(\s*dict\.keys\s*\(\s*\)\s*\)", "Unnecessary list() around dict.keys()"),
        (r"for\s+\w+\s+in\s+range\s*\(\s*len\s*\(\s*\w+\s*\)\s*\):", "Index iteration anti-pattern - use enumerate()"),
        (r"@staticmethod", "Static method without corresponding class usage"),
        (r"raise\s+Exception\s*\(\s*\)", "Generic exception - raise specific exception type"),
    ]

    SECURITY_PATTERNS = [
        (r"password\s*=", "Hardcoded password - use environment variables"),
        (r"api[_-]?key\s*=", "Hardcoded API key - use environment variables"),
        (r"secret\s*=", "Hardcoded secret - use secrets management"),
        (r"token\s*=", "Hardcoded token - use secure storage"),
        (r"\/\*[\s\S]*?\*\/", "Block comment - may contain temporary debug code"),
        (r"TODO|FIXME|HACK|XXX", "TODO/FIXME comment - technical debt marker"),
    ]

    PERFORMANCE_PATTERNS = [
        (r"\.append\s*\(\s*\)", "Empty append - likely unnecessary"),
        (r"\[\s*\w+\s*\]\s*\+\s*\[\s*\w+\s*\]", "List concatenation in loop - use extend()"),
        (r"for\s+\w+\s+in\s+\w+\.keys\s*\(\s*\):", "Explicit .keys() iteration - iterate directly"),
        (r"re\.compile\s*\(\s*\w+\s*\)\s*(?:\n\s*\w+\s*=\s*re\.compile)?", "Regex recompilation - cache compiled patterns"),
    ]

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "BugHunter", "coding")
        # 2026-08-06: governor capability declarations — see architect_bot.py
        self.capabilities = [
            "find_bugs", "debug", "scan_bugs", "bug_scan", "analyze_bugs",
        ]
        if ghost:
            self.inherit_ghost(ghost)
        self._bug_reports: list[dict] = []
        self._scan_history: list[dict] = []
        logger.info("[VECTOR][bug_hunter] BugHunter initialized")
        # Phase 2B: subscribe to coding failure events
        self.subscribe_to("task_failed")
        self.subscribe_to("coding_complete")

    async def handle_event(self, event: dict) -> dict:
        """Phase 2B: React to build/test failures by investigating root cause."""
        await super().handle_event(event)
        et = event.get("event_type", "")
        if et in ("task_failed", "coding_complete"):
            try:
                data = event.get("data", {})
                logger.info(f"[VECTOR][bug_hunter] event-triggered investigation: {et}")
                await self.run({"type": "investigate", "params": {"context": str(data)[:200], "source": "event"}})
            except Exception as e:
                logger.debug(f"[VECTOR][bug_hunter] handle_event failed: {e}")
        return {"status": "handled", "agent": self.name, "event": et}

    def scan_file(self, filepath: str) -> dict:
        """
        Perform AST-based static analysis on a Python file.
        Returns dict with bugs categorized by severity.
        """
        source_path = _confine_py_path(filepath)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {filepath}")

        with open(source_path, "r", encoding="utf-8") as f:
            source_code = f.read()

        bugs = {
            "file": str(source_path),
            "total_lines": len(source_code.splitlines()),
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
            "info": []
        }

        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            bugs["critical"].append({
                "type": "syntax_error",
                "message": f"Syntax error: {e}",
                "line": getattr(e, "lineno", 0)
            })
            return bugs

        bugs["ast_bugs"] = self._analyze_ast(tree, source_code)
        bugs["pattern_bugs"] = self.find_pattern_issues(str(source_path))

        for category in ["critical", "high", "medium", "low", "info"]:
            bugs[category].extend(bugs.get("ast_bugs", {}).get(category, []))
            bugs[category].extend(bugs.get("pattern_bugs", {}).get(category, []))

        bugs["total_bugs"] = sum(len(bugs[c]) for c in ["critical", "high", "medium", "low", "info"])

        self._scan_history.append({
            "file": str(source_path),
            "timestamp": self._get_timestamp(),
            "bug_count": bugs["total_bugs"]
        })

        if bugs["total_bugs"] > 10:
            self.deduct_points(bugs["total_bugs"] * 2, "high_bug_count")
        else:
            self.award_points(max(5 - bugs["total_bugs"], 1), "clean_scan")

        logger.info(f"[VECTOR][bug_hunter] Scanned {source_path.name}: {bugs['total_bugs']} bugs found")
        return bugs

    def _analyze_ast(self, tree: ast.AST, source_code: str) -> dict:
        """Analyze AST for common bug patterns."""
        bugs = {"critical": [], "high": [], "medium": [], "low": [], "info": []}
        lines = source_code.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                bugs["info"].append({
                    "type": "function",
                    "message": f"Function '{node.name}' at line {node.lineno}",
                    "line": node.lineno,
                    "severity": "info"
                })

                if not node.body:
                    bugs["medium"].append({
                        "type": "empty_body",
                        "message": f"Function '{node.name}' has empty body",
                        "line": node.lineno
                    })

                if len(node.args.args) > 7:
                    bugs["low"].append({
                        "type": "too_many_args",
                        "message": f"Function '{node.name}' has {len(node.args.args)} arguments - consider grouping",
                        "line": node.lineno
                    })

            elif isinstance(node, ast.ClassDef):
                if not node.body:
                    bugs["high"].append({
                        "type": "empty_class",
                        "message": f"Class '{node.name}' has empty body",
                        "line": node.lineno
                    })

            elif isinstance(node, ast.Try):
                for handler in node.handlers:
                    if isinstance(handler.type, ast.Name) and handler.type.id == "Exception":
                        if not handler.body or all(isinstance(stmt, ast.Pass) for stmt in handler.body):
                            bugs["high"].append({
                                "type": "silent_exception",
                                "message": f"Empty or bare except at line {handler.lineno}",
                                "line": handler.lineno
                            })

            elif isinstance(node, ast.For):
                if isinstance(node.iter, ast.Call):
                    if isinstance(node.iter.func, ast.Name) and node.iter.func.id == "range":
                        if node.iter.args and isinstance(node.iter.args[0], ast.Constant):
                            if hasattr(node.iter.args[0], 'value') and node.iter.args[0].value < 0:
                                bugs["critical"].append({
                                    "type": "negative_range",
                                    "message": f"Negative range() at line {node.lineno}",
                                    "line": node.lineno
                                })

            elif isinstance(node, ast.While):
                has_break = any(isinstance(n, ast.Break) for n in ast.walk(node))
                if not has_break and not node.body:
                    bugs["critical"].append({
                        "type": "infinite_loop",
                        "message": f"Potential infinite while loop at line {node.lineno}",
                        "line": node.lineno
                    })

        return bugs

    def find_pattern_issues(self, filepath: str) -> dict:
        """
        Use regex patterns to find common bug patterns in source code.
        Returns categorized issues.
        """
        source_path = _confine_py_path(filepath)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {filepath}")

        with open(source_path, "r", encoding="utf-8") as f:
            source_code = f.read()

        issues = {"critical": [], "high": [], "medium": [], "low": [], "info": []}

        for pattern, description in self.COMMON_BUG_PATTERNS:
            matches = re.finditer(pattern, source_code, re.MULTILINE)
            for match in matches:
                line_num = source_code[:match.start()].count('\n') + 1
                severity = self._categorize_bug(description)
                issues[severity].append({
                    "type": "pattern_match",
                    "message": description,
                    "line": line_num,
                    "match": match.group()[:50]
                })

        for pattern, description in self.SECURITY_PATTERNS:
            matches = re.finditer(pattern, source_code, re.MULTILINE | re.IGNORECASE)
            for match in matches:
                line_num = source_code[:match.start()].count('\n') + 1
                issues["critical"].append({
                    "type": "security_issue",
                    "message": description,
                    "line": line_num,
                    "match": match.group()[:50]
                })

        for pattern, description in self.PERFORMANCE_PATTERNS:
            matches = re.finditer(pattern, source_code, re.MULTILINE)
            for match in matches:
                line_num = source_code[:match.start()].count('\n') + 1
                issues["low"].append({
                    "type": "performance",
                    "message": description,
                    "line": line_num,
                    "match": match.group()[:50]
                })

        return issues

    def _categorize_bug(self, description: str) -> str:
        """Categorize bug severity based on description keywords."""
        critical_keywords = ["injection", "security", "shell", "eval", "exec"]
        high_keywords = ["bare except", "empty", "infinite", "silent"]
        medium_keywords = ["print", "global", "format"]

        desc_lower = description.lower()
        if any(kw in desc_lower for kw in critical_keywords):
            return "critical"
        elif any(kw in desc_lower for kw in high_keywords):
            return "high"
        elif any(kw in desc_lower for kw in medium_keywords):
            return "medium"
        return "low"

    def analyze_with_llm(self, filepath: str) -> dict:
        """
        Use Ollama LLM to analyze code for bugs and potential improvements.
        Returns LLM-generated analysis.
        """
        source_path = _confine_py_path(filepath)
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {filepath}")

        with open(source_path, "r", encoding="utf-8") as f:
            source_code = f.read()

        prompt = self._build_analysis_prompt(source_code, source_path.name)

        try:
            import asyncio as _asyncio
            import concurrent.futures as _cf
            from core.inference.provider_client import ProviderClient as _PC

            async def _call():
                from core.prompt_library import get_library as _gl
                _sys = _gl().get_for_agent("bug_hunter") or "You are a security-focused bug hunter. Find vulnerabilities and bugs rigorously."
                r = await _PC().chat(
                    messages=[{"role": "system", "content": _sys}, {"role": "user", "content": prompt}],
                    model="domain:coding.review",   # bug hunting = review-grade scrutiny
                    tier="coding",
                    temperature=0.3,
                    max_tokens=1000,
                    caller_id="bug_hunter",
                )
                return r.content

            with _cf.ThreadPoolExecutor(max_workers=1) as pool:
                analysis = pool.submit(_asyncio.run, _call()).result(timeout=90)

            self._bug_reports.append({
                "file": str(source_path),
                "timestamp": self._get_timestamp(),
                "llm_analysis": analysis,
                "model_used": "provider_client/coding",
            })

            self.award_points(15, "llm_analysis_completed")
            return {"analysis": analysis, "model": "provider_client/coding"}

        except Exception as e:
            logger.error(f"[VECTOR][bug_hunter] LLM analysis failed: {e}")
            return {"error": str(e)}

    def _build_analysis_prompt(self, source_code: str, filename: str) -> str:
        """Build prompt for LLM bug analysis."""
        truncated_code = source_code[:5000] if len(source_code) > 5000 else source_code

        return f"""Analyze the following Python code for bugs, vulnerabilities, and improvements.
Focus on:
1. Logic errors and bugs
2. Security vulnerabilities
3. Error handling issues
4. Performance problems
5. Code quality issues

File: {filename}

```python
{truncated_code}
```

Return a structured analysis in this format:
BUGS:
- [SEVERITY] Line X: Description

SECURITY:
- [CRITICAL/HIGH] Line X: Description

IMPROVEMENTS:
- Line X: Description

OVERALL ASSESSMENT: [score 1-10]
"""

    def report_bugs(self) -> dict:
        """
        Generate a comprehensive bug report from all scanned files.
        Returns structured report.
        """
        report = {
            "generated_at": self._get_timestamp(),
            "total_files_scanned": len(self._scan_history),
            "scan_history": self._scan_history,
            "llm_analyses": self._bug_reports,
            "summary": self._generate_summary()
        }
        return report

    def _generate_summary(self) -> dict:
        """Generate summary statistics from all scans."""
        if not self._scan_history:
            return {"status": "no_scans", "message": "No files have been scanned yet"}

        total_bugs = sum(s["bug_count"] for s in self._scan_history)
        avg_bugs = total_bugs / len(self._scan_history) if self._scan_history else 0

        return {
            "total_bugs_found": total_bugs,
            "average_bugs_per_file": round(avg_bugs, 2),
            "most_bugs_file": max(self._scan_history, key=lambda x: x["bug_count"])["file"]
                if self._scan_history else None,
            "health_score": max(0, 100 - int(avg_bugs * 5))
        }

    def scan_directory(self, directory: str) -> list[dict]:
        """
        Recursively scan all Python files in a directory.
        Returns list of bug reports for each file.
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        results = []
        for py_file in dir_path.rglob("*.py"):
            if "__pycache__" in str(py_file) or "venv" in str(py_file):
                continue

            try:
                bug_report = self.scan_file(str(py_file))
                results.append(bug_report)
            except Exception as e:
                logger.warning(f"[VECTOR][bug_hunter] Failed to scan {py_file}: {e}")

        logger.info(f"[VECTOR][bug_hunter] Directory scan complete: {len(results)} files")
        return results

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    def get_bug_stats(self) -> dict:
        """Get statistics about all detected bugs."""
        if not self._scan_history:
            return {"total_scans": 0, "total_bugs": 0}

        return {
            "total_scans": len(self._scan_history),
            "total_bugs": sum(s["bug_count"] for s in self._scan_history),
            "scans": self._scan_history
        }


    async def _answer_query(self, query: str) -> str:
        """Answer a free-text question directly, grounded in BugHunter's
        role (AST/regex/LLM bug detection). Used by run() when a real chat
        message arrives instead of a file to scan — 2026-07-29 sweep, same
        bug class as #1/#14/#15/#21/#33 (content-free stub instead of the
        real question)."""
        try:
            from core.inference.provider_client import ProviderClient as _PC
            from core.prompt_library import get_library as _gl
            _sys = _gl().get_for_agent("bug_hunter") or (
                "You are BugHunter, VECTOR's static-analysis and LLM-powered bug "
                "detection agent. You scan Python files for logic errors, security "
                "vulnerabilities, silent failures, and performance issues. Answer "
                "the user's question directly and concisely."
            )
            r = await _PC().chat(
                messages=[{"role": "system", "content": _sys}, {"role": "user", "content": query}],
                model="domain:coding.review",
                tier="coding",
                temperature=0.3,
                max_tokens=600,
                caller_id="bug_hunter",
            )
            self.award_points(10, "bug_hunter_qa_answered")
            return r.content
        except Exception as e:
            logger.error(f"[VECTOR][bug_hunter] _answer_query error: {e}")
            return f"Error answering question: {e}"

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        if p.get("file"):
            result = self.scan_file(p["file"])
            return {"status": "ok", **result}

        query = (
            p.get("query") or p.get("content") or task.get("query")
            or task.get("prompt") or ""
        )
        if query.strip():
            answer = await self._answer_query(query)
            return {"status": "ok", "response": answer, "agent": self.name}

        result = self.report_bugs()
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    hunter = BugHunter()

    test_file = Path(__file__)
    bugs = hunter.scan_file(str(test_file))
    print(f"Found {bugs['total_bugs']} bugs in {test_file.name}")

    pattern_issues = hunter.find_pattern_issues(str(test_file))
    print(f"Pattern issues: {sum(len(v) for v in pattern_issues.values())}")

    report = hunter.report_bugs()
    print(f"Health score: {report['summary'].get('health_score', 'N/A')}")

    print("✅ bug_hunter.py OK")
