from __future__ import annotations

from pathlib import Path

from loguru import logger

from core.config import CONFIG
from core.mcp_tools.expansion_modules import resolve_in_root
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.error_handling import register_stub_tool as _reg
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    resolve_memory_path as _resolve_memory_path,
)


_ROOT = Path(__file__).resolve().parents[3]  # module-level so tests can point it at a tmp dir


def add_security_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _ROOT

    # â”€â”€ security_* (10) — wired to districts/security/ and core/security/ â”€â”€â”€â”€â”€
    try:
        @mcp.tool
        def security_scan(path: str) -> str:
            """Scan a file or directory for threats."""
            try:
                import inspect as _inspect
                from districts.security.threat_scout import ThreatScout
                target = resolve_in_root(ROOT, path)
                if target is None:
                    return _safe_json({"ok": False, "error": "Path traversal denied"})
                scout = ThreatScout()
                if not hasattr(scout, "scan_file"):
                    return _safe_json({"ok": False, "error": "scanner unavailable - file NOT scanned"})
                result = scout.scan_file(str(target))
                if _inspect.isawaitable(result):
                    # async scanner: a sync MCP tool cannot await it; never report an unawaited coroutine as a result
                    if hasattr(result, "close"):
                        result.close()
                    return _safe_json({"ok": False, "error": "scanner is async and was not run - file NOT scanned"})
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def security_audit(path: str = ".") -> str:
            """Run a full security assessment."""
            try:
                from districts.security.threat_scout import run_threat_assessment
                result = run_threat_assessment(path)
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def security_validate(text: str) -> str:
            """Validate input against security rules."""
            try:
                from core.security.prompt_injection import get_scanner
                scanner = get_scanner()
                if not hasattr(scanner, "scan"):
                    return _safe_json({"ok": False, "error": "scanner unavailable - input NOT validated"})
                return _safe_json(scanner.scan(text))
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def security_path_check(path: str) -> str:
            """Check if a path is safe (no traversal, within root)."""
            resolved = resolve_in_root(ROOT, path)  # is_relative_to, not str.startswith ("/repo-evil" passes startswith)
            return _safe_json({"path": path, "safe": resolved is not None, "resolved": str(resolved) if resolved else ""})

        @mcp.tool
        def security_threats() -> str:
            """List current detected threats."""
            try:
                from districts.security.threat_scout import scan_running_processes, scan_startup_entries
                procs = scan_running_processes() if callable(scan_running_processes) else []
                startup = scan_startup_entries() if callable(scan_startup_entries) else []
                return _safe_json({"processes": procs, "startup": startup})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def security_report() -> str:
            """Generate a security report."""
            try:
                from districts.security.threat_scout import run_threat_assessment
                result = run_threat_assessment(str(ROOT))
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def security_input_validate(text: str) -> str:
            """Validate tool input for injection patterns."""
            try:
                from core.security.prompt_injection import scan_text
                result = scan_text(text)
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def security_executor_check(command: str) -> str:
            """Check if a command is safe to execute."""
            dangerous = ["rm -rf", "DROP TABLE", "sudo", "curl | bash", "wget | sh", "mkfs", "dd if="]
            is_dangerous = any(d in command for d in dangerous)
            return _safe_json({"command": command, "safe": not is_dangerous, "warnings": ["Contains dangerous pattern"] if is_dangerous else []})

        @mcp.tool
        def security_allowlist() -> str:
            """View the command allowlist from config."""
            try:
                from core.config import CONFIG
                perm = CONFIG.get("permission", {})
                return _safe_json({"green": perm.get("green", []), "yellow": perm.get("yellow", []), "red": perm.get("red", [])})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def security_cve_scan(path: str = ".") -> str:
            """Scan dependencies for known CVEs using pip-audit."""
            try:
                cmd = ["pip-audit", "-f", "json"]
                if path and path != ".":
                    target = resolve_in_root(ROOT, path)
                    if target is None:
                        return _safe_json({"ok": False, "error": "Path traversal denied"})
                    cmd += ["--path", str(target)]
                result = _subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                # pip-audit: 0 = clean, 1 = vulnerabilities found (JSON on stdout), else tool error
                if result.returncode == 0:
                    return _safe_json({"ok": True, "vulnerable": False, "report": result.stdout.strip()})
                if result.returncode == 1 and result.stdout.strip():
                    return _safe_json({"ok": True, "vulnerable": True, "report": result.stdout.strip()})
                return _safe_json({"ok": False, "error": result.stderr.strip() or f"pip-audit exited {result.returncode}"})
            except FileNotFoundError:
                return _safe_json({"status": "pip-audit not installed", "install": "pip install pip-audit"})
            except Exception as e:
                return _safe_json({"error": str(e)})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] security tools unavailable: {e}")
        for n, d in [("security_scan", "Scan for threats"), ("security_audit", "Security audit"), ("security_validate", "Validate input"), ("security_path_check", "Path check"), ("security_threats", "List threats"), ("security_report", "Security report"), ("security_input_validate", "Input validation"), ("security_executor_check", "Executor check"), ("security_allowlist", "View allowlist"), ("security_cve_scan", "CVE scan")]:
            _reg(mcp, n, d)
