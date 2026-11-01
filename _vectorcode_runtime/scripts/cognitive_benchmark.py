"""VECTOR Cognitive Benchmark — CLI entry point.

Measures actual cognitive capabilities across 14 dimensions.
Not unit tests — repeatable benchmark with quantitative comparison.

Usage:
    python scripts/cognitive_benchmark.py
    python scripts/cognitive_benchmark.py --categories long_term_memory,planning
    python scripts/cognitive_benchmark.py --diff data/benchmarks/baseline_20260813.json
    python scripts/cognitive_benchmark.py --list
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger


def main() -> int:
    parser = argparse.ArgumentParser(
        description="VECTOR Cognitive Benchmark — measure actual cognitive capabilities",
    )
    parser.add_argument(
        "--categories", "-c",
        type=str,
        default=None,
        help="Comma-separated categories to run (default: all 14)",
    )
    parser.add_argument(
        "--diff", "-d",
        type=str,
        default=None,
        help="Path to previous benchmark JSON for diff comparison",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output directory for reports (default: data/benchmarks/)",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available categories and exit",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if not args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="INFO", format="{message}")

    if args.list:
        from core.benchmark.benchmark_runner import BenchmarkRunner
        categories = BenchmarkRunner.list_categories()
        print("\nAvailable benchmark categories:")
        print("-" * 40)
        for i, cat in enumerate(categories, 1):
            print(f"  {i:2d}. {cat.replace('_', ' ').title()}")
        print(f"\nTotal: {len(categories)} categories")
        print("\nRun all:    python scripts/cognitive_benchmark.py")
        print("Run subset: python scripts/cognitive_benchmark.py --categories long_term_memory,planning")
        return 0

    # Build category filter
    categories = None
    if args.categories:
        categories = [c.strip() for c in args.categories.split(",")]

    print("\n" + "=" * 60)
    print("  VECTOR Cognitive Benchmark")
    print("=" * 60)

    if categories:
        print(f"  Categories: {', '.join(c.replace('_', ' ') for c in categories)}")
    else:
        print("  Running all 14 cognitive categories")
    print()

    # Run benchmark
    from core.benchmark.benchmark_runner import BenchmarkRunner

    runner = BenchmarkRunner(categories=categories)

    if not runner.tasks:
        print("ERROR: No benchmark tasks loaded. Check imports.")
        return 1

    print(f"  Loaded {len(runner.tasks)} tasks")
    print("-" * 60)

    t0 = time.monotonic()
    report = runner.run()
    elapsed = time.monotonic() - t0

    # Print summary
    summary = report.summary
    print()
    print("=" * 60)
    print(f"  Results: {summary['passed']}/{summary['total_tasks']} passed ({summary['pass_rate']:.1%})")
    print(f"  Total time: {elapsed:.1f}s")
    print(f"  LLM calls: {summary['total_llm_calls']}")
    print(f"  Tokens consumed: {summary['total_tokens']:,}")
    print(f"  Human interventions: {summary['total_human_interventions']}")
    print("=" * 60)

    # Save reports
    output_dir = Path(args.output) if args.output else None
    json_path, md_path = report.save(output_dir=output_dir)
    print(f"\n  Reports saved:")
    print(f"    JSON: {json_path}")
    print(f"    Markdown: {md_path}")

    # Diff if requested
    if args.diff:
        diff_path = Path(args.diff)
        if diff_path.exists():
            from core.benchmark.report import BenchmarkReport
            prev = BenchmarkReport.load_json(diff_path)
            diff_text = report.diff(prev)
            diff_file = json_path.with_suffix(".diff.md")
            diff_file.write_text(diff_text, encoding="utf-8")
            print(f"    Diff: {diff_file}")
            print()
            print(diff_text)
        else:
            print(f"\n  WARNING: Diff file not found: {args.diff}")

    # Print per-task results
    print()
    for r in report.results:
        status = "PASS" if r.success else "FAIL"
        icon = "+" if r.success else "-"
        cat = r.category.replace("_", " ").title()
        print(f"  [{icon}] {r.task_id} {cat:<30s} {status:<6s} {r.latency_ms:>8.0f}ms")

    print()

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
