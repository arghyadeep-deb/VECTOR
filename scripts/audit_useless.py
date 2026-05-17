"""Audit what's useless in absorbed repos and remove it."""
import shutil
from pathlib import Path

CA = Path("core/coding_assistant")
RE = Path("core/research_engine")

# ── core/coding_assistant/ — what to remove ───────────────────────────────────
REMOVE_CA = {
    "setup/onboarding":
        "Mistral first-run UI screens — VECTOR has no onboarding",
    "setup/auth":
        "Browser OAuth for Mistral cloud — VECTOR is local-only (Ollama)",
    "cli/plan_offer":
        "Mistral Pro subscription upsell — not a product, has no place in VECTOR",
    "cli/update_notifier":
        "Checks PyPI for new versions — VECTOR updates via git pull",
    "core/data_retention.py":
        "Mistral GDPR/data-retention policy file — not applicable",
    "core/proxy_setup.py":
        "HTTP proxy config UI — VECTOR uses environment variables",
    "core/tracing.py":
        "OpenTelemetry/Honeycomb distributed tracing — VECTOR uses loguru",
    "core/teleport":
        "Uploads code snapshots to Mistral cloud (nuage) — nuage already deleted, would crash",
    "core/tts/mistral_tts_client.py":
        "Mistral cloud TTS API client — VECTOR uses local Kokoro",
    "core/transcribe/mistral_transcribe_client.py":
        "Mistral cloud STT API client — VECTOR uses local Whisper",
    "core/auth/github.py":
        "GitHub device-flow OAuth — VECTOR uses gh CLI, not OAuth",
}

# ── core/research_engine/ — what to remove ───────────────────────────────────
REMOVE_RE = {
    "mcp":
        "LDR's own MCP server — VECTOR's mcp_server.py already exposes research tools",
    "notifications":
        "Apprise email/push — VECTOR uses Pushover + Telegram via vectorcode",
    "scheduler":
        "LDR research scheduler — VECTOR uses APScheduler in autonomous_loop.py",
    "research_scheduler":
        "Duplicate of scheduler/ — same reason",
}

def count_py(p: Path) -> int:
    if p.is_dir():
        return len(list(p.rglob("*.py")))
    return 1 if p.suffix == ".py" else 0

def check_imports(root: Path, keyword: str, skip_prefix: str) -> list[str]:
    refs = []
    for f in root.rglob("*.py"):
        rel = str(f.relative_to(root)).replace("\\", "/")
        if rel.startswith(skip_prefix):
            continue
        content = f.read_text(encoding="utf-8", errors="replace")
        if keyword in content:
            refs.append(rel)
    return refs[:5]

print("=" * 60)
print("AUDIT: core/coding_assistant/ — removing useless parts")
print("=" * 60)
ca_total = 0
for rel, reason in REMOVE_CA.items():
    p = CA / rel
    if p.exists():
        n = count_py(p)
        ca_total += n
        print(f"  REMOVE ({n:3d} py)  {rel}")
        print(f"          {reason}")
    else:
        print(f"  MISSING (skip): {rel}")

# Safety: confirm teleport not imported elsewhere
teleport_refs = check_imports(CA, "teleport", "core/teleport")
plan_refs = check_imports(CA, "plan_offer", "cli/plan_offer")
update_refs = check_imports(CA, "update_notifier", "cli/update_notifier")
print(f"\n  teleport imported elsewhere: {teleport_refs}")
print(f"  plan_offer imported elsewhere: {plan_refs}")
print(f"  update_notifier imported elsewhere: {update_refs}")
print(f"\n  Total to remove: {ca_total} py files")

print()
print("=" * 60)
print("AUDIT: core/research_engine/ — removing useless parts")
print("=" * 60)
re_total = 0
for rel, reason in REMOVE_RE.items():
    p = RE / rel
    if p.exists():
        n = count_py(p)
        re_total += n
        print(f"  REMOVE ({n:3d} py)  {rel}")
        print(f"          {reason}")
    else:
        print(f"  MISSING (skip): {rel}")

mcp_refs = check_imports(RE, "research_engine.mcp", "mcp")
sched_refs = check_imports(RE, "research_scheduler", "research_scheduler")
notif_refs = check_imports(RE, ".notifications", "notifications")
print(f"\n  mcp imported outside mcp/: {mcp_refs}")
print(f"  research_scheduler imported: {sched_refs}")
print(f"  notifications imported: {notif_refs}")
print(f"\n  Total to remove: {re_total} py files")

print()
answer = input("Proceed with deletion? (yes/no): ").strip().lower()
if answer != "yes":
    print("Aborted — nothing deleted.")
    raise SystemExit(0)

# ── Execute deletions ─────────────────────────────────────────────────────────
removed_ca = 0
for rel in REMOVE_CA:
    p = CA / rel
    if p.exists():
        n = count_py(p)
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        removed_ca += n
        print(f"  Deleted: core/coding_assistant/{rel} ({n} py)")

removed_re = 0
for rel in REMOVE_RE:
    p = RE / rel
    if p.exists():
        n = count_py(p)
        shutil.rmtree(p)
        removed_re += n
        print(f"  Deleted: core/research_engine/{rel} ({n} py)")

print()
print(f"Removed {removed_ca} py from coding_assistant, {removed_re} from research_engine")
print(f"coding_assistant now: {len(list(CA.rglob('*.py')))} py")
print(f"research_engine now : {len(list(RE.rglob('*.py')))} py")
