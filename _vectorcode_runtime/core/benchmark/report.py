"""Benchmark report generation — JSON + Markdown output with diff comparison.

Supports:
- Baseline run → JSON + Markdown report
- Diff against previous baseline → per-category delta
- Persistent storage in data/benchmarks/
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from core.benchmark.benchmark_task import TaskResult


class BenchmarkReport:
    """Generates and manages benchmark reports."""

    def __init__(self, results: list[TaskResult]):
        self.results = results
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.hostname = platform.node()
        self.git_sha = self._get_git_sha()

    @staticmethod
    def _get_git_sha() -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            return "unknown"

    @property
    def summary(self) -> dict[str, Any]:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        failed = total - passed
        return {
            "total_tasks": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / total, 3) if total > 0 else 0.0,
            "total_latency_ms": round(sum(r.latency_ms for r in self.results), 1),
            "total_llm_calls": sum(r.llm_calls for r in self.results),
            "total_tokens": sum(r.tokens_consumed for r in self.results),
            "total_human_interventions": sum(r.human_intervention_count for r in self.results),
            "total_incorrect_actions": sum(r.incorrect_actions for r in self.results),
            "total_recovery_attempts": sum(r.recovery_attempts for r in self.results),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": "1.0",
            "timestamp": self.timestamp,
            "hostname": self.hostname,
            "git_sha": self.git_sha,
            "summary": self.summary,
            "tasks": [r.to_dict() for r in self.results],
        }

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        """Durably replace a report without exposing a partial file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False,
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                tmp_path = Path(handle.name)
            os.replace(tmp_path, path)
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)

    # ── JSON output ──────────────────────────────────────────────────────

    def save_json(self, path: str | Path) -> Path:
        path = Path(path)
        self._atomic_write(path, json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        logger.info("[VECTOR][bench] JSON report saved to {}", path)
        return path

    @classmethod
    def load_json(cls, path: str | Path) -> BenchmarkReport:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        results = [
            TaskResult(
                task_id=t["task_id"],
                category=t["category"],
                initial_state=t.get("initial_state", ""),
                required_capability=t.get("required_capability", ""),
                expected_behavior=t.get("expected_behavior", ""),
                actual_behavior=t.get("actual_behavior", ""),
                success=t.get("success", False),
                human_intervention_count=t.get("human_intervention_count", 0),
                incorrect_actions=t.get("incorrect_actions", 0),
                recovery_attempts=t.get("recovery_attempts", 0),
                latency_ms=t.get("latency_ms", 0.0),
                llm_calls=t.get("llm_calls", 0),
                tokens_consumed=t.get("tokens_consumed", 0),
                final_outcome=t.get("final_outcome", ""),
                details=t.get("details", {}),
            )
            for t in data.get("tasks", [])
        ]
        report = cls(results)
        report.timestamp = data.get("timestamp", report.timestamp)
        report.hostname = data.get("hostname", report.hostname)
        report.git_sha = data.get("git_sha", report.git_sha)
        return report

    # ── Markdown output ──────────────────────────────────────────────────

    def to_markdown(self) -> str:
        s = self.summary
        lines = [
            f"# VECTOR Cognitive Benchmark — {self.timestamp[:19]}",
            "",
            f"**Host**: {self.hostname} | **Git**: {self.git_sha}",
            "",
            f"## Summary: {s['passed']}/{s['total_tasks']} passed ({s['pass_rate']:.1%})",
            "",
            f"- **Total latency**: {s['total_latency_ms']:.0f}ms",
            f"- **LLM calls**: {s['total_llm_calls']}",
            f"- **Tokens consumed**: {s['total_tokens']:,}",
            f"- **Human interventions**: {s['total_human_interventions']}",
            f"- **Incorrect actions**: {s['total_incorrect_actions']}",
            f"- **Recovery attempts**: {s['total_recovery_attempts']}",
            "",
            "## Results",
            "",
            "| # | Category | Status | Latency | LLM Calls | Tokens | Interventions |",
            "|---|----------|--------|---------|-----------|--------|---------------|",
        ]

        for r in self.results:
            status = "✅ PASS" if r.success else "❌ FAIL"
            cat = r.category.replace("_", " ").title()
            lines.append(
                f"| {r.task_id} | {cat} | {status} | "
                f"{r.latency_ms:.0f}ms | {r.llm_calls} | {r.tokens_consumed:,} | "
                f"{r.human_intervention_count} |"
            )

        # Failed tasks detail
        failed = [r for r in self.results if not r.success]
        if failed:
            lines.extend(["", "## Failed Tasks", ""])
            for r in failed:
                cat = r.category.replace("_", " ").title()
                lines.extend([
                    f"### {r.task_id} — {cat}",
                    f"- **Expected**: {r.expected_behavior}",
                    f"- **Actual**: {r.actual_behavior}",
                    f"- **Outcome**: {r.final_outcome}",
                    f"- **Recovery attempts**: {r.recovery_attempts}",
                    "",
                ])

        return "\n".join(lines)

    def save_markdown(self, path: str | Path) -> Path:
        path = Path(path)
        self._atomic_write(path, self.to_markdown())
        logger.info("[VECTOR][bench] Markdown report saved to {}", path)
        return path

    # ── Diff comparison ──────────────────────────────────────────────────

    def diff(self, other: BenchmarkReport) -> str:
        """Generate a markdown diff between this report and a previous one."""
        lines = [
            f"# Benchmark Diff: {other.timestamp[:10]} → {self.timestamp[:10]}",
            "",
            "## Summary Comparison",
            "",
            "| Metric | Previous | Current | Delta |",
            "|--------|----------|---------|-------|",
        ]

        prev_s = other.summary
        curr_s = self.summary
        for key, label in [
            ("pass_rate", "Pass Rate"),
            ("passed", "Passed"),
            ("failed", "Failed"),
            ("total_latency_ms", "Total Latency (ms)"),
            ("total_llm_calls", "LLM Calls"),
            ("total_tokens", "Tokens"),
            ("total_human_interventions", "Human Interventions"),
            ("total_incorrect_actions", "Incorrect Actions"),
        ]:
            prev_val = prev_s.get(key, 0)
            curr_val = curr_s.get(key, 0)
            if isinstance(prev_val, float):
                delta = curr_val - prev_val
                delta_str = f"{delta:+.3f}" if delta != 0 else "0"
                lines.append(f"| {label} | {prev_val:.3f} | {curr_val:.3f} | {delta_str} |")
            else:
                delta = curr_val - prev_val
                delta_str = f"{delta:+d}" if delta != 0 else "0"
                lines.append(f"| {label} | {prev_val} | {curr_val} | {delta_str} |")

        # Per-category diff
        lines.extend(["", "## Per-Category Changes", ""])
        prev_map = {r.task_id: r for r in other.results}
        curr_map = {r.task_id: r for r in self.results}

        all_ids = sorted(set(list(prev_map.keys()) + list(curr_map.keys())))
        changed = False
        for tid in all_ids:
            prev_r = prev_map.get(tid)
            curr_r = curr_map.get(tid)
            if prev_r is None:
                lines.append(f"- **{tid}** ({curr_r.category}): 🆕 NEW — {'✅' if curr_r.success else '❌'}")
                changed = True
            elif curr_r is None:
                lines.append(f"- **{tid}** ({prev_r.category}): 🗑️ REMOVED")
                changed = True
            elif prev_r.success != curr_r.success:
                arrow = "📈" if curr_r.success else "📉"
                prev_status = "✅" if prev_r.success else "❌"
                curr_status = "✅" if curr_r.success else "❌"
                lines.append(f"- **{tid}** ({curr_r.category}): {arrow} {prev_status} → {curr_status}")
                changed = True

        if not changed:
            lines.append("_No category changes._")

        return "\n".join(lines)

    def save_diff(self, other: BenchmarkReport, path: str | Path) -> Path:
        path = Path(path)
        self._atomic_write(path, self.diff(other))
        return path

    # ── Auto-save with timestamp ─────────────────────────────────────────

    def save(self, output_dir: str | Path | None = None) -> tuple[Path, Path]:
        """Save both JSON and Markdown with auto-generated timestamp filename."""
        if output_dir is None:
            output_dir = Path(__file__).parent.parent.parent / "data" / "benchmarks"
        output_dir = Path(output_dir)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = output_dir / f"benchmark_{ts}"
        json_path = self.save_json(f"{base}.json")
        md_path = self.save_markdown(f"{base}.md")
        return json_path, md_path
