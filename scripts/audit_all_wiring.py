"""Full cross-repo wiring audit — all absorbed modules vs all codebase files."""
from loguru import logger
import sys, os, re
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

CODEBASE = Path(__file__).resolve().parents[1]
os.chdir(CODEBASE)

# Load all Python source files
all_source: dict[str, str] = {}
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", "graphify-out", ".claude"}
for root, dirs, files in os.walk(CODEBASE):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    for f in files:
        if not f.endswith(".py"):
            continue
        fpath = os.path.join(root, f)
        rel = os.path.relpath(fpath, CODEBASE).replace("\\", "/")
        try:
            with open(fpath, encoding="utf-8") as fh:
                all_source[rel] = fh.read()
        except Exception:
            logger.opt(exception=True).debug("[VECTOR] unable to read {}", fpath)

def is_wired(module_rel: str, symbol: str) -> tuple[bool, list[str]]:
    """Return (wired, [files that import/use it])."""
    callers = []
    module_source = all_source.get(module_rel, "")
    if module_rel.endswith("/__init__.py") and "__getattr__" in module_source and symbol in module_source:
        callers.append(f"{module_rel} (lazy export)")
    # Build import patterns
    mod_dotted = module_rel.replace("/", ".").replace(".py", "")
    # Also check short name (last segment)
    short = mod_dotted.split(".")[-1]
    for fpath, src in all_source.items():
        if fpath == module_rel:
            continue
        direct_symbol_import = re.search(
            rf"\bfrom\s+{re.escape(mod_dotted)}\s+import\s+[^\n]*\b{re.escape(symbol)}\b",
            src,
        )
        if (f"from {mod_dotted}" in src or
            f"import {mod_dotted}" in src or
            direct_symbol_import):
            callers.append(fpath)
    return bool(callers), callers


results = []

def check(module, symbol, expect_wired=True):
    wired, callers = is_wired(module, symbol)
    status = "WIRED" if wired else "UNWIRED"
    marker = "OK" if (wired == expect_wired) else "!!"
    short_callers = [c.split("/")[-1] for c in callers[:3]]
    note = f"← {', '.join(short_callers)}" if callers else ""
    results.append((status, module, symbol, note))
    print(f"  {status:8s} {module.split('/')[-1]:40s} ({symbol}) {note}")


# ── JCODE ─────────────────────────────────────────────────────────────────────
print("=== JCODE (core/jcode/) ===")
check("core/jcode/cache_tracker.py",        "CacheTracker")
check("core/jcode/tools/multiedit.py",      "multiedit_file")
check("core/jcode/tools/apply_patch.py",    "apply_codex_patch")
check("core/jcode/ambient_scheduler.py",    "AmbientScheduler")
check("core/jcode/session_persistence.py",  "PersistedSession")

# ── OPENFANG ──────────────────────────────────────────────────────────────────
print()
print("=== OPENFANG (core/audit,metering,security,network,sandbox,migration,inference/) ===")
check("core/audit/merkle_chain.py",         "get_audit_chain")
check("core/metering/budget_meter.py",      "get_budget_meter")
check("core/metering/rate_limiter.py",      "get_rate_limiter")
check("core/security/prompt_injection.py",  "scan_text")
check("core/security/ssrf_guard.py",        "is_safe_url")
check("core/security/taint_tracker.py",     "get_taint_tracker")
check("core/network/ofp_protocol.py",       "OFPNode")
check("core/sandbox/vector_sandbox.py",     "VectorSandbox")
check("core/migration/importer.py",         "VectorMigrator")
check("core/inference/llm_providers.py",    "PROVIDERS")
check("core/inference/provider_client.py",  "ProviderClient")

# ── OPENHUMAN ─────────────────────────────────────────────────────────────────
print()
print("=== OPENHUMAN (core/engine/) ===")
check("core/engine/memory_tree/tree_builder.py",    "MemoryTree")
check("core/engine/memory_tree/ingestion_queue.py", "IngestionQueue")
check("core/engine/memory_tree/wiki_formatter.py",  "WikiFormatter")
check("core/engine/token_juice/compressor.py",      "reduce_text")
check("core/engine/agents/roles.py",                "ROLES_BY_NAME")
check("core/engine/research/parallel_researcher.py","ParallelResearcher")
check("core/engine/oauth/server.py",                "create_oauth_app")
check("core/engine/oauth/registry.py",              "OAUTH_REGISTRY")
check("core/engine/oauth/flows.py",                 "OAuthToken")
check("core/engine/telemetry/otel_bridge.py",       "get_telemetry")
check("core/engine/telemetry/sentry_bridge.py",     "init_sentry")
check("core/engine/providers/model_router.py",      "ModelRouter")
check("core/engine/tools/dispatcher.py",            "NativeDispatcher")
check("core/engine/channels/runtime.py",            "ChannelRuntime")

# ── SCRAPLING ─────────────────────────────────────────────────────────────────
print()
print("=== SCRAPLING (core/scraper/) ===")
check("core/scraper/vector_scraper.py",     "get_scraper")
check("core/scraper/fetchers.py",           "AsyncFetcher")
check("core/scraper/__init__.py",           "Fetcher")
check("core/scraper/spiders/spider.py",     "Spider")

# ── HYPERFRAMES / core/video ──────────────────────────────────────────────────
print()
print("=== HYPERFRAMES (core/video/ + dashboard/) ===")
check("core/video/composition_types.py",    "Fps")
check("core/video/html_renderer.py",        "HTMLFrameRenderer")
check("core/video/video_encoder.py",        "VideoEncoder")
check("core/video/audio_mixer.py",          "AudioMixer")
check("core/video/background_remover.py",   "BackgroundRemover")
check("core/video/vector_composer.py",      "VectorComposer")
check("core/video/website_to_video.py",     "WebsiteToVideo")
check("core/video/composition_linter.py",   "lint_composition")
check("core/video/studio_server.py",        "start_studio_server")
# JS runtime - special case
js_wired = "_RUNTIME_JS" in all_source.get("core/video/html_renderer.py", "")
results.append(("WIRED" if js_wired else "UNWIRED", "core/video/runtime/vector_runtime.js", "__vector", ""))
print(f"  {'WIRED' if js_wired else 'UNWIRED':8s} vector_runtime.js                       (__vector) {'← html_renderer.py' if js_wired else ''}")

print()
print("=== SUMMARY ===")
wired_count   = sum(1 for r in results if r[0] == "WIRED")
unwired_count = sum(1 for r in results if r[0] == "UNWIRED")
total = len(results)
print(f"  WIRED:   {wired_count}/{total}")
print(f"  UNWIRED: {unwired_count}/{total}")
print()
if unwired_count:
    print("UNWIRED modules:")
    for status, mod, sym, note in results:
        if status == "UNWIRED":
            print(f"  - {mod} ({sym})")

sys.exit(1 if unwired_count else 0)
