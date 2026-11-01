"""Self-improvement cycle: collect → train → evaluate → deploy."""

import json
from pathlib import Path
from datetime import datetime

from loguru import logger
from core.runtime_paths import data_path
from core.training.training_config import AdapterConfig, TrainingArgs, EvalConfig
from core.training.data_collector import DataCollector
from core.training.lora_trainer import LoRATrainer
from core.training.eval_harness import EvalHarness
from core.training.benchmarks import CodingBenchmark, ResearchBenchmark


class SelfImprovementCycle:
    def __init__(self, adapters_dir: str | None = None):
        self.data_collector = DataCollector()
        self.trainer = LoRATrainer(adapters_dir or str(data_path("adapters")))
        self.eval_harness = EvalHarness()
        self.eval_harness.register_benchmark("coding", CodingBenchmark)
        self.eval_harness.register_benchmark("research", ResearchBenchmark)
        self.reports_dir = data_path("reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        logger.info("[Training] SelfImprovementCycle initialized")

    def run_weekly(self) -> dict:
        logger.info("[Training] Starting weekly self-improvement cycle")
        results = {"timestamp": datetime.now().isoformat(), "phases": {}}
        try:
            data = self._collect_training_data()
            results["phases"]["collect"] = {"samples": len(data)}
            if not data:
                logger.warning("[Training] No data collected, aborting cycle")
                results["status"] = "skipped_no_data"
                return results
        except Exception as e:
            logger.error("[Training] Data collection failed: {}", e)
            results["phases"]["collect"] = {"error": str(e)}
            results["status"] = "failed_collect"
            return results
        try:
            train_result = self._train_adapters(data)
            results["phases"]["train"] = train_result
        except Exception as e:
            logger.error("[Training] Training failed: {}", e)
            results["phases"]["train"] = {"error": str(e)}
            results["status"] = "failed_train"
            return results
        try:
            eval_result = self._evaluate_adapters()
            results["phases"]["evaluate"] = eval_result
        except Exception as e:
            logger.error("[Training] Evaluation failed: {}", e)
            results["phases"]["evaluate"] = {"error": str(e)}
            results["status"] = "failed_eval"
            return results
        try:
            deploy_result = self._deploy_best(eval_result)
            results["phases"]["deploy"] = deploy_result
        except Exception as e:
            logger.error("[Training] Deployment failed: {}", e)
            results["phases"]["deploy"] = {"error": str(e)}
        try:
            report = self._generate_report(results)
            results["report_path"] = report
        except Exception as e:
            logger.error("[Training] Report generation failed: {}", e)
        results["status"] = "completed"
        logger.info("[Training] Self-improvement cycle completed")
        return results

    def _collect_training_data(self) -> list[dict]:
        logger.info("[Training] Phase 1/4: Collecting training data")
        episodic = self.data_collector.collect_from_episodic_memory(days=30, min_reward=0.7)
        feedback = self.data_collector.collect_from_feedback(days=7)
        domain_coding = self.data_collector.collect_from_domain("coding", count=200)
        combined = episodic + feedback + domain_coding
        formatted = self.data_collector.format_for_training(combined, template="alpaca")
        deduped = self.data_collector.deduplicate(formatted)
        logger.info("[Training] Collected {} total samples ({} after dedup)", len(combined), len(deduped))
        return deduped

    def _train_adapters(self, data: list[dict]) -> dict:
        logger.info("[Training] Phase 2/4: Training adapters")
        domains = {
            "coding_general": AdapterConfig(
                name="coding_v1", base_model="vector-coder",
                target_modules=["q_proj", "v_proj"], rank=16, alpha=16.0, dropout=0.05,
                save_dir=str(self.trainer.adapters_dir),
            ),
            "research_assist": AdapterConfig(
                name="research_v1", base_model="vector-focus",
                target_modules=["q_proj", "v_proj"], rank=8, alpha=8.0, dropout=0.05,
                save_dir=str(self.trainer.adapters_dir),
            ),
        }
        train_args = TrainingArgs(learning_rate=2e-4, num_epochs=3, batch_size=4)
        results = {}
        for domain, config in domains.items():
            logger.info("[Training] Training adapter for '{}'", domain)
            result = self.trainer.train(config, train_args, data[:500])
            if result.get("status") == "success":
                self.trainer.save_adapter(config, result)
            results[domain] = result
        return results

    def _evaluate_adapters(self) -> dict:
        logger.info("[Training] Phase 3/4: Evaluating adapters")
        adapters = self.trainer.list_adapters()
        results = {}
        rejected_dir = data_path("rejected_runs")
        rejected_dir.mkdir(parents=True, exist_ok=True)
        for adapter in adapters:
            name = adapter.get("name", "unknown")
            base = adapter.get("base_model", "")
            result = self.eval_harness.evaluate(model_name=base, adapter_name=name)
            train_result = adapter.get("training_result", {})
            val_loss = float(train_result.get("val_loss", 0))
            initial_loss = float(train_result.get("initial_loss", 1))

            # Phase 4C: Eval gates — reject regressions
            rejection_reason = None
            if initial_loss > 0 and val_loss > 1.5 * initial_loss:
                rejection_reason = f"val_loss {val_loss:.3f} > 1.5x initial {initial_loss:.3f}"
            elif result.overall_score < 0.5:
                rejection_reason = f"overall_score {result.overall_score:.2f} < 0.5 baseline"

            if rejection_reason:
                logger.warning(f"[Training] Adapter '{name}' REJECTED: {rejection_reason}")
                import json as _json, time as _time
                reject_path = rejected_dir / f"{name}_{int(_time.time())}.json"
                reject_path.write_text(_json.dumps({
                    "adapter": name, "reason": rejection_reason,
                    "val_loss": val_loss, "initial_loss": initial_loss,
                    "score": result.overall_score,
                }, indent=2))
                results[name] = {"status": "rejected", "reason": rejection_reason}
                continue

            results[name] = {
                "status": "approved",
                "overall_score": result.overall_score,
                "num_prompts": result.num_prompts,
                "benchmark_results": result.benchmark_results,
            }
            logger.info("[Training] Adapter '{}' overall score: {:.2f}", name, result.overall_score)
        return results

    @staticmethod
    def _final_loss_rank(adapter: dict) -> tuple[int, float]:
        """Sort key: lowest final_loss first; missing/None/invalid loss ranks last."""
        train_result = adapter.get("training_result") or {}
        try:
            loss = float(train_result.get("final_loss"))
        except (TypeError, ValueError):
            return (1, 0.0)
        if loss != loss:  # NaN
            return (1, 0.0)
        return (0, loss)

    def _deploy_best(self, evaluation_results: dict | None = None) -> dict:
        logger.info("[Training] Phase 4/4: Deploying best adapter")
        adapters = self.trainer.list_adapters()
        if not adapters:
            logger.warning("[Training] No adapters to deploy")
            return {"deployed": False, "reason": "no_adapters"}
        evaluation_results = evaluation_results or {}
        eligible = [
            adapter for adapter in adapters
            if (adapter.get("training_result") or {}).get("status") == "success"
            and (adapter.get("training_result") or {}).get("method") in {"peft", "unsloth"}
            and (evaluation_results.get(adapter.get("name")) or {}).get("status") == "approved"
        ]
        best = min(eligible, key=self._final_loss_rank, default=None)
        if best:
            name = best.get("name", "unknown")
            save_path = str(self.trainer.adapters_dir / name)
            deployed = self.trainer.deploy_to_ollama(save_path)
            return {"deployed": deployed, "adapter": name, "path": save_path}
        logger.warning("[Training] No approved real adapter to deploy")
        return {"deployed": False, "reason": "no_eligible_adapter"}

    def _generate_report(self, results: dict) -> str:
        lines = [
            "# Self-Improvement Cycle Report",
            "",
            f"**Timestamp:** {results.get('timestamp', 'unknown')}",
            f"**Status:** {results.get('status', 'unknown')}",
            "",
            "## Data Collection",
        ]
        collect = results.get("phases", {}).get("collect", {})
        lines.append(f"- Samples collected: {collect.get('samples', 'N/A')}")
        lines.append("")
        lines.append("## Training")
        train = results.get("phases", {}).get("train", {})
        for domain, result in train.items():
            status = result.get("status", "unknown")
            method = result.get("method", "N/A")
            samples = result.get("train_samples", "N/A")
            lines.append(f"- **{domain}**: status={status}, method={method}, samples={samples}")
        lines.append("")
        lines.append("## Evaluation")
        eval_data = results.get("phases", {}).get("evaluate", {})
        for name, data in eval_data.items():
            lines.append(f"- **{name}**: score={data.get('overall_score', 'N/A')}")
        lines.append("")
        lines.append("## Deployment")
        deploy = results.get("phases", {}).get("deploy", {})
        lines.append(f"- Deployed: {deploy.get('deployed', False)}")
        if deploy.get("adapter"):
            lines.append(f"- Adapter: {deploy['adapter']}")
        report_path = self.reports_dir / f"cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        report_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("[Training] Report saved to {}", report_path)
        return str(report_path)
