from __future__ import annotations

from core.repo_hygiene import audit_repo_paths, classify_repo_path, normalize_repo_path


def test_normalize_repo_path_handles_windows_separators() -> None:
    assert normalize_repo_path(r"frontend\uploads\sample.png") == "frontend/uploads/sample.png"


def test_classify_runtime_artifacts() -> None:
    finding = classify_repo_path("data/security/incidents/demo/evidence.json")

    assert finding is not None
    assert finding.category == "runtime"
    assert finding.severity == "medium"


def test_classify_sensitive_key_material() -> None:
    finding = classify_repo_path("certs/vector.key")

    assert finding is not None
    assert finding.category == "sensitive"
    assert finding.severity == "high"


def test_env_templates_are_allowed_but_real_env_files_are_sensitive() -> None:
    assert classify_repo_path(".env.hardened.example") is None

    finding = classify_repo_path(".env.production")

    assert finding is not None
    assert finding.category == "sensitive"


def test_audit_repo_paths_ignores_source_files() -> None:
    findings = audit_repo_paths(
        [
            "core/runtime/doctor.py",
            "frontend/uploads/local.jpg",
            "README.md",
            ".env.production",
            ".env.hardened.example",
        ]
    )

    assert [finding.path for finding in findings] == [
        ".env.production",
        "frontend/uploads/local.jpg",
    ]
