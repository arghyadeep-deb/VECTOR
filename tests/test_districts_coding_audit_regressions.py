from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
MLOPS_ROOT = ROOT / "districts" / "coding" / "vector_mlops"


def _import_backend_auth():
    backend = str(MLOPS_ROOT / "backend")
    agent_root = str(MLOPS_ROOT)
    for entry in (backend, agent_root):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    sys.modules.pop("routes.auth", None)
    return importlib.import_module("routes.auth")


@pytest.mark.asyncio
async def test_oauth_callback_rejects_expired_state_before_token_exchange() -> None:
    auth = _import_backend_auth()
    auth.oauth_states.clear()
    auth.oauth_states["expired-state"] = {
        "redirect_uri": "https://example.test/auth/callback",
        "expires_at": time.time() - 1,
    }

    with pytest.raises(HTTPException, match="Invalid or expired state parameter") as exc:
        await auth.oauth_callback(request=None, code="attacker-code", state="expired-state")

    assert exc.value.status_code == 400
    assert "expired-state" not in auth.oauth_states


def test_session_log_writes_use_durable_atomic_helper() -> None:
    source = (
        MLOPS_ROOT / "agent" / "core" / "session.py"
    ).read_text(encoding="utf-8")

    assert "def _atomic_write_json(" in source
    assert "os.fsync(" in source
    assert "os.replace(" in source
    assert "encoding=\"utf-8\"" in source
    assert "with open(filepath, \"w\")" not in source


def test_mlops_local_file_reads_are_explicit_utf8() -> None:
    source = (
        MLOPS_ROOT / "agent" / "tools" / "local_tools.py"
    ).read_text(encoding="utf-8")

    assert "p.read_text()" not in source
    assert 'p.read_text(encoding="utf-8")' in source


@pytest.mark.parametrize(
    ("relative_path", "secret_name"),
    [
        ("backend/routes/auth.py", "OAUTH_CLIENT_SECRET"),
        ("backend/dependencies.py", "HF_TOKEN"),
        ("backend/session_manager.py", "HF_ADMIN_TOKEN"),
        ("agent/config.py", "SLACK_BOT_TOKEN"),
        ("agent/core/session_persistence.py", "MONGODB_URI"),
        ("agent/tools/github_find_examples.py", "GITHUB_TOKEN"),
        ("agent/tools/github_list_repos.py", "GITHUB_TOKEN"),
        ("agent/tools/github_read_file.py", "GITHUB_TOKEN"),
        ("agent/tools/papers_tool.py", "S2_API_KEY"),
    ],
)
def test_vector_hosted_secrets_use_central_manager(
    relative_path: str, secret_name: str
) -> None:
    source = (MLOPS_ROOT / relative_path).read_text(encoding="utf-8")

    assert f'os.environ.get("{secret_name}"' not in source
    assert f'get_secret("{secret_name}"' in source


def test_sandbox_http_response_cannot_default_to_success() -> None:
    source = (
        MLOPS_ROOT / "agent" / "tools" / "sandbox_client.py"
    ).read_text(encoding="utf-8")

    assert 'success=data.get("success", True)' not in source
    assert 'success=data.get("success") is True' in source


def test_windows_case_insensitive_path_confinement_uses_platform_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from districts.coding import path_security

    monkeypatch.setattr(path_security.os.path, "normcase", lambda value: value.lower())
    root = Path("C:/Vector/Repo")
    candidate = Path("c:/VECTOR/REPO/districts/coding/agent.py")
    outside = Path("c:/VECTOR/REPO-escape/secret.py")

    assert path_security.is_path_within(candidate, root)
    assert not path_security.is_path_within(outside, root)
