from __future__ import annotations

import json
import subprocess
import sys

from fastapi.testclient import TestClient


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
    assert "frontend:VECTOR.prod.html" in names


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
    assert payload["required_failed"] >= 4
    assert checks["env:VECTOR_API_KEY"]["required"] is True
    assert checks["env:VECTOR_JWT_SECRET"]["required"] is True
    assert checks["frontend:production_bundle"]["required"] is True
    assert checks["frontend:production_bundle"]["status"] == "ok"
    assert checks["sidecar:comfyui_path"]["required"] is True
    assert "set VECTOR_API_KEY" in checks["env:VECTOR_API_KEY"]["remediation"]
    assert "VECTOR_COMFYUI_PATH" in checks["sidecar:comfyui_path"]["remediation"]


def test_dependency_doctor_rejects_weak_production_secrets(monkeypatch, tmp_path) -> None:
    from core.runtime.doctor import run_dependency_doctor

    monkeypatch.setenv("VECTOR_ENV", "production")
    monkeypatch.setenv("VECTOR_API_KEY", "short")
    monkeypatch.setenv("VECTOR_JWT_SECRET", "changeme")
    monkeypatch.setenv("VECTOR_COMFYUI_PATH", str(tmp_path))
    monkeypatch.setenv("VECTOR_LIBRECHAT_PATH", str(tmp_path))
    monkeypatch.setenv("COMFYUI_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("LIBRECHAT_URL", "http://127.0.0.1:9")

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
    monkeypatch.setenv("VECTOR_LIBRECHAT_PATH", str(tmp_path))
    monkeypatch.setenv("COMFYUI_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("LIBRECHAT_URL", "http://127.0.0.1:9")

    payload = run_dependency_doctor(include_optional=True).to_dict()
    checks = {check["name"]: check for check in payload["checks"]}

    assert checks["env:VECTOR_API_KEY"]["status"] == "ok"
    assert checks["env:VECTOR_JWT_SECRET"]["status"] == "ok"
    assert checks["frontend:production_bundle"]["status"] == "ok"
    assert checks["sidecar:comfyui_health"]["status"] == "fail"
    assert checks["sidecar:librechat_health"]["status"] == "fail"
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


def test_health_production_readiness_reports_503_for_missing_hardening(monkeypatch) -> None:
    from core.api.app import create_app

    monkeypatch.delenv("VECTOR_ENV", raising=False)
    for key in (
        "VECTOR_API_KEY",
        "VECTOR_JWT_SECRET",
        "VECTOR_COMFYUI_PATH",
        "VECTOR_LIBRECHAT_PATH",
    ):
        monkeypatch.delenv(key, raising=False)

    client = TestClient(create_app(), client=("127.0.0.1", 50000))

    response = client.get("/health/production-readiness")

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
