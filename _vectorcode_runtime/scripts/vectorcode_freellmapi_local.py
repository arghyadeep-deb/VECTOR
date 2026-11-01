"""Start the owner's loopback FreeLLMAPI install without putting secrets in command arguments."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import keyring
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

VAULT_SERVICE = "vectorcode.freellmapi.local"
DASHBOARD_USER = "vectorcode@localhost.local"
ORIGIN = "http://127.0.0.1:3001"


def saved_secret(name: str, size: int = 32) -> str:
    value = keyring.get_password(VAULT_SERVICE, name)
    if not value:
        value = secrets.token_hex(size)
        keyring.set_password(VAULT_SERVICE, name, value)
    return value


def run(args) -> dict:
    from vectorcode.src.cli.auth import AuthManager

    state_dir = Path(os.environ["LOCALAPPDATA"]) / "VectorCode" / "FreeLLMAPI"
    state_dir.mkdir(parents=True, exist_ok=True)
    profile_file = state_dir / "profile.json"
    profile = json.loads(profile_file.read_text()) if profile_file.exists() else {}
    repo = Path(args.router_repo or profile.get("repo", "")).resolve()
    if not (repo / "server/dist/index.js").is_file():
        raise RuntimeError("Pass --router-repo pointing to the built FreeLLMAPI repository.")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is not installed.")
    password = saved_secret("dashboard-password")
    if args.copy_password:
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        subprocess.run(
            [str(powershell), "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
            input=password, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return {"password_copied": True, "dashboard_user": DASHBOARD_USER}
    local_model = args.local_model or profile.get("local_model")
    with httpx.Client(timeout=15, trust_env=False) as client:
        try:
            status = client.get(ORIGIN + "/api/auth/status")
            status.raise_for_status()
            if not profile_file.exists():
                raise RuntimeError("Port 3001 already has a server; refusing to configure an unowned install.")
        except httpx.ConnectError:
            config = {"admin": {"email": DASHBOARD_USER, "password": password}}
            if local_model:
                config["customProviders"] = [{
                    "baseUrl": "http://127.0.0.1:11434/v1",
                    "apiKey": "ollama",
                    "label": "VECTOR local Ollama (verification; not cloud capacity)",
                    "models": [{"model": local_model, "supportsTools": True, "contextWindow": 8192}],
                }]
            env = dict(os.environ)
            env.update({
                "HOST": "127.0.0.1", "PORT": "3001", "NODE_ENV": "production",
                "ENCRYPTION_KEY": saved_secret("encryption-key"),
                "FREEAPI_DB_PATH": str(state_dir / "freeapi.db"),
                "FREEAPI_DB_DIR_HARDENING": "1",
                "FREEAPI_CONFIG_JSON": json.dumps(config),
                "ALLOWED_HOSTS": "localhost,127.0.0.1",
            })
            with (state_dir / "server.log").open("ab") as output:
                process = subprocess.Popen(
                    [node, str(repo / "server/dist/index.js")], cwd=repo, env=env,
                    stdout=output, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            profile = {"repo": str(repo), "pid": process.pid, "local_model": local_model,
                       "dashboard_user": DASHBOARD_USER, "origin": ORIGIN}
            profile_file.write_text(json.dumps(profile, indent=2), encoding="utf-8")
            deadline = time.monotonic() + 30
            while True:
                if process.poll() is not None:
                    raise RuntimeError("FreeLLMAPI exited; inspect its local server.log.")
                try:
                    status = client.get(ORIGIN + "/api/auth/status")
                    if status.status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("FreeLLMAPI did not become ready within 30 seconds.")
                time.sleep(0.25)
        login = client.post(ORIGIN + "/api/auth/login", json={"email": DASHBOARD_USER, "password": password})
        if login.status_code != 200:
            raise RuntimeError("Dashboard login failed; the local account needs owner attention.")
        token = login.json()["token"]
        response = client.get(ORIGIN + "/api/settings/api-key", headers={"Authorization": f"Bearer {token}"})
        response.raise_for_status()
        unified_key = response.json()["apiKey"]
        AuthManager().add("freellmapi", "freellmapi", unified_key, require_keyring=True)
        client.post(ORIGIN + "/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    return {"running": True, "origin": ORIGIN, "pid": profile.get("pid"),
            "key_saved_to_keyring": True, "dashboard_user": DASHBOARD_USER, "local_model": local_model}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--router-repo", help="Built FreeLLMAPI checkout; remembered after first launch")
    parser.add_argument("--local-model", help="Optional installed Ollama model for gateway verification")
    parser.add_argument("--copy-password", action="store_true", help="Copy the local dashboard password to clipboard")
    args = parser.parse_args()
    try:
        logger.info("{}", json.dumps(run(args)))
    except Exception as exc:
        logger.error("FreeLLMAPI setup failed ({}). Inspect the local server log; no secrets were printed.",
                     type(exc).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
