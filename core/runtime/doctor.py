from __future__ import annotations

import importlib.util
import os
import platform
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from core.runtime_paths import get_data_root


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class DependencyCheck:
    name: str
    status: str
    required: bool
    detail: str = ""
    remediation: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass
class DoctorReport:
    status: str
    required_failed: int
    warnings: int
    checks: list[DependencyCheck]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["checks"] = [asdict(check) for check in self.checks]
        return data


def _check(
    name: str,
    ok: bool,
    required: bool,
    detail: str = "",
    remediation: str = "",
) -> DependencyCheck:
    if ok:
        return DependencyCheck(name=name, status="ok", required=required, detail=detail)
    return DependencyCheck(
        name=name,
        status="fail" if required else "warn",
        required=required,
        detail=detail,
        remediation=remediation,
    )


def _module_exists(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _sidecar_enabled(name: str) -> bool:
    """Whether the owner has switched a sidecar on. Owner rule (2026-07-16, run_vector._start_sidecars): no extra localhost
    servers by default; VECTOR_SIDECARS=1|all enables everything, or a comma list of names."""
    val = os.environ.get("VECTOR_SIDECARS", "").strip().lower()
    if val in ("", "0", "off", "false", "none"):
        return False
    return val in ("1", "all", "true", "on") or name.lower() in {t.strip() for t in val.split(",")}


def _is_hardened_env() -> bool:
    return os.environ.get("VECTOR_ENV", "").strip().lower() in {"prod", "production", "vector"}


def _sqlcipher_available() -> bool:
    return _module_exists("sqlcipher3") or _module_exists("pysqlcipher3")


def _check_modules(modules: Iterable[tuple[str, bool]]) -> list[DependencyCheck]:
    checks: list[DependencyCheck] = []
    for module, required in modules:
        exists = _module_exists(module)
        checks.append(
            _check(
                f"python_module:{module}",
                exists,
                required,
                "importable" if exists else "not installed",
            )
        )
    return checks


def _check_writable_dir(path: Path, name: str, required: bool = True) -> DependencyCheck:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="vector_doctor_", dir=path, delete=True) as handle:
            handle.write(b"ok")
        return _check(name, True, required, str(path))
    except Exception as exc:
        return _check(name, False, required, f"{path}: {exc}")


def _check_file(path: Path, name: str, required: bool = True) -> DependencyCheck:
    return _check(name, path.exists() and path.is_file(), required, str(path))


def _check_dir(path: Path, name: str, required: bool = True) -> DependencyCheck:
    return _check(name, path.exists() and path.is_dir(), required, str(path))


def _check_env_secret(
    name: str,
    required: bool = False,
    min_length: int = 32,
) -> DependencyCheck:
    value = os.environ.get(name, "").strip()
    if not value:
        return _check(
            f"env:{name}",
            False,
            required,
            "not configured",
            f"set {name} to at least {min_length} random characters in your production environment",
        )

    weak_values = {"changeme", "change-me", "change_me", "secret", "password", "test"}
    if required and (len(value) < min_length or value.lower() in weak_values):
        return _check(
            f"env:{name}",
            False,
            True,
            f"configured but too weak for production; use at least {min_length} random characters",
            f"replace {name} with a generated secret, for example: python -c \"import secrets; print(secrets.token_urlsafe(48))\"",
        )

    if len(value) < min_length:
        return _check(
            f"env:{name}",
            False,
            False,
            f"configured but short; use at least {min_length} random characters for production",
            f"rotate {name} before production; target at least {min_length} random characters",
        )

    return _check(f"env:{name}", True, required, "configured")


def _check_env_dir(name: str, env_name: str, required: bool) -> DependencyCheck:
    raw = os.environ.get(env_name, "").strip()
    if not raw:
        return _check(
            name,
            False,
            required,
            f"set {env_name} to an existing directory",
            f"install/configure the sidecar and set {env_name} to its local directory",
        )
    path = Path(raw).expanduser()
    return _check(
        name,
        path.exists() and path.is_dir(),
        required,
        str(path),
        f"create the directory or correct {env_name}; current value does not resolve to a directory",
    )


def _join_url(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def _check_local_http_service(
    name: str,
    url: str,
    required: bool,
    timeout: float = 0.75,
) -> DependencyCheck:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return _check(
            name,
            False,
            required,
            f"not checked because {url} is not a loopback URL",
            "keep production sidecar health checks on loopback/private service URLs or certify them separately",
        )

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VECTOR-doctor/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            code = getattr(response, "status", 200)
        return _check(name, code < 500, required, f"{url} -> HTTP {code}")
    except urllib.error.HTTPError as exc:
        return _check(name, exc.code < 500, required, f"{url} -> HTTP {exc.code}")
    except Exception as exc:
        return _check(
            name,
            False,
            required,
            f"{url} unreachable: {exc}",
            "start the sidecar service or correct its URL before production use",
        )


def run_dependency_doctor(
    include_optional: bool = True,
    hardened: bool | None = None,
) -> DoctorReport:
    """Run offline-safe runtime checks for local VECTOR readiness."""
    hardened_mode = _is_hardened_env() if hardened is None else bool(hardened)
    checks: list[DependencyCheck] = []

    checks.append(
        _check(
            "python:version",
            sys.version_info >= (3, 11),
            True,
            f"{platform.python_version()} on {platform.system()}",
        )
    )

    checks.extend(
        _check_modules(
            [
                ("fastapi", True),
                ("pydantic", True),
                ("loguru", True),
                ("httpx", True),
                ("psutil", True),
                ("uvicorn", False),
                ("sqlcipher3", False),
                ("torch", False),
                ("playwright", False),
            ]
        )
    )
    if hardened_mode and not _sqlcipher_available():
        checks.append(
            _check(
                "memory:encrypted_driver",
                False,
                True,
                "install sqlcipher3 or pysqlcipher3 before production use",
                "run: python -m pip install sqlcipher3; if unavailable on this platform, install pysqlcipher3 with native SQLCipher build tools",
            )
        )
    elif _sqlcipher_available():
        checks.append(
            _check(
                "memory:encrypted_driver",
                True,
                hardened_mode,
                "SQLCipher driver available",
            )
        )

    checks.append(_check_writable_dir(get_data_root(), "data_root:writable", True))
    checks.append(_check_writable_dir(PROJECT_ROOT / "test_tmp", "test_tmp:writable", False))

    frontend_html = PROJECT_ROOT / "frontend" / "VECTOR.html"
    # The subsystem dock is built by demo.js, so the one HUD needs it in every environment.
    demo_script = PROJECT_ROOT / "frontend" / "js" / "demo.js"
    checks.extend(
        [
            _check_file(PROJECT_ROOT / "run_vector.py", "launcher:run_vector.py", True),
            _check_file(frontend_html, "frontend:VECTOR.html", True),
            _check_file(PROJECT_ROOT / "frontend" / "js" / "widgets.js", "frontend:widgets.js", True),
            _check_file(demo_script, "frontend:demo.js", True),
            _check_dir(PROJECT_ROOT / "core" / "api" / "routers", "api:routers", True),
            _check_dir(PROJECT_ROOT / "districts", "districts", True),
        ]
    )

    try:
        from core.api.app import create_app

        app = create_app()
        routes = {getattr(route, "path", "") for route in app.routes}
        required_routes = {
            "/status",
            "/health/status",
            "/health/system",
            "/gateway/pending",
            "/hud/",
            "/voice/status",
        }
        missing = sorted(required_routes - routes)
        checks.append(
            _check(
                "api:required_routes",
                not missing,
                True,
                "all required routes mounted" if not missing else "missing: " + ", ".join(missing),
            )
        )
    except Exception as exc:
        checks.append(_check("api:create_app", False, True, str(exc)))

    checks.extend(
        [
            _check_env_secret("VECTOR_API_KEY", hardened_mode),
            _check_env_secret("VECTOR_JWT_SECRET", hardened_mode, min_length=48),
            # Stable MCP stdio signing secret — required in production so signed
            # requests survive restarts (see core/mcp_server_stdio.py).
            _check_env_secret("MCP_KERNEL_SECRET", hardened_mode),
        ]
    )

    if include_optional:
        optional_paths = [
            ("sidecar:comfyui_path", "VECTOR_COMFYUI_PATH"),
        ]
        sidecar_path_checks: dict[str, DependencyCheck] = {}
        for name, env_name in optional_paths:
            check = _check_env_dir(name, env_name, hardened_mode)
            sidecar_path_checks[name] = check
            checks.append(check)

        if sidecar_path_checks.get("sidecar:comfyui_path", DependencyCheck("", "fail", False)).ok:
            comfyui_base = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").strip()
            checks.append(
                _check_local_http_service(
                    "sidecar:comfyui_health",
                    _join_url(comfyui_base, "/system_stats"),
                    # A server the owner has deliberately not started must not make the whole readiness report 503;
                    # it is still reported (as a warning) when its path is configured but it is not running.
                    hardened_mode and _sidecar_enabled("comfyui"),
                )
            )


    required_failed = sum(1 for check in checks if check.required and not check.ok)
    warnings = sum(1 for check in checks if not check.required and not check.ok)
    status = "ok" if required_failed == 0 else "unready"
    if status == "ok" and warnings:
        status = "degraded"

    return DoctorReport(
        status=status,
        required_failed=required_failed,
        warnings=warnings,
        checks=checks,
    )
