from __future__ import annotations

import json
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    """These tests assert the documented no-key/localhost dev contract; the owner's
    real .env loads VECTOR_API_KEY and VECTOR_ENV=production into the test process.
    Set the key to "" (not delenv — lazy load_dotenv(override=False) calls during
    app import resurrect a deleted var from .env, but skip one that exists empty)
    and pin VECTOR_ENV=dev so production-only doctor checks (TLS, sidecar health)
    don't apply. Tests that assert production behavior setenv it back explicitly."""
    monkeypatch.setenv("VECTOR_API_KEY", "")
    monkeypatch.setenv("VECTOR_ENV", "dev")


def test_dependency_doctor_required_core_checks_pass(monkeypatch) -> None:
    from core.runtime.doctor import run_dependency_doctor

    monkeypatch.delenv("VECTOR_ENV", raising=False)
    report = run_dependency_doctor(include_optional=False)
    payload = report.to_dict()

    assert payload["required_failed"] == 0
    assert payload["status"] in {"ok", "degraded"}
    names = {check["name"] for check in payload["checks"]}
    assert "python:version" in names
    assert "api:required_routes" in names
    assert "frontend:VECTOR.html" in names
    assert "frontend:demo.js" in names
    assert "frontend:VECTOR.prod.html" not in names


def test_dependency_doctor_classifies_optional_vector_backends(monkeypatch) -> None:
    from core.runtime import doctor as doctor_module

    real_module_exists = doctor_module._module_exists

    def module_exists(module: str) -> bool:
        if module in {"faiss", "colbert"}:
            return False
        return real_module_exists(module)

    monkeypatch.setattr(doctor_module, "_module_exists", module_exists)
    payload = doctor_module.run_dependency_doctor(include_optional=False).to_dict()
    checks = {check["name"]: check for check in payload["checks"]}

    for backend, package in (
        ("faiss_backend", "faiss-cpu"),
        ("colbert_backend", "colbert-ai"),
    ):
        check = checks[f"capability:{backend}"]
        assert check["status"] == "warn"
        assert check["required"] is False
        assert check["capability_status"] == "NEEDS_CONFIG"
        assert package in check["remediation"]


def test_readiness_cli_does_not_emit_optional_backend_tracebacks() -> None:
    proc = subprocess.run(
        [sys.executable, "run_vector.py", "readiness-check"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert proc.returncode == 0, proc.stderr
    output = proc.stdout + proc.stderr
    assert "Traceback" not in output
    assert '"name": "capability:faiss_backend"' in output
    assert '"name": "capability:colbert_backend"' in output


def test_dependency_doctor_marks_production_config_required(monkeypatch) -> None:
    from core.runtime.doctor import run_dependency_doctor

    monkeypatch.setenv("VECTOR_ENV", "production")
    for key in (
        "VECTOR_API_KEY",
        "VECTOR_JWT_SECRET",
        "VECTOR_COMFYUI_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    payload = run_dependency_doctor(include_optional=True).to_dict()
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["status"] == "unready"
    # Count only the checks this test controls via env — sidecar checks (ComfyUI etc.)
    # legitimately pass on machines where the sidecar exists at its default path.
    assert payload["required_failed"] >= 2
    assert checks["env:VECTOR_API_KEY"]["required"] is True
    assert checks["env:VECTOR_API_KEY"]["status"] != "ok"
    assert checks["env:VECTOR_JWT_SECRET"]["required"] is True
    assert checks["env:VECTOR_JWT_SECRET"]["status"] != "ok"
    assert "frontend:production_bundle" not in checks
    assert checks["sidecar:comfyui_path"]["required"] is True
    assert "set VECTOR_API_KEY" in checks["env:VECTOR_API_KEY"]["remediation"]
    assert "VECTOR_COMFYUI_PATH" in checks["sidecar:comfyui_path"]["remediation"]


def test_dependency_doctor_rejects_weak_production_secrets(monkeypatch, tmp_path) -> None:
    from core.runtime.doctor import run_dependency_doctor

    monkeypatch.setenv("VECTOR_ENV", "production")
    monkeypatch.setenv("VECTOR_API_KEY", "short")
    monkeypatch.setenv("VECTOR_JWT_SECRET", "changeme")
    monkeypatch.setenv("VECTOR_COMFYUI_PATH", str(tmp_path))
    monkeypatch.setenv("COMFYUI_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("VECTOR_SIDECARS", "comfyui")  # the owner enabled it, so a dead server is a real failure

    payload = run_dependency_doctor(include_optional=True).to_dict()
    checks = {check["name"]: check for check in payload["checks"]}

    assert payload["status"] == "unready"
    assert checks["env:VECTOR_API_KEY"]["status"] == "fail"
    assert checks["env:VECTOR_JWT_SECRET"]["status"] == "fail"
    assert "generated secret" in checks["env:VECTOR_JWT_SECRET"]["remediation"]
    assert checks["sidecar:comfyui_path"]["status"] == "ok"
    assert checks["sidecar:comfyui_health"]["status"] == "fail"
    assert checks["sidecar:comfyui_health"]["required"] is True


def test_dependency_doctor_accepts_strong_configured_production_inputs_and_certifies_sidecar_health(monkeypatch, tmp_path) -> None:
    from core.runtime.doctor import run_dependency_doctor

    monkeypatch.setenv("VECTOR_ENV", "production")
    monkeypatch.setenv("VECTOR_API_KEY", "v" * 40)
    monkeypatch.setenv("VECTOR_JWT_SECRET", "j" * 64)
    monkeypatch.setenv("VECTOR_COMFYUI_PATH", str(tmp_path))
    monkeypatch.setenv("COMFYUI_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("VECTOR_SIDECARS", "comfyui")  # the owner enabled it, so a dead server is a real failure

    payload = run_dependency_doctor(include_optional=True).to_dict()
    checks = {check["name"]: check for check in payload["checks"]}

    assert checks["env:VECTOR_API_KEY"]["status"] == "ok"
    assert checks["env:VECTOR_JWT_SECRET"]["status"] == "ok"
    assert "frontend:production_bundle" not in checks
    assert checks["sidecar:comfyui_health"]["status"] == "fail"
    assert "start the sidecar service" in checks["sidecar:comfyui_health"]["remediation"]


def test_health_readiness_and_doctor_endpoints_are_available() -> None:
    from core.api.app import create_app

    client = TestClient(create_app(), client=("127.0.0.1", 50000))

    readiness = client.get("/health/readiness")
    assert readiness.status_code == 200
    assert readiness.json()["required_failed"] == 0

    doctor = client.get("/health/doctor")
    assert doctor.status_code == 200
    assert "checks" in doctor.json()


def test_health_hardened_readiness_reports_503_for_missing_hardening(monkeypatch) -> None:
    from core.api.app import create_app

    monkeypatch.delenv("VECTOR_ENV", raising=False)
    for key in (
        "VECTOR_API_KEY",
        "VECTOR_JWT_SECRET",
        "VECTOR_COMFYUI_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    client = TestClient(create_app(), client=("127.0.0.1", 50000))

    response = client.get("/health/hardened-readiness")

    assert response.status_code == 503
    payload = response.json()["detail"]
    assert payload["status"] == "unready"
    assert payload["required_failed"] > 0


def test_run_vector_doctor_cli_returns_json() -> None:
    proc = subprocess.run(
        [sys.executable, "run_vector.py", "doctor"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["required_failed"] == 0
    assert any(check["name"] == "api:required_routes" for check in payload["checks"])


def test_comfyui_health_is_required_only_when_the_owner_enabled_the_sidecar(monkeypatch, tmp_path) -> None:
    """Owner rule 2026-07-16: sidecars are off by default, so a ComfyUI that was never started must not turn the
    hardened readiness report into a 503; when VECTOR_SIDECARS enables it, a dead server is a real failure again."""
    from core.runtime.doctor import run_dependency_doctor

    monkeypatch.setenv("VECTOR_COMFYUI_PATH", str(tmp_path))
    monkeypatch.setenv("COMFYUI_URL", "http://127.0.0.1:1")  # nothing listens here

    def _check(report):
        return next(c for c in report.to_dict()["checks"] if c["name"] == "sidecar:comfyui_health")

    monkeypatch.delenv("VECTOR_SIDECARS", raising=False)
    off = _check(run_dependency_doctor(include_optional=True, hardened=True))
    assert off["status"] != "ok" and off["required"] is False

    monkeypatch.setenv("VECTOR_SIDECARS", "comfyui")
    on = _check(run_dependency_doctor(include_optional=True, hardened=True))
    assert on["status"] != "ok" and on["required"] is True
