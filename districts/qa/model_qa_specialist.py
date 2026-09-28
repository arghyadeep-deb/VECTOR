
import asyncio
import datetime
import json
import math
import uuid

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.inference.vectorcode_llm import chat
from core.loop.context_engine import ContextEngine

class ModelQASpecialist(AgentBase):
    """
    ML model auditing agent for VECTOR's own neural_training.py outputs.
    Handles calibration testing, bias detection, drift analysis, and
    performance monitoring with structured audit reports.
    RULE 11: local models only — never Claude API at runtime.
    """

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="ModelQASpecialist",
            district="qa",
            generation=generation,
        )
        self.capabilities = ["audit", "bias", "drift", "evaluate", "model_qa", "qa", "report"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory: EpisodicMemory | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        logger.info(f"[VECTOR][model_qa_specialist] initialized gen={generation}")

    def _get_memory(self) -> EpisodicMemory:
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _llm(self, prompt: str, timeout: float = 25.0) -> str:
        hydration = ContextEngine().session_hydration_prompt({"query": prompt})
        return chat(
            self._model,
            [{"role": "user", "content": f"{hydration}\n\n{prompt}"}],
            timeout=timeout,
            district="qa",
            domain="agentic.loop",
        )

    # ── Core audit methods ────────────────────────────────────────────────────

    def audit_predictions(
        self,
        predictions: list[float],
        labels: list[float],
        threshold: float = 0.5,
    ) -> dict:
        """
        Computes accuracy, precision, recall, F1, Expected Calibration Error (ECE).
        Returns {metrics, calibration_issues, recommendations}.
        """
        if not predictions or not labels or len(predictions) != len(labels):
            return {"error": "predictions and labels must be non-empty lists of equal length"}

        n = len(predictions)

        # Binary classification metrics at threshold
        tp = sum(1 for p, l in zip(predictions, labels) if p >= threshold and l >= threshold)
        tn = sum(1 for p, l in zip(predictions, labels) if p < threshold and l < threshold)
        fp = sum(1 for p, l in zip(predictions, labels) if p >= threshold and l < threshold)
        fn = sum(1 for p, l in zip(predictions, labels) if p < threshold and l >= threshold)

        accuracy = (tp + tn) / n if n > 0 else 0.0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        # Expected Calibration Error (ECE) — 10-bin approximation
        n_bins = 10
        bin_size = 1.0 / n_bins
        ece = 0.0
        calibration_issues: list[str] = []

        for b in range(n_bins):
            lower = b * bin_size
            upper = (b + 1) * bin_size
            bin_preds = [(p, l) for p, l in zip(predictions, labels) if lower <= p < upper]
            if not bin_preds:
                continue
            bin_n = len(bin_preds)
            avg_pred = sum(p for p, _ in bin_preds) / bin_n
            avg_label = sum(l for _, l in bin_preds) / bin_n
            ece += (bin_n / n) * abs(avg_pred - avg_label)
            gap = abs(avg_pred - avg_label)
            if gap > 0.15:
                calibration_issues.append(
                    f"Bin [{lower:.1f},{upper:.1f}]: confidence={avg_pred:.2f} vs actual={avg_label:.2f} (gap={gap:.2f})"
                )

        ece = round(ece, 4)

        # Recommendations based on metrics
        recommendations: list[str] = []
        if accuracy < 0.7:
            recommendations.append("Accuracy below 70% — consider retraining with more data or better features")
        if f1 < 0.6:
            recommendations.append(f"F1={f1:.2f} is low — check class imbalance and threshold ({threshold})")
        if ece > 0.1:
            recommendations.append(f"ECE={ece} indicates poor calibration — apply temperature scaling or Platt scaling")
        if precision < 0.6:
            recommendations.append("Low precision — model generating too many false positives")
        if recall < 0.6:
            recommendations.append("Low recall — model missing too many true positives")
        if not recommendations:
            recommendations.append("Model metrics are within acceptable range")

        metrics = {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "ece": ece,
            "tp": tp, "tn": tn, "fp": fp, "fn": fn,
            "n_samples": n,
            "threshold": threshold,
        }

        logger.info(
            f"[VECTOR][model_qa_specialist] audit: acc={accuracy:.3f} f1={f1:.3f} ece={ece}"
        )
        return {
            "metrics": metrics,
            "calibration_issues": calibration_issues,
            "recommendations": recommendations,
        }

    def detect_bias(self, groups: dict, metric: str = "accuracy") -> dict:
        """
        Computes metric per group and flags disparate impact (>20% gap).
        groups format: {group_name: {"predictions": [...], "labels": [...]}}
        Returns {bias_detected, worst_group, disparity_pct, group_metrics}.
        """
        if not groups:
            return {"error": "groups dict is required", "bias_detected": False}

        group_metrics: dict[str, float] = {}
        threshold = 0.5

        for group_name, data in groups.items():
            preds = data.get("predictions", [])
            lbls = data.get("labels", [])
            if not preds or len(preds) != len(lbls):
                group_metrics[group_name] = 0.0
                continue

            n = len(preds)
            if metric == "accuracy":
                tp = sum(1 for p, l in zip(preds, lbls) if (p >= threshold) == (l >= threshold))
                group_metrics[group_name] = round(tp / n, 4)
            elif metric == "precision":
                tp = sum(1 for p, l in zip(preds, lbls) if p >= threshold and l >= threshold)
                fp = sum(1 for p, l in zip(preds, lbls) if p >= threshold and l < threshold)
                group_metrics[group_name] = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
            elif metric == "recall":
                tp = sum(1 for p, l in zip(preds, lbls) if p >= threshold and l >= threshold)
                fn = sum(1 for p, l in zip(preds, lbls) if p < threshold and l >= threshold)
                group_metrics[group_name] = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
            else:
                # Default: accuracy
                tp = sum(1 for p, l in zip(preds, lbls) if (p >= threshold) == (l >= threshold))
                group_metrics[group_name] = round(tp / n, 4)

        if not group_metrics:
            return {"bias_detected": False, "group_metrics": {}, "worst_group": None, "disparity_pct": 0.0}

        best_val = max(group_metrics.values())
        worst_group = min(group_metrics, key=group_metrics.get)
        worst_val = group_metrics[worst_group]
        disparity_pct = round((best_val - worst_val) / best_val * 100, 1) if best_val > 0 else 0.0
        bias_detected = disparity_pct > 20.0

        if bias_detected:
            logger.warning(
                f"[VECTOR][model_qa_specialist] BIAS DETECTED: worst_group='{worst_group}' "
                f"disparity={disparity_pct}%"
            )
        else:
            logger.info(f"[VECTOR][model_qa_specialist] bias check: disparity={disparity_pct}% (OK)")

        return {
            "bias_detected": bias_detected,
            "metric": metric,
            "group_metrics": group_metrics,
            "worst_group": worst_group,
            "worst_value": worst_val,
            "best_value": best_val,
            "disparity_pct": disparity_pct,
            "threshold_pct": 20.0,
            "verdict": "BIAS DETECTED" if bias_detected else "No significant bias",
        }

    def check_drift(
        self,
        baseline_preds: list[float],
        current_preds: list[float],
    ) -> dict:
        """
        PSI approximation + KS statistic to detect distribution drift.
        Returns {psi, ks_statistic, drift_detected, drift_verdict}.
        """
        if not baseline_preds or not current_preds:
            return {"error": "baseline_preds and current_preds are required"}

        n_bins = 10

        # PSI (Population Stability Index) approximation
        def _bin_distribution(preds: list[float], bins: int) -> list[float]:
            bin_counts = [0] * bins
            for p in preds:
                idx = min(int(p * bins), bins - 1)
                bin_counts[idx] += 1
            total = len(preds)
            return [max(c / total, 1e-8) for c in bin_counts]  # avoid log(0)

        baseline_dist = _bin_distribution(baseline_preds, n_bins)
        current_dist = _bin_distribution(current_preds, n_bins)

        psi = sum(
            (c - b) * math.log(c / b)
            for b, c in zip(baseline_dist, current_dist)
        )
        psi = round(abs(psi), 4)

        # Kolmogorov-Smirnov statistic
        baseline_sorted = sorted(baseline_preds)
        current_sorted = sorted(current_preds)
        n_b = len(baseline_sorted)
        n_c = len(current_sorted)

        # Compute empirical CDFs and find maximum difference
        all_values = sorted(set(baseline_sorted + current_sorted))
        ks_stat = 0.0
        for v in all_values:
            cdf_b = sum(1 for x in baseline_sorted if x <= v) / n_b
            cdf_c = sum(1 for x in current_sorted if x <= v) / n_c
            ks_stat = max(ks_stat, abs(cdf_b - cdf_c))
        ks_stat = round(ks_stat, 4)

        # PSI thresholds: <0.1 stable, 0.1-0.2 moderate, >0.2 significant drift
        if psi < 0.1:
            drift_verdict = "Stable — no significant drift"
            drift_detected = False
        elif psi < 0.2:
            drift_verdict = "Moderate drift — monitor closely, consider retraining"
            drift_detected = True
        else:
            drift_verdict = "Significant drift — retraining required"
            drift_detected = True

        logger.info(
            f"[VECTOR][model_qa_specialist] drift: PSI={psi} KS={ks_stat} drift={drift_detected}"
        )
        return {
            "psi": psi,
            "ks_statistic": ks_stat,
            "drift_detected": drift_detected,
            "drift_verdict": drift_verdict,
            "baseline_n": n_b,
            "current_n": n_c,
        }

    def generate_audit_report(self, model_name: str, audit_results: dict) -> str:
        """
        Structured audit report: executive summary, findings table, risk level, recommended actions.
        """
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        # Infer risk level from combined results
        risk_signals = 0
        if audit_results.get("calibration_issues"):
            risk_signals += 1
        if audit_results.get("bias_detected") or audit_results.get("bias", {}).get("bias_detected"):
            risk_signals += 2
        if audit_results.get("drift_detected") or audit_results.get("drift", {}).get("drift_detected"):
            risk_signals += 1
        metrics = audit_results.get("metrics", {})
        if metrics.get("f1", 1.0) < 0.6 or metrics.get("accuracy", 1.0) < 0.7:
            risk_signals += 2

        risk_level = "LOW" if risk_signals == 0 else ("MEDIUM" if risk_signals <= 2 else "HIGH")
        risk_emoji_text = {"LOW": "[OK]", "MEDIUM": "[WARNING]", "HIGH": "[CRITICAL]"}[risk_level]

        lines = [
            f"# ML Model Audit Report: {model_name}",
            f"**Generated:** {now}  ",
            f"**Risk Level:** {risk_level} {risk_emoji_text}",
            "",
            "## Executive Summary",
        ]

        if risk_level == "LOW":
            lines.append(f"Model '{model_name}' passed all audits. No immediate action required.")
        elif risk_level == "MEDIUM":
            lines.append(
                f"Model '{model_name}' shows moderate issues. Monitor and plan retraining within 30 days."
            )
        else:
            lines.append(
                f"Model '{model_name}' has critical quality issues. Retraining or replacement recommended immediately."
            )

        # Performance metrics table
        if metrics:
            lines += [
                "",
                "## Performance Metrics",
                "",
                "| Metric | Value | Status |",
                "|--------|-------|--------|",
            ]
            for metric_name in ["accuracy", "precision", "recall", "f1", "ece"]:
                val = metrics.get(metric_name)
                if val is not None:
                    if metric_name == "ece":
                        status = "OK" if val < 0.1 else "WARN"
                    else:
                        status = "OK" if val >= 0.7 else "WARN"
                    lines.append(f"| {metric_name.title()} | {val:.4f} | {status} |")

        # Calibration issues
        cal_issues = audit_results.get("calibration_issues", [])
        if cal_issues:
            lines += ["", "## Calibration Issues", ""]
            for issue in cal_issues:
                lines.append(f"- {issue}")

        # Bias findings
        bias = audit_results.get("bias", {})
        if bias:
            lines += [
                "",
                "## Bias Analysis",
                f"**Verdict:** {bias.get('verdict', 'Unknown')}  ",
                f"**Metric:** {bias.get('metric', 'N/A')}  ",
                f"**Disparity:** {bias.get('disparity_pct', 0)}%",
            ]
            if bias.get("group_metrics"):
                lines += ["", "| Group | Score |", "|-------|-------|"]
                for g, s in bias["group_metrics"].items():
                    lines.append(f"| {g} | {s:.4f} |")

        # Drift findings
        drift = audit_results.get("drift", {})
        if drift:
            lines += [
                "",
                "## Drift Analysis",
                f"**PSI:** {drift.get('psi', 'N/A')}  ",
                f"**KS Statistic:** {drift.get('ks_statistic', 'N/A')}  ",
                f"**Verdict:** {drift.get('drift_verdict', 'N/A')}",
            ]

        # Recommended actions
        recommendations = audit_results.get("recommendations", [])
        if recommendations:
            lines += ["", "## Recommended Actions", ""]
            for i, rec in enumerate(recommendations, 1):
                lines.append(f"{i}. {rec}")

        lines += [
            "",
            "---",
            f"*Audit conducted by VECTOR ModelQASpecialist | {now}*",
        ]

        return "\n".join(lines)

    async def answer_model_qa_question(self, query: str) -> str:
        """Answer a free-text/unmatched-task_type question grounded in
        this agent's real supported capabilities, instead of always
        dumping the raw status dict regardless of what was actually asked
        (KNOWN_ISSUES bug pattern — 'dumps an unrelated hardcoded
        default')."""
        context = (
            "ModelQASpecialist supports: audit (accuracy/F1/precision/recall "
            "against predictions+labels), bias (per-group metric parity), "
            "drift (baseline vs current prediction distribution shift), "
            "report (formatted audit summary)."
        )
        prompt = (
            "You are VECTOR's ModelQASpecialist in the qa district — you "
            "audit ML model predictions for accuracy, bias, and drift. "
            "Answer the owner's question using this real context; do not "
            f"invent data you don't have:\n\n{context}\n\nQuestion: {query}"
        )
        try:
            result = await asyncio.to_thread(self._llm, prompt, 20.0)
            return (result or "").strip() or context
        except Exception as e:
            logger.warning("[VECTOR][model_qa_specialist] answer_model_qa_question failed: {}", e)
            return context

    # ── run dispatch ──────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "status")
        try:
            if task_type == "audit":
                predictions = task.get("predictions", [])
                labels = task.get("labels", [])
                threshold = float(task.get("threshold", 0.5))
                if not predictions or not labels:
                    return {"status": "error", "error": "task.predictions and task.labels are required"}
                result = self.audit_predictions(predictions, labels, threshold)
                self._get_memory().store(
                    event_type="model_audit",
                    content=f"Model audit: acc={result['metrics']['accuracy']:.3f} f1={result['metrics']['f1']:.3f}",
                    tags=["qa", "model_audit"],
                    source="model_qa_specialist",
                )
                self.award_points(40, "model_audit_done")
                return {"status": "ok", "result": result}

            elif task_type == "bias":
                groups = task.get("groups", {})
                metric = task.get("metric", "accuracy")
                if not groups:
                    return {"status": "error", "error": "task.groups is required"}
                result = self.detect_bias(groups, metric)
                self.award_points(30, "bias_check_done")
                return {"status": "ok", "result": result}

            elif task_type == "drift":
                baseline = task.get("baseline_preds", [])
                current = task.get("current_preds", [])
                if not baseline or not current:
                    return {"status": "error", "error": "task.baseline_preds and task.current_preds are required"}
                result = self.check_drift(baseline, current)
                self.award_points(25, "drift_check_done")
                return {"status": "ok", "result": result}

            elif task_type == "report":
                model_name = task.get("model_name", "unknown_model")
                audit_results = task.get("audit_results", {})
                report = self.generate_audit_report(model_name, audit_results)
                self.award_points(35, "report_generated")
                return {"status": "ok", "report": report}

            else:
                # KNOWN_ISSUES bug pattern: any unmatched task_type (e.g. a
                # stray conversational question routed here) used to always
                # get this same static status/capabilities dump back,
                # regardless of what was actually asked. Real free text now
                # gets answered; a genuinely content-free structured call
                # still gets the identical status dump.
                query = (
                    (task.get("params") or {}).get("query")
                    or task.get("query")
                    or task.get("text")
                    or ""
                ).strip()
                if query:
                    answer = await self.answer_model_qa_question(query)
                    if answer:
                        self.award_points(15, "model_qa_question_answered")
                        return {"status": "ok", "response": answer}

                # Default: status report
                return {
                    "status": "ok",
                    "agent": self.name,
                    "hp": self.health_points,
                    "supported_tasks": ["audit", "bias", "drift", "report"],
                    "note": "Provide task.type=audit|bias|drift|report",
                }

        except Exception as e:
            logger.error("[VECTOR][model_qa_specialist] {}", e)
            self.deduct_points(30, "task_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        agent = ModelQASpecialist()
        assert agent.health_points == 500

        # Test audit_predictions
        import random
        random.seed(42)
        preds = [random.random() for _ in range(100)]
        labels = [1.0 if p > 0.4 else 0.0 for p in preds]
        audit = agent.audit_predictions(preds, labels)
        assert "metrics" in audit and "calibration_issues" in audit
        m = audit["metrics"]
        assert 0 <= m["accuracy"] <= 1
        assert 0 <= m["f1"] <= 1
        assert 0 <= m["ece"] <= 1
        print(f"  audit_predictions: acc={m['accuracy']:.3f} f1={m['f1']:.3f} ece={m['ece']}")

        # Test detect_bias
        groups = {
            "group_A": {"predictions": [0.8, 0.9, 0.7, 0.85], "labels": [1.0, 1.0, 1.0, 1.0]},
            "group_B": {"predictions": [0.3, 0.2, 0.4, 0.25], "labels": [1.0, 1.0, 1.0, 1.0]},
        }
        bias_result = agent.detect_bias(groups, "accuracy")
        assert "bias_detected" in bias_result and "worst_group" in bias_result
        print(f"  detect_bias: bias={bias_result['bias_detected']} disparity={bias_result['disparity_pct']}%")

        # Test check_drift
        baseline = [random.gauss(0.5, 0.1) for _ in range(200)]
        baseline = [max(0, min(1, x)) for x in baseline]
        drifted = [random.gauss(0.7, 0.1) for _ in range(200)]
        drifted = [max(0, min(1, x)) for x in drifted]
        drift = agent.check_drift(baseline, drifted)
        assert "psi" in drift and "ks_statistic" in drift and "drift_detected" in drift
        print(f"  check_drift: PSI={drift['psi']} KS={drift['ks_statistic']} drift={drift['drift_detected']}")

        # Test generate_audit_report
        report = agent.generate_audit_report("vector-policy-model", {
            "metrics": m,
            "calibration_issues": audit["calibration_issues"],
            "recommendations": audit["recommendations"],
            "bias": bias_result,
            "drift": drift,
        })
        assert "ML Model Audit Report" in report
        assert "Risk Level" in report
        print(f"  generate_audit_report: {len(report)} chars")

        # Test run dispatch
        result = await agent.run({"type": "status"})
        assert result["status"] == "ok"
        print(f"[OK] status={result['status']}")
        print("model_qa_specialist.py OK")

    asyncio.run(_smoke())
