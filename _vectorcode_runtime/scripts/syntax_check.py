"""Syntax check all modified files from the audit."""
import ast

files = [
    "core/event_bus/worker_pool.py",
    "core/loop/autonomous_loop.py",
    "core/inference/provider_health.py",
    "core/inference/model_pool.py",
    "core/inference/quota_ledger.py",
    "core/inference/cloud_router.py",
    "core/inference/provider_registry.py",
    "core/inference/llm_providers.py",
    "core/inference/smart_routing/fallback_chain.py",
    "core/inference/vectorcode_llm.py",
    "core/inference/model_catalog.py",
    "core/metering/rate_limiter.py",
    "core/email/sender.py",
    "core/memory/semantic.py",
    "districts/content/blog_publisher.py",
    "districts/content/uploader.py",
    "districts/growth/content_arm.py",
    "vectorcode/src/channels/bulk_sender.py",
]

ok = 0
failed = 0
for f in files:
    try:
        ast.parse(open(f, encoding="utf-8").read())
        ok += 1
        print(f"  OK  {f}")
    except SyntaxError as e:
        print(f"FAIL  {f}: {e}")
        failed += 1
    except FileNotFoundError:
        print(f"MISS  {f} (not found)")
        failed += 1

print(f"\n{ok}/{len(files)} files syntax OK")
raise SystemExit(1 if failed else 0)
