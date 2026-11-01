"""VECTOR Inference Report CLI — daily observability reports.

Generates human-readable reports of LLM usage: calls/day, tokens/day,
provider breakdown, domain breakdown, model breakdown (tokens/model),
autonomous vs. user-triggered token consumption, raw fallback count,
failure rate, retry rate (where measurable), latency percentiles, quota
saturation, and alert checks.

Usage:
    python scripts/inference_report.py                    # today's report
    python scripts/inference_report.py --date 2026-08-13  # specific day
    python scripts/inference_report.py --provider         # provider breakdown only
    python scripts/inference_report.py --domain           # domain breakdown only
    python scripts/inference_report.py --models           # tokens-by-model breakdown only
    python scripts/inference_report.py --autonomy         # autonomous vs. user token split
    python scripts/inference_report.py --callers          # top callers
    python scripts/inference_report.py --alerts           # check alerts only
    python scripts/inference_report.py --json             # JSON output (all breakdowns)
    python scripts/inference_report.py --hourly           # last hour snapshot
    python scripts/inference_report.py --prune 30         # delete records > 30 days old
"""

import sys
import json
import argparse
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger


def main() -> int:
    parser = argparse.ArgumentParser(
        description="VECTOR Inference Report — daily LLM observability reports",
    )
    parser.add_argument(
        "--date", "-d",
        type=str,
        default=None,
        help="Date to report on (YYYY-MM-DD, default: today UTC)",
    )
    parser.add_argument(
        "--provider", "-p",
        action="store_true",
        help="Show provider breakdown only",
    )
    parser.add_argument(
        "--domain",
        action="store_true",
        help="Show domain breakdown only",
    )
    parser.add_argument(
        "--callers",
        action="store_true",
        help="Show top callers breakdown only",
    )
    parser.add_argument(
        "--models",
        action="store_true",
        help="Show tokens-by-model breakdown only",
    )
    parser.add_argument(
        "--autonomy",
        action="store_true",
        help="Show autonomous vs. user-triggered token consumption only",
    )
    parser.add_argument(
        "--alerts", "-a",
        action="store_true",
        help="Check alert conditions only",
    )
    parser.add_argument(
        "--hourly",
        action="store_true",
        help="Show last hour snapshot",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON instead of human-readable text",
    )
    parser.add_argument(
        "--prune",
        type=int,
        default=None,
        metavar="DAYS",
        help="Delete records older than DAYS and exit",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if not args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="WARNING", format="{message}")

    from core.metering.inference_observability import get_inference_observability

    obs = get_inference_observability()

    # Prune mode
    if args.prune is not None:
        deleted = obs.prune(days=args.prune)
        print(f"Pruned {deleted} records older than {args.prune} days.")
        return 0

    # Alerts-only mode
    if args.alerts:
        alerts = obs.alert_check()
        if not alerts:
            print("No alerts — all clear.")
        else:
            print(f"{len(alerts)} alert(s):")
            for alert in alerts:
                print(f"  !! {alert}")
        return 0 if not alerts else 1

    # Hourly snapshot mode
    if args.hourly:
        snap = obs.hourly_snapshot()
        if args.json:
            print(json.dumps(snap, indent=2))
        else:
            print(f"Last hour: {snap['total_calls']} calls, "
                  f"{snap.get('total_tokens', 0):,} tokens, "
                  f"avg {snap.get('avg_latency_ms', 0):,.0f}ms, "
                  f"Ollama {snap.get('ollama_pct', 0):.1f}%")
        return 0

    # Full report or specific breakdowns
    target_date = args.date

    # JSON mode — output everything
    if args.json:
        data = {
            "summary": obs.daily_summary(target_date),
            "providers": obs.provider_summary(target_date),
            "domains": obs.domain_summary(target_date),
            "models": obs.model_summary(target_date),
            "callers": obs.caller_summary(target_date),
            "autonomy_tokens": obs.autonomy_token_summary(target_date),
            "token_exactness": obs.token_exactness_summary(target_date),
            "quota": obs.quota_saturation(),
            "alerts": obs.alert_check(),
        }
        print(json.dumps(data, indent=2))
        return 0

    # Specific breakdown modes
    if args.provider:
        providers = obs.provider_summary(target_date)
        if not providers:
            print(f"No inference calls recorded for {target_date or 'today'}.")
            return 0
        print(f"Provider Breakdown — {target_date or 'today'}:")
        print("-" * 70)
        for p in providers:
            print(
                f"  {p['provider']:<16s} {p['calls']:>5d} calls  "
                f"{p['tokens']:>10,d} tokens  avg {p['avg_latency_ms']:>7,.0f}ms  "
                f"{p['errors']} errors"
            )
        return 0

    if args.domain:
        domains = obs.domain_summary(target_date)
        if not domains:
            print(f"No inference calls recorded for {target_date or 'today'}.")
            return 0
        print(f"Domain Breakdown — {target_date or 'today'}:")
        print("-" * 60)
        for d in domains:
            print(
                f"  {d['domain']:<24s} {d['calls']:>5d} calls  "
                f"{d['tokens']:>10,d} tokens  avg {d['avg_latency_ms']:>7,.0f}ms"
            )
        return 0

    if args.callers:
        callers = obs.caller_summary(target_date)
        if not callers:
            print(f"No inference calls recorded for {target_date or 'today'}.")
            return 0
        print(f"Top Callers — {target_date or 'today'}:")
        print("-" * 70)
        for c in callers:
            kind = "AUTO" if c["is_autonomous"] else "USER"
            print(
                f"  [{kind}] {c['caller_id']:<30s} {c['calls']:>5d} calls  "
                f"{c['tokens']:>10,d} tokens"
            )
        return 0

    if args.models:
        models = obs.model_summary(target_date)
        if not models:
            print(f"No inference calls recorded for {target_date or 'today'}.")
            return 0
        print(f"Model Breakdown (tokens by model) — {target_date or 'today'}:")
        print("-" * 80)
        for m in models:
            print(
                f"  {m['model']:<28s} {m['calls']:>5d} calls  "
                f"{m['tokens']:>10,d} tokens "
                f"(in: {m['input_tokens']:,} | out: {m['output_tokens']:,})  "
                f"avg {m['avg_latency_ms']:>7,.0f}ms"
            )
        return 0

    if args.autonomy:
        auto = obs.autonomy_token_summary(target_date)
        print(f"Autonomous vs. User-Triggered Token Consumption — {target_date or 'today'}:")
        print("-" * 70)
        for kind, label in (("autonomous", "AUTO"), ("user", "USER")):
            row = auto[kind]
            print(
                f"  [{label}] {row['calls']:>5d} calls  {row['tokens']:>10,d} tokens "
                f"(in: {row['input_tokens']:,} | out: {row['output_tokens']:,})"
            )
        return 0

    # Full daily report
    report = obs.generate_daily_report(target_date)
    print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
