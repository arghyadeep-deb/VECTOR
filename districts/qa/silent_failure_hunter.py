"""
Silent Failure Hunter — finds swallowed errors, bad fallbacks, missing error propagation.
Loaded from: vectorcode/agents/vector-silent-failure-hunter.md
District: qa
"""
import asyncio
import ast
import re
from pathlib import Path

from loguru import logger
from core.city.prompt_agent import PromptAgent


class SilentFailureHunter(PromptAgent):
    """
    Zero tolerance for silent failures. Hunts empty except blocks,
    bad fallbacks, swallowed errors, missing async error handling.
    Powered by vector-silent-failure-hunter.md system prompt.
    """

    def __init__(self):
        super().__init__("vector-silent-failure-hunter.md", "silent_failure_hunter_001", "qa")
        self.capabilities = ["file", "qa", "scan", "silent_failure", "test"]

    def scan_python_file(self, filepath: str) -> list[dict]:
        """AST-based scan for silent failure patterns in a Python file."""
        findings = []
        try:
            src = Path(filepath).read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(src)
            lines = src.splitlines()

            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    # Empty except: pass
                    if (len(node.body) == 1 and isinstance(node.body[0], ast.Pass)):
                        findings.append({
                            "line": node.lineno,
                            "severity": "critical",
                            "issue": "Empty except block — exception silently swallowed",
                            "code": lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                            "fix": "Log the exception: logger.error('...', e) or re-raise",
                        })
                    # Bare except (no type)
                    if node.type is None and not (len(node.body) == 1 and isinstance(node.body[0], ast.Pass)):
                        findings.append({
                            "line": node.lineno,
                            "severity": "high",
                            "issue": "Bare except — catches ALL exceptions including SystemExit, KeyboardInterrupt",
                            "code": lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
                            "fix": "Use 'except Exception as e:' — never bare except",
                        })

            # Regex patterns for dangerous fallbacks
            dangerous_patterns = [
                (r"except.*:\s*\n\s*return\s*\[\]\s*$", "high", "Returns empty list on exception — hides real error"),
                (r"except.*:\s*\n\s*return\s*None\s*$", "medium", "Returns None on exception — may cause downstream NullPointerError"),
                (r"except.*:\s*\n\s*return\s*{}\s*$", "medium", "Returns empty dict on exception — hides real error"),
                (r"except.*:\s*\n\s*pass\s*$", "critical", "Exception swallowed with pass — silent failure"),
            ]
            for pattern, severity, issue in dangerous_patterns:
                for m in re.finditer(pattern, src, re.MULTILINE):
                    line_num = src[:m.start()].count("\n") + 1
                    if not any(f["line"] == line_num for f in findings):
                        findings.append({
                            "line": line_num,
                            "severity": severity,
                            "issue": issue,
                            "code": lines[line_num - 1].strip() if line_num <= len(lines) else "",
                            "fix": "Log the exception before returning fallback value",
                        })

        except SyntaxError as e:
            findings.append({"line": 0, "severity": "info", "issue": f"Syntax error in file: {e}", "fix": "Fix syntax first"})
        except Exception as e:
            logger.warning("[VECTOR][sfh] scan error {}: {}", filepath, e)
        return findings

    def scan_directory(self, path: str = ".", max_files: int = 100) -> dict:
        """Scan all Python files in a directory."""
        all_findings = {}
        files_scanned = 0
        for pyfile in sorted(Path(path).rglob("*.py")):
            if "__pycache__" in str(pyfile) or ".git" in str(pyfile):
                continue
            if files_scanned >= max_files:
                break
            findings = self.scan_python_file(str(pyfile))
            if findings:
                rel = str(pyfile.relative_to(Path(path)))
                all_findings[rel] = findings
            files_scanned += 1

        total = sum(len(v) for v in all_findings.values())
        critical = sum(1 for v in all_findings.values() for f in v if f["severity"] == "critical")
        return {
            "files_scanned": files_scanned,
            "files_with_issues": len(all_findings),
            "total_findings": total,
            "critical_count": critical,
            "findings": all_findings,
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
        task_type = task.get("type", "scan")
        try:
            if task_type == "scan":
                result = self.scan_directory(task.get("path", "."), task.get("max_files", 50))
                self.award_points(25 if result["critical_count"] == 0 else 15, "silent_failures_scanned")
                return {"status": "ok", "scan": result}
            elif task_type == "file":
                findings = self.scan_python_file(task.get("filepath", ""))
                self.award_points(15, "file_scanned")
                return {"status": "ok", "findings": findings, "count": len(findings)}
            else:
                return await super().run(task)
        except Exception as e:
            logger.error("[VECTOR][sfh] {}", e)
            self.deduct_points(30, "scan_failed")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")
    async def _smoke():
        agent = SilentFailureHunter()
        print(f"[OK] loaded: {agent.name}")
        result = await agent.run({"type": "scan", "path": ".", "max_files": 10})
        scan = result.get("scan", {})
        print(f"[OK] scan: {scan.get('files_scanned',0)} files, {scan.get('critical_count',0)} critical")
        print("silent_failure_hunter.py OK")
    asyncio.run(_smoke())
