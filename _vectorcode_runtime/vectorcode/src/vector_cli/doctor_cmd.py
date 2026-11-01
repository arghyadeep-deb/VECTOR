"""VECTOR doctor — comprehensive health check.

One command that verifies every part of VECTOR is wired and ready:

    python -m vectorcode.src.vector_cli.doctor_cmd
    python -m vectorcode.src.vector_cli.doctor_cmd --json
    python -m vectorcode.src.vector_cli.doctor_cmd --fix    # auto-fix common issues

Checks performed:
  • Python version
  • Required Python packages (loguru, ollama, fastapi, etc.)
  • Ollama daemon reachable + parallel-load env vars set
  • GPU detected (NVIDIA / AMD / Apple)
  • Telemetry capabilities (energy_monitor, gpu_monitor, flops, etc.)
  • Skill registry populated
  • Agent registry populated
  • Hook registry populated
  • Slash commands loaded
  • SSL certs present
  • Vector memory DB writable
  • Obsidian vault reachable (if configured)
  • Required Ollama models pulled
  • Telemetry DB schema migrated
  • Disk space available
"""
from __future__ import annotations
from loguru import logger

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Color codes (no external dep)
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

# Status glyphs (works in Windows Terminal w/ UTF-8)
OK_MARK = "✓"
WARN_MARK = "⚠"
FAIL_MARK = "✗"
INFO_MARK = "ℹ"


@dataclass
class CheckResult:
    name: str
    status: str  # "ok" | "warn" | "fail" | "info"
    message: str
    detail: str = ""
    fix_hint: str = ""


# Repo root — assumed to be 4 levels up from this file (vectorcode/src/vector_cli/doctor_cmd.py)
ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _emit(r: CheckResult, plain: bool = False) -> None:
    if plain:
        print(f"[{r.status.upper():>4}] {r.name:<32}  {r.message}")
        if r.detail:
            print(f"         {r.detail}")
        return
    icon, color = {
        "ok":   (OK_MARK,   GREEN),
        "warn": (WARN_MARK, YELLOW),
        "fail": (FAIL_MARK, RED),
        "info": (INFO_MARK, DIM),
    }.get(r.status, ("?", DIM))
    print(f"  {color}{icon}{RESET}  {BOLD}{r.name:<32}{RESET}  {r.message}")
    if r.detail:
        print(f"     {DIM}{r.detail}{RESET}")
    if r.fix_hint and r.status in ("warn", "fail"):
        print(f"     {YELLOW}fix:{RESET} {r.fix_hint}")


# ── Individual checks ────────────────────────────────────────────────────────


def check_python() -> CheckResult:
    v = sys.version_info
    if v >= (3, 11):
        return CheckResult("Python", "ok", f"{v.major}.{v.minor}.{v.micro}")
    return CheckResult(
        "Python", "fail", f"{v.major}.{v.minor} (need ≥ 3.11)",
        fix_hint="upgrade Python; `winget install Python.Python.3.13`",
    )


def check_packages() -> list[CheckResult]:
    required = [
        "loguru", "ollama", "fastapi", "uvicorn", "pydantic",
        "pydantic_settings", "httpx", "sqlite3",
    ]
    optional = [
        ("nvidia_ml_py", "telemetry: NVIDIA energy"),
        ("amdsmi", "telemetry: AMD energy"),
        ("kokoro_onnx", "TTS: Kokoro voices"),
        ("faster_whisper", "STT: faster Whisper"),
        ("face_recognition", "sensing: camera face ID"),
        ("mediapipe", "sensing: pose estimation"),
        ("PIL", "icon generation"),
    ]
    results = []
    for pkg in required:
        try:
            __import__(pkg)
            results.append(CheckResult(f"pkg:{pkg}", "ok", "installed"))
        except ImportError:
            results.append(CheckResult(
                f"pkg:{pkg}", "fail", "missing",
                fix_hint=f"pip install {pkg}",
            ))
    for pkg, why in optional:
        try:
            __import__(pkg)
            results.append(CheckResult(f"opt:{pkg}", "ok", f"installed — {why}"))
        except ImportError:
            results.append(CheckResult(
                f"opt:{pkg}", "info", f"not installed — {why}",
                fix_hint=f"pip install {pkg}",
            ))
    return results


def check_ollama() -> list[CheckResult]:
    out: list[CheckResult] = []
    try:
        import httpx
        r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=3.0)
        if r.status_code == 200:
            n = len(r.json().get("models", []))
            out.append(CheckResult("Ollama daemon", "ok", f"reachable, {n} models pulled"))
        else:
            out.append(CheckResult(
                "Ollama daemon", "fail",
                f"http {r.status_code}",
                fix_hint="restart the Ollama tray app",
            ))
            return out
    except Exception as e:
        out.append(CheckResult(
            "Ollama daemon", "fail", "unreachable on 127.0.0.1:11434",
            detail=str(e),
            fix_hint="start Ollama: `ollama serve` or launch the tray app",
        ))
        return out

    # Parallel-load env vars
    for var, want in [
        ("OLLAMA_MAX_LOADED_MODELS", "≥ 2"),
        ("OLLAMA_NUM_PARALLEL", "≥ 2"),
        ("OLLAMA_KEEP_ALIVE", "≥ 5m"),
    ]:
        v = os.environ.get(var, "")
        if not v:
            out.append(CheckResult(
                f"env:{var}", "warn", f"not set (default = 1)",
                fix_hint=f"set {var}={want.split()[1]} at User scope, restart Ollama",
            ))
        else:
            out.append(CheckResult(f"env:{var}", "ok", v))
    return out


def check_required_models() -> list[CheckResult]:
    out: list[CheckResult] = []
    try:
        import httpx
        resp = httpx.get("http://127.0.0.1:11434/api/tags", timeout=3.0)
        if resp.status_code != 200:
            return [CheckResult("Ollama models", "warn", "could not check (daemon unreachable)")]
        names = {m["name"].split(":")[0] for m in resp.json().get("models", [])}
        required = ["vector-coder", "vector-focus", "vector-ambient", "nomic-embed-text"]
        for m in required:
            if m in names or any(m in n for n in names):
                out.append(CheckResult(f"model:{m}", "ok", "pulled"))
            else:
                out.append(CheckResult(
                    f"model:{m}", "warn", "missing",
                    fix_hint=f"ollama create {m} -f modelfiles/{m}.modelfile",
                ))
    except Exception as e:
        out.append(CheckResult("Ollama models", "fail", "check failed", detail=str(e)))
    return out


def check_gpu() -> CheckResult:
    # Try nvidia-smi first
    if shutil.which("nvidia-smi"):
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
                 "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5.0,
            )
            if r.returncode == 0 and r.stdout.strip():
                line = r.stdout.strip().split("\n")[0]
                return CheckResult("GPU", "ok", f"NVIDIA — {line}")
        except Exception as _sve:
            logger.debug("[VECTOR][vector_cli.doctor_cmd] suppressed Exception: %s", _sve)
    # macOS / Apple Silicon
    if sys.platform == "darwin":
        return CheckResult("GPU", "info", "Apple SoC (Metal)")
    return CheckResult("GPU", "warn", "no NVIDIA detected — CPU inference only")


def check_telemetry() -> list[CheckResult]:
    out: list[CheckResult] = []
    try:
        from core.telemetry import capabilities  # type: ignore[import]
        caps = capabilities()
        for name, on in caps.items():
            out.append(CheckResult(
                f"telemetry:{name}",
                "ok" if on else "info",
                "ready" if on else "not available",
            ))
    except Exception as e:
        out.append(CheckResult(
            "telemetry", "fail", "core.telemetry failed to import",
            detail=str(e),
            fix_hint="run: python scripts/fix_oj_imports.py --apply",
        ))
    return out


def check_registries() -> list[CheckResult]:
    out: list[CheckResult] = []
    try:
        from vectorcode.src.agents.registry import get_registry  # type: ignore
        n = len(get_registry().list_all())
        out.append(CheckResult("agent registry", "ok", f"{n} agents registered"))
    except Exception as e:
        out.append(CheckResult(
            "agent registry", "fail", "load failed", detail=str(e)[:120],
        ))

    try:
        from vectorcode.src.vector_cli.commands import COMMAND_REGISTRY  # type: ignore
        out.append(CheckResult("slash commands", "ok", f"{len(COMMAND_REGISTRY)} commands"))
    except Exception as e:
        out.append(CheckResult("slash commands", "fail", "load failed", detail=str(e)[:120]))

    try:
        from vectorcode.src.hooks.registry import get_hook_registry, HookName  # type: ignore
        reg = get_hook_registry()
        active = sum(len(reg.list_handlers(h)) for h in HookName)
        out.append(CheckResult("hooks", "ok", f"{active} handlers across all hook events"))
    except Exception as e:
        out.append(CheckResult("hooks", "fail", "load failed", detail=str(e)[:120]))
    return out


def check_skills() -> CheckResult:
    skills_dir = ROOT / "vectorcode" / "skills"
    if not skills_dir.exists():
        return CheckResult("skills", "fail", "vectorcode/skills/ missing")
    n_md = sum(1 for _ in skills_dir.rglob("SKILL.md"))
    n_top = sum(1 for _ in skills_dir.glob("*.md"))
    return CheckResult("skills", "ok", f"{n_md} folder skills + {n_top} top-level vc-*.md")


def check_certs() -> CheckResult:
    cert_dir = ROOT / "certs"
    crt = cert_dir / "vector.crt"
    key = cert_dir / "vector.key"
    if crt.exists() and key.exists():
        return CheckResult("SSL certs", "ok", f"{crt.name} + {key.name}")
    return CheckResult(
        "SSL certs", "warn", "self-signed cert missing",
        fix_hint="they auto-generate when you run `python run_vector.py api`",
    )


def check_db() -> list[CheckResult]:
    out: list[CheckResult] = []
    from core.memory.db_utils import configured_db_path

    main_db = configured_db_path()
    if main_db.exists():
        try:
            from core.memory.episodic import get_db_connection
            con = get_db_connection()
            con.execute("SELECT 1").fetchone()
            mb = main_db.stat().st_size / 1024 / 1024
            out.append(CheckResult("vector_memory.db", "ok", f"{mb:.1f} MB"))
        except Exception as e:
            out.append(CheckResult("vector_memory.db", "fail", "locked or corrupt", detail=str(e)))
    else:
        out.append(CheckResult(
            "vector_memory.db", "info", "not yet created (will be on first run)",
        ))

    tel_db = ROOT / "data" / "telemetry.db"
    if tel_db.exists():
        try:
            con = sqlite3.connect(tel_db, timeout=2.0, check_same_thread=False)
            n = con.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0]
            con.close()
            out.append(CheckResult("data/telemetry.db", "ok", f"{n:,} records"))
        except Exception as e:
            out.append(CheckResult("data/telemetry.db", "warn", "schema not migrated", detail=str(e)))
    else:
        out.append(CheckResult(
            "data/telemetry.db", "info", "not yet created (created on first chat() call)",
        ))
    return out


def check_disk() -> CheckResult:
    total, used, free = shutil.disk_usage(ROOT)
    free_gb = free / (1024 ** 3)
    if free_gb >= 20:
        return CheckResult("disk space", "ok", f"{free_gb:.1f} GB free")
    if free_gb >= 5:
        return CheckResult(
            "disk space", "warn", f"only {free_gb:.1f} GB free",
            fix_hint="VECTOR's models + telemetry need 20+ GB",
        )
    return CheckResult(
        "disk space", "fail", f"only {free_gb:.1f} GB free — too low",
        fix_hint="free up disk space; models alone are 50+ GB",
    )


def check_obsidian() -> CheckResult:
    try:
        from core.config import CONFIG  # type: ignore
        vault = CONFIG.get("vault_path", "")
        if not vault:
            return CheckResult("Obsidian vault", "info", "not configured")
        p = Path(str(vault))
        if p.exists():
            return CheckResult("Obsidian vault", "ok", str(p))
        return CheckResult(
            "Obsidian vault", "warn", f"path missing: {p}",
            fix_hint="set vault_path in config or .env",
        )
    except Exception as e:
        return CheckResult("Obsidian vault", "info", "config not loaded", detail=str(e))


def check_desktop_app() -> CheckResult:
    cargo = ROOT / "desktop" / "src-tauri" / "Cargo.toml"
    if cargo.exists():
        return CheckResult("desktop app", "ok", "Tauri scaffold present at desktop/src-tauri/")
    return CheckResult("desktop app", "info", "not scaffolded")


# ── Auto-fix attempts (when --fix is passed) ─────────────────────────────────


def attempt_fixes(results: list[CheckResult]) -> list[str]:
    """Try benign auto-fixes for warn/fail items. Returns list of actions taken."""
    actions: list[str] = []

    # Fix 1: ensure data/ dir exists
    data_dir = ROOT / "data"
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        actions.append("Created data/ directory")

    # Fix 2: set Ollama env vars at User scope (Windows only, idempotent)
    if sys.platform == "win32":
        wanted = {
            "OLLAMA_MAX_LOADED_MODELS": "4",
            "OLLAMA_NUM_PARALLEL": "4",
            "OLLAMA_KEEP_ALIVE": "30m",
        }
        try:
            for var, val in wanted.items():
                if not os.environ.get(var):
                    subprocess.run(
                        ["setx", var, val],
                        capture_output=True, timeout=5.0,
                    )
                    actions.append(f"Set {var}={val} (User scope)")
        except Exception as _sve:
            logger.debug("[VECTOR][vector_cli.doctor_cmd] suppressed Exception: %s", _sve)

    # Fix 3: run fix_oj_imports.py if telemetry import failed
    tel_failed = any(r.name == "telemetry" and r.status == "fail" for r in results)
    if tel_failed:
        fix_script = ROOT / "scripts" / "fix_oj_imports.py"
        if fix_script.exists():
            try:
                r = subprocess.run(
                    [sys.executable, str(fix_script), "--apply"],
                    capture_output=True, text=True, timeout=60.0,
                )
                if r.returncode == 0:
                    actions.append("Ran fix_oj_imports.py to repair absorbed module imports")
            except Exception as _sve:
                logger.debug("[VECTOR][vector_cli.doctor_cmd] suppressed Exception: %s", _sve)

    return actions


# ── Main ─────────────────────────────────────────────────────────────────────


def run_all_checks() -> list[CheckResult]:
    results: list[CheckResult] = []
    results.append(check_python())
    results.extend(check_packages())
    results.append(check_gpu())
    results.extend(check_ollama())
    results.extend(check_required_models())
    results.extend(check_telemetry())
    results.extend(check_registries())
    results.append(check_skills())
    results.append(check_certs())
    results.extend(check_db())
    results.append(check_disk())
    results.append(check_obsidian())
    results.append(check_desktop_app())
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vector doctor", description=__doc__)
    p.add_argument("--json", action="store_true", help="output JSON instead of pretty")
    p.add_argument("--fix", action="store_true", help="attempt benign auto-fixes")
    p.add_argument("--no-color", action="store_true")
    args = p.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception as _sve:
        logger.debug("[VECTOR][vector_cli.doctor_cmd] suppressed Exception: %s", _sve)

    if args.no_color:
        global GREEN, YELLOW, RED, DIM, BOLD, RESET
        GREEN = YELLOW = RED = DIM = BOLD = RESET = ""

    print(f"\n{BOLD}VECTOR doctor{RESET}  {DIM}— health check{RESET}")
    print("─" * 70)
    results = run_all_checks()

    fix_actions: list[str] = []
    if args.fix:
        fix_actions = attempt_fixes(results)
        if fix_actions:
            print(f"\n{BOLD}Auto-fix actions taken:{RESET}")
            for a in fix_actions:
                print(f"  {GREEN}{OK_MARK}{RESET}  {a}")
            # Re-run after fixes
            print(f"\n{BOLD}Re-running checks…{RESET}")
            print("─" * 70)
            results = run_all_checks()

    if args.json:
        print(json.dumps([asdict(r) for r in results], indent=2))
        return 0

    for r in results:
        _emit(r, plain=args.no_color)

    n_ok = sum(1 for r in results if r.status == "ok")
    n_warn = sum(1 for r in results if r.status == "warn")
    n_fail = sum(1 for r in results if r.status == "fail")
    n_info = sum(1 for r in results if r.status == "info")

    print()
    print("─" * 70)
    print(
        f"  Summary: {GREEN}{n_ok} OK{RESET}  "
        f"{YELLOW}{n_warn} warn{RESET}  "
        f"{RED}{n_fail} fail{RESET}  "
        f"{DIM}{n_info} info{RESET}"
    )

    if n_fail > 0:
        return 1
    if n_warn > 0:
        return 0  # warn doesn't fail the doctor; just informs
    return 0


if __name__ == "__main__":
    sys.exit(main())
