#!/usr/bin/env python3
"""Run VECTOR's pytest suite in deterministic shards.

The full test suite has enough import/runtime cost that a single pytest
process is not a useful signal on local Windows or CI. This runner keeps the
suite repeatable by using named shards with isolated basetemp directories.
"""
from __future__ import annotations

import argparse
import os
import stat
import time
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
TMP = ROOT / "test_tmp" / "pytest_shards"


def _on_rm_error(func, path, _exc):
    """rmtree onexc handler: clear the read-only bit and retry (Windows).

    Windows refuses os.rmdir/os.remove on read-only files (TLS keys, secret
    fixtures), which otherwise leaves a half-deleted basetemp behind.
    """
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _fresh_basetemp(name: str) -> Path:
    """A unique, repo-local pytest basetemp for one shard for this run.

    Reusing a single fixed `test_tmp/pytest_shards/<name>` across runs caused a
    WinError 5 cascade on Windows: a read-only/locked leftover (TLS keys, secret
    fixtures, open SQLite/WAL handles) from the prior run made pytest's
    start-of-run rmtree of that path fail, leaving it half-deleted so every later
    tmp_path fixture errored at setup with --maxfail=1 aborting the whole shard.
    A unique path per run is never pre-populated, so pytest never deletes a locked
    dir. Stale `<name>_*` dirs are best-effort cleaned with a read-only-aware
    rmtree. (CI on Linux was unaffected; this only ever bit local Windows.)
    """
    TMP.mkdir(parents=True, exist_ok=True)
    for stale in TMP.glob(f"{name}_*"):
        if stale.is_dir():
            shutil.rmtree(stale, onexc=_on_rm_error)
    legacy = TMP / name  # fixed dir from before this fix
    if legacy.exists():
        shutil.rmtree(legacy, onexc=_on_rm_error)
    return TMP / f"{name}_{os.getpid()}_{int(time.time())}"


def _root_files(start: int, end: int) -> list[str]:
    files = sorted(TESTS.glob("test_*.py"))
    return [str(p.relative_to(ROOT)) for p in files[start : end + 1]]


SHARDS: dict[str, list[str]] = {
    "root-00-04": _root_files(0, 4),
    "root-05-09": _root_files(5, 9),
    "root-10-14": _root_files(10, 14),
    "root-15-19": _root_files(15, 19),
    "root-20-29": _root_files(20, 29),
    "root-30-39": _root_files(30, 39),
    "root-40-49": _root_files(40, 49),
    "root-50-59": _root_files(50, 59),
    "root-60-69": _root_files(60, 69),
    "root-70-end": _root_files(70, 999),
    "backend-a": [
        "tests/backend/test_api_contract_imports.py",
        "tests/backend/test_audit_followups.py",
        "tests/backend/test_autonomous_executor.py",
        "tests/backend/test_cloud_deploy_configs.py",
        "tests/backend/test_comms_service_auth.py",
        "tests/backend/test_control_gateway.py",
        "tests/backend/test_district_smoke.py",
        "tests/backend/test_hud_entrypoint.py",
        "tests/backend/test_hud_serving.py",
    ],
    "backend-b": [
        "tests/backend/test_mcp_kernel_secret.py",
        "tests/backend/test_mcp_memory_safety.py",
        "tests/backend/test_memory_concurrency_safety.py",
        "tests/backend/test_memory_quality.py",
        "tests/backend/test_missions.py",
        "tests/backend/test_multi_db_mesh.py",
        "tests/backend/test_phone_node_hardening.py",
        "tests/backend/test_production_honesty.py",
        "tests/backend/test_readiness_tls_and_secrets.py",
        "tests/backend/test_promoted_repo_upgrades.py",
        "tests/backend/test_provider_keys.py",
    ],
    "backend-c": [
        "tests/backend/test_cloud_email_worker_hardening.py",
        "tests/backend/test_quarantine.py",
        "tests/backend/test_read_only_status_endpoints.py",
        "tests/backend/test_repo_analysis_content_research_training.py",
        "tests/backend/test_repo_analysis_optional_boundaries.py",
        "tests/backend/test_repo_analysis_security_and_provider.py",
        "tests/backend/test_repo_analysis_voice_sensing_gateway.py",
        "tests/backend/test_repo_hygiene.py",
        "tests/backend/test_retry_queue.py",
        "tests/backend/test_runtime_doctor.py",
        "tests/backend/test_runtime_tls.py",
        "tests/backend/test_secrets_manager.py",
        "tests/backend/test_social_sim_security.py",
        "tests/backend/test_studio_server_security.py",
        "tests/backend/test_wake_on_lan.py",
        "tests/backend/test_world_snapshot.py",
    ],
    "unit": ["tests/unit"],
    "systems": ["tests/event_bus", "tests/emergency", "tests/resilience", "tests/persona", "tests/personality"],
    "districts": ["tests/districts", "tests/hands", "tests/loop"],
    "research-training-voice": ["tests/research_engine", "tests/training", "tests/voice"],
    "frontend-core": ["tests/frontend", "tests/core"],
    "integration": ["tests/integration"],
}


def run_shard(name: str, extra_pytest_args: list[str]) -> int:
    paths = SHARDS[name]
    if not paths:
        print(f"[skip] {name}: no files")
        return 0
    basetemp = _fresh_basetemp(name)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--maxfail=1",
        f"--basetemp={basetemp}",
        *paths,
        *extra_pytest_args,
    ]
    print(f"\n=== {name} ===")
    print(" ".join(cmd))
    try:
        return subprocess.run(cmd, cwd=ROOT).returncode
    finally:
        if basetemp.exists():
            shutil.rmtree(basetemp, onexc=_on_rm_error)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="List shard names and exit")
    parser.add_argument("--shard", action="append", choices=sorted(SHARDS), help="Shard to run; repeatable")
    parser.add_argument("--continue-on-fail", action="store_true", help="Run remaining shards after a failure")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Extra args after --, passed to pytest")
    args = parser.parse_args()

    if args.list:
        for name in sorted(SHARDS):
            print(name)
        return 0

    selected = args.shard or list(SHARDS)
    extra = args.pytest_args
    if extra and extra[0] == "--":
        extra = extra[1:]

    failures: list[str] = []
    for name in selected:
        rc = run_shard(name, extra)
        if rc != 0:
            failures.append(name)
            if not args.continue_on_fail:
                break

    if failures:
        print("\nFAILED SHARDS: " + ", ".join(failures))
        return 1
    print("\nAll selected shards passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
