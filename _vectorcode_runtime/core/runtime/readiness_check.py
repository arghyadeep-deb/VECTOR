"""Production readiness checks for the local VECTOR launcher."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]

_PLACEHOLDER_SECRETS = {
    "your-global-hmac-secret",
    "your-global-secret",
    "your-webhook-secret",
    "generate-a-strong-secret-here",
    "change-me",
    "changeme",
}

_PY_SCAN_ROOTS = ("core", "districts", "vectorcode/src")
_CONFIG_GLOBS = ("*.env", ".env", "*.yaml", "*.yml", "*.toml", "*.json")
_SKIP_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "skills",
    "evals",
    "tests",
    "training",
    "training_runs",
}
_DYNAMIC_EXEC_ALLOWLIST = (
    "repl.py",
    "code_interpreter",
    "templates/loader.py",
    "tools/skills_guard.py",
    "vc_core/config.py",
)
_DYNAMIC_EXEC_GATED_MARKER = "require_dynamic_strategy_execution"


@dataclass
class Check:
    name: str
    status: str
    detail: str
    evidence: Any = None

    def to_dict(self) -> dict[str, Any]:
        data = {"name": self.name, "status": self.status, "detail": self.detail}
        if self.evidence is not None:
            data["evidence"] = self.evidence
        return data


def _is_hardened() -> bool:
    return os.environ.get("VECTOR_ENV", "").strip().lower() in {"prod", "production", "vector"}


def _iter_repo_files() -> list[Path]:
    files: list[Path] = []
    for pattern in _CONFIG_GLOBS:
        files.extend(REPO_ROOT.glob(pattern))
    config_dir = REPO_ROOT / "config"
    if config_dir.exists():
        for pattern in _CONFIG_GLOBS:
            files.extend(config_dir.rglob(pattern))
    return sorted({path for path in files if path.is_file()})


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _scan_config_placeholders() -> Check:
    hits: list[str] = []
    for path in _iter_repo_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        if any(secret in text for secret in _PLACEHOLDER_SECRETS):
            hits.append(_relative(path))
    if hits:
        return Check(
            "runtime_secret_placeholders",
            "fail",
            "Runtime config contains placeholder webhook/API secrets.",
            hits[:20],
        )
    return Check("runtime_secret_placeholders", "ok", "No placeholder secrets found in runtime config files.")


def _is_skipped(path: Path) -> bool:
    return any(part in _SKIP_PARTS for part in path.parts)


def _is_dynamic_exec_allowed(path: Path) -> bool:
    rel = _relative(path).replace("\\", "/")
    return any(marker in rel for marker in _DYNAMIC_EXEC_ALLOWLIST)


def _scan_dynamic_exec() -> Check:
    hits: list[str] = []
    for root_name in _PY_SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if _is_skipped(path) or _is_dynamic_exec_allowed(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if _DYNAMIC_EXEC_GATED_MARKER in text:
                    continue
                tree = ast.parse(text)
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id in {"eval", "exec"}:
                        hits.append(f"{_relative(path)}:{node.lineno}:{node.func.id}")
    if hits:
        return Check(
            "dynamic_exec_surface",
            "warn",
            "eval/exec calls remain outside the known REPL/eval allowlist.",
            hits[:30],
        )
    return Check("dynamic_exec_surface", "ok", "No eval/exec calls found outside the allowlist.")


def _check_dependencies() -> Check:
    try:
        from core.runtime.doctor import run_dependency_doctor

        report = run_dependency_doctor(include_optional=False).to_dict()
    except Exception as exc:
        return Check("required_dependencies", "fail", f"Dependency doctor failed to run: {exc}")
    failed = int(report.get("required_failed", 0) or 0)
    if failed:
        return Check(
            "required_dependencies",
            "fail",
            f"{failed} required dependency check(s) failed.",
            report,
        )
    return Check("required_dependencies", "ok", "Required dependency checks passed.", report)


def _check_memory_encryption() -> Check:
    try:
        from core.memory.episodic import _USE_SQLCIPHER
    except Exception as exc:
        return Check("memory_encryption", "fail", f"Memory encryption status unavailable: {exc}")
    if _USE_SQLCIPHER:
        detail = "SQLCipher is available for the shared memory database."
        if not os.environ.get("VECTOR_DB_KEY"):
            detail += " VECTOR_DB_KEY is not set; startup will rely on OS keyring."
        return Check("memory_encryption", "ok", detail)
    return Check(
        "memory_encryption",
        "warn",
        "SQLCipher is not installed; shared memory falls back to plain SQLite.",
    )


def _check_memory_db_open() -> Check:
    try:
        from core.memory.episodic import diagnose_memory_db

        report = diagnose_memory_db()
    except Exception as exc:
        return Check("memory_db_open", "fail", f"Memory DB diagnostic failed: {exc}")
    if report.get("can_open") or report.get("status") == "missing":
        return Check("memory_db_open", "ok", report.get("detail", "Memory DB is available."), report)
    if report.get("status") == "plaintext_migration_needed":
        return Check("memory_db_open", "warn", report.get("detail", "Memory DB needs migration."), report)
    return Check("memory_db_open", "fail", report.get("detail", "Memory DB is unavailable."), report)


def _check_launch_secrets() -> Check:
    secret = os.environ.get("MCP_KERNEL_SECRET", "")
    if len(secret) >= 32:
        return Check("mcp_kernel_secret", "ok", "MCP_KERNEL_SECRET is set with production-length entropy.")
    status = "fail" if _is_hardened() else "warn"
    return Check(
        "mcp_kernel_secret",
        status,
        "MCP_KERNEL_SECRET is unset or shorter than 32 characters.",
    )


def _check_secret_manager() -> Check:
    required = {
        "VECTOR_API_KEY": 32,
        "MCP_KERNEL_SECRET": 32,
    }
    optional = {
        "VECTOR_JWT_SECRET": 48,
    }
    try:
        from core.security.secrets_manager import audit_secret
    except Exception as exc:
        return Check("secret_manager", "fail", f"Secret manager unavailable: {exc}")

    audits = {
        name: audit_secret(name, min_length=min_length).to_dict()
        for name, min_length in {**required, **optional}.items()
    }
    missing = [
        name for name in required
        if not audits[name]["configured"]
    ]
    weak = [
        name for name in required
        if audits[name]["configured"] and not audits[name]["strong"]
    ]
    optional_missing = [
        name for name in optional
        if not audits[name]["configured"]
    ]
    evidence = {
        "missing": missing,
        "weak": weak,
        "optional_missing": optional_missing,
        "audits": audits,
    }
    if missing or weak:
        status = "fail" if _is_hardened() else "warn"
        return Check(
            "secret_manager",
            status,
            "Required launch secrets are missing or weak.",
            evidence,
        )
    if optional_missing:
        return Check("secret_manager", "warn", "Optional production secrets are not configured.", evidence)
    return Check("secret_manager", "ok", "Runtime secrets are configured.", evidence)


def _check_tls_config() -> Check:
    try:
        from core.runtime.tls import load_tls_config

        config = load_tls_config()
    except Exception as exc:
        return Check("api_tls", "fail", f"TLS configuration check failed: {exc}")

    evidence = {
        "enabled": config.enabled,
        "terminated": config.terminated,
        "certfile_configured": bool(config.certfile),
        "keyfile_configured": bool(config.keyfile),
        "ca_certs_configured": bool(config.ca_certs),
    }
    if config.enabled:
        return Check("api_tls", "ok", config.detail, evidence)
    if config.terminated:
        return Check("api_tls", "ok", config.detail, evidence)
    status = "fail" if _is_hardened() else "warn"
    return Check("api_tls", status, config.detail, evidence)


def _check_agent_manifest() -> Check:
    """Verify the canonical manifest has no empty or duplicate entries."""
    try:
        from core.runtime.manifest_inventory import load_manifest_inventory

        inventory = load_manifest_inventory()
    except Exception as exc:
        return Check("agent_manifest", "fail", f"Agent manifest could not be loaded: {exc}")

    problems = []
    if inventory["agent_count"] <= 0:
        problems.append("no agents")
    if inventory["district_count"] <= 0:
        problems.append("no districts")
    if inventory["empty_districts"]:
        problems.append(f"empty districts: {inventory['empty_districts']}")
    if inventory["duplicate_agent_names"]:
        problems.append(f"duplicate agents: {inventory['duplicate_agent_names']}")
    if problems:
        return Check("agent_manifest", "fail", "; ".join(problems), inventory)
    return Check(
        "agent_manifest",
        "ok",
        f"{inventory['agent_count']} agents across {inventory['district_count']} districts.",
        inventory,
    )


def run_readiness_check() -> dict[str, Any]:
    checks = [
        _check_agent_manifest(),
        _check_dependencies(),
        _check_memory_encryption(),
        _check_memory_db_open(),
        _check_launch_secrets(),
        _check_secret_manager(),
        _check_tls_config(),
        _scan_config_placeholders(),
        _scan_dynamic_exec(),
    ]
    failed = sum(1 for check in checks if check.status == "fail")
    warned = sum(1 for check in checks if check.status == "warn")
    status = "fail" if failed else "warn" if warned else "ok"
    return {
        "status": status,
        "hardened_env": _is_hardened(),
        "summary": {"failed": failed, "warned": warned, "passed": len(checks) - failed - warned},
        "checks": [check.to_dict() for check in checks],
    }
