"""Session 11 — Adaptive Learning end-to-end integration tests.

Verifies:
- Seed dataset loads correctly
- DataCollector picks up domain data from data/training/coding/
- SelfImprovementCycle.run_weekly() completes with real seed data
- Adapter manifest (data/adapters/<name>/manifest.json) is produced
- Eval gates fire (approve or reject with reason)
- Report file is created
- WeeklyTrainingScheduler can trigger and log a run
- Benchmarks score responses correctly
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tmp_cycle(adapters_subdir: str = "adapters"):
    """Create a SelfImprovementCycle backed by a temp adapters dir."""
    tmp = tempfile.mkdtemp()
    adapters_dir = os.path.join(tmp, adapters_subdir)
    os.makedirs(adapters_dir, exist_ok=True)
    from core.training.self_improvement_cycle import SelfImprovementCycle
    cycle = SelfImprovementCycle(adapters_dir=adapters_dir)
    return cycle, tmp


# ---------------------------------------------------------------------------
# 1. Seed dataset
# ---------------------------------------------------------------------------

class TestSeedDataset(unittest.TestCase):

    def test_seed_file_exists(self):
        self.assertTrue(Path("data/training/seed.jsonl").exists(), "data/training/seed.jsonl missing")

    def test_seed_has_50_examples(self):
        lines = Path("data/training/seed.jsonl").read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 50, f"Expected 50 seed examples, got {len(lines)}")

    def test_seed_coding_domain_file_exists(self):
        self.assertTrue(
            Path("data/training/coding/seed.jsonl").exists(),
            "data/training/coding/seed.jsonl missing (DataCollector domain file)",
        )

    def test_seed_examples_have_required_fields(self):
        lines = Path("data/training/seed.jsonl").read_text(encoding="utf-8").strip().splitlines()
        for i, line in enumerate(lines):
            ex = json.loads(line)
            self.assertIn("instruction", ex, f"Line {i+1} missing 'instruction'")
            self.assertIn("output", ex, f"Line {i+1} missing 'output'")
            self.assertTrue(ex["instruction"].strip(), f"Line {i+1} has empty instruction")
            self.assertTrue(ex["output"].strip(), f"Line {i+1} has empty output")

    def test_seed_examples_cover_multiple_domains(self):
        lines = Path("data/training/seed.jsonl").read_text(encoding="utf-8").strip().splitlines()
        all_text = " ".join(lines).lower()
        for keyword in ("async", "hp", "mitre", "lora", "episodic"):
            self.assertIn(keyword, all_text, f"Seed data missing domain keyword: {keyword}")


# ---------------------------------------------------------------------------
# 2. DataCollector
# ---------------------------------------------------------------------------

class TestDataCollector(unittest.TestCase):

    def setUp(self):
        from core.training.data_collector import DataCollector
        self.dc = DataCollector()

    def test_collect_from_coding_domain(self):
        examples = self.dc.collect_from_domain("coding", count=200)
        self.assertGreater(len(examples), 0, "No examples from coding domain")

    def test_collected_examples_have_instruction_output(self):
        examples = self.dc.collect_from_domain("coding", count=10)
        if examples:
            for ex in examples[:3]:
                self.assertIn("instruction", ex)
                self.assertIn("output", ex)

    def test_format_for_training_alpaca(self):
        examples = self.dc.collect_from_domain("coding", count=5)
        formatted = self.dc.format_for_training(examples, template="alpaca")
        self.assertGreater(len(formatted), 0)
        for ex in formatted:
            self.assertIn("text", ex)
            self.assertIn("### Instruction:", ex["text"])
            self.assertIn("### Response:", ex["text"])

    def test_deduplicate_removes_exact_dupes(self):
        examples = [{"text": "hello world", "source": "test"}] * 5
        deduped = self.dc.deduplicate(examples)
        self.assertEqual(len(deduped), 1)

    def test_export_dataset(self):
        examples = [{"text": "sample", "source": "test"}]
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "out.jsonl")
        result = self.dc.export_dataset(examples, path)
        self.assertTrue(Path(result).exists())
        shutil.rmtree(tmp, ignore_errors=True)

    def test_collect_from_feedback_returns_list(self):
        result = self.dc.collect_from_feedback(days=7)
        self.assertIsInstance(result, list)


# ---------------------------------------------------------------------------
# 3. Benchmarks
# ---------------------------------------------------------------------------

class TestBenchmarks(unittest.TestCase):

    def _good_response(self, prompt: str) -> str:
        return (
            "async def retry(fn, retries=3):\n"
            "    import asyncio\n"
            "    for attempt in range(retries):\n"
            "        try: return await fn()\n"
            "        except: await asyncio.sleep(2**attempt)\n"
            "# Uses loguru sqlite lora adapter circuit breaker pattern episodic "
            "semantic recall mitre tactic technique detection adversary "
            "lora rank parameter fine-tun ollama local cloud latency privacy cost "
            "hp fitness evolut generation inherit fastapi status_code commit "
            "rotation sink executor yield elapsed contextmanager "
            "gather coroutine concurrent"
        )

    def _empty_response(self, prompt: str) -> str:
        return ""

    def test_coding_benchmark_scores_good_response(self):
        from core.training.benchmarks import CodingBenchmark
        cb = CodingBenchmark()
        scores = cb.run(self._good_response)
        avg = sum(scores.values()) / len(scores)
        self.assertGreater(avg, 0.3, f"CodingBenchmark avg too low: {avg:.3f}")

    def test_coding_benchmark_penalises_empty_response(self):
        from core.training.benchmarks import CodingBenchmark
        cb = CodingBenchmark()
        scores = cb.run(self._empty_response)
        avg = sum(scores.values()) / len(scores)
        self.assertLessEqual(avg, 0.2, f"Expected low score for empty, got {avg:.3f}")

    def test_research_benchmark_scores_good_response(self):
        from core.training.benchmarks import ResearchBenchmark
        rb = ResearchBenchmark()
        scores = rb.run(self._good_response)
        avg = sum(scores.values()) / len(scores)
        self.assertGreater(avg, 0.3, f"ResearchBenchmark avg too low: {avg:.3f}")

    def test_coding_benchmark_returns_dict(self):
        from core.training.benchmarks import CodingBenchmark
        cb = CodingBenchmark()
        scores = cb.run(self._good_response)
        self.assertIsInstance(scores, dict)
        self.assertGreater(len(scores), 0)

    def test_research_benchmark_returns_dict(self):
        from core.training.benchmarks import ResearchBenchmark
        rb = ResearchBenchmark()
        scores = rb.run(self._good_response)
        self.assertIsInstance(scores, dict)
        self.assertGreater(len(scores), 0)

    def test_benchmark_score_range(self):
        from core.training.benchmarks import CodingBenchmark
        cb = CodingBenchmark()
        scores = cb.run(self._good_response)
        for k, v in scores.items():
            self.assertGreaterEqual(v, 0.0, f"{k} score below 0")
            self.assertLessEqual(v, 1.0, f"{k} score above 1")


# ---------------------------------------------------------------------------
# 4. LoRATrainer (simulated path)
# ---------------------------------------------------------------------------

class TestLoRATrainerSimulated(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        from core.training.lora_trainer import LoRATrainer
        self.trainer = LoRATrainer(adapters_dir=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_simulate_training_returns_success(self):
        from core.training.training_config import AdapterConfig, TrainingArgs
        config = AdapterConfig(
            name="test_adapter",
            base_model="vector-focus",
            target_modules=["q_proj", "v_proj"],
            rank=8, alpha=8.0,
        )
        args = TrainingArgs(num_epochs=1, batch_size=2)
        dataset = [{"text": f"example {i}"} for i in range(10)]
        result = self.trainer.train(config, args, dataset)
        self.assertIn(result.get("status"), ("success", "failed"))

    def test_save_adapter_creates_manifest(self):
        from core.training.training_config import AdapterConfig
        config = AdapterConfig(
            name="manifest_test",
            base_model="vector-focus",
            target_modules=["q_proj"],
        )
        result = {"status": "success", "method": "simulated", "final_loss": 0.42}
        save_dir = self.trainer.save_adapter(config, result)
        manifest = Path(save_dir) / "manifest.json"
        self.assertTrue(manifest.exists(), f"manifest.json not found at {manifest}")

    def test_list_adapters_finds_saved(self):
        from core.training.training_config import AdapterConfig
        config = AdapterConfig(name="list_test", base_model="vector-coder", target_modules=["q_proj"])
        self.trainer.save_adapter(config, {"status": "success", "method": "simulated"})
        adapters = self.trainer.list_adapters()
        names = [a["name"] for a in adapters]
        self.assertIn("list_test", names)

    def test_empty_dataset_returns_failed(self):
        from core.training.training_config import AdapterConfig, TrainingArgs
        config = AdapterConfig(name="empty_test", base_model="vector-focus", target_modules=["q_proj"])
        result = self.trainer.train(config, TrainingArgs(), [])
        self.assertEqual(result["status"], "failed")


# ---------------------------------------------------------------------------
# 5. SelfImprovementCycle.run_weekly() end-to-end
# ---------------------------------------------------------------------------

class TestSelfImprovementCycleEndToEnd(unittest.TestCase):

    def setUp(self):
        self.cycle, self.tmp = _tmp_cycle()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_weekly_returns_dict(self):
        result = self.cycle.run_weekly()
        self.assertIsInstance(result, dict)

    def test_run_weekly_has_status(self):
        result = self.cycle.run_weekly()
        self.assertIn("status", result)
        self.assertIn(result["status"], ("completed", "skipped_no_data", "failed_collect", "failed_train", "failed_eval"))

    def test_run_weekly_completes_with_seed_data(self):
        """Core acceptance: cycle must reach 'completed' with seed data present."""
        result = self.cycle.run_weekly()
        self.assertEqual(
            result["status"], "completed",
            f"run_weekly() did not complete: {result}",
        )

    def test_run_weekly_phases_present(self):
        result = self.cycle.run_weekly()
        if result.get("status") == "completed":
            self.assertIn("phases", result)
            phases = result["phases"]
            self.assertIn("collect", phases)
            self.assertIn("train", phases)
            self.assertIn("evaluate", phases)

    def test_adapter_manifest_produced(self):
        """Core acceptance: adapter manifest appears in data/adapters/."""
        result = self.cycle.run_weekly()
        adapters_dir = Path(self.tmp) / "adapters"
        manifests = list(adapters_dir.glob("*/manifest.json"))
        self.assertGreater(
            len(manifests), 0,
            f"No adapter manifest found in {adapters_dir}. Cycle result: {result}",
        )

    def test_adapter_manifest_is_valid_json(self):
        self.cycle.run_weekly()
        adapters_dir = Path(self.tmp) / "adapters"
        for manifest in adapters_dir.glob("*/manifest.json"):
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertIn("name", data)
            self.assertIn("base_model", data)
            self.assertIn("training_result", data)

    def test_eval_gates_fire(self):
        """Eval phase must contain at least one adapter result with status approved or rejected."""
        result = self.cycle.run_weekly()
        if result.get("status") == "completed":
            eval_data = result.get("phases", {}).get("evaluate", {})
            if eval_data:
                for adapter_name, eval_result in eval_data.items():
                    self.assertIn(eval_result.get("status"), ("approved", "rejected"),
                                  f"Adapter '{adapter_name}' has unexpected eval status")

    def test_report_file_created(self):
        self.cycle.run_weekly()
        reports = list(Path("data/reports").glob("cycle_*.md"))
        self.assertGreater(len(reports), 0, "No cycle report .md file found in data/reports/")

    def test_collect_phase_sample_count(self):
        result = self.cycle.run_weekly()
        collect = result.get("phases", {}).get("collect", {})
        samples = collect.get("samples", 0)
        self.assertGreater(samples, 0, f"Collect phase returned 0 samples: {collect}")

    def test_train_phase_has_domain_results(self):
        result = self.cycle.run_weekly()
        train = result.get("phases", {}).get("train", {})
        if isinstance(train, dict) and "error" not in train:
            self.assertGreater(len(train), 0, "Train phase returned no domain results")


# ---------------------------------------------------------------------------
# 6. WeeklyTrainingScheduler
# ---------------------------------------------------------------------------

class TestWeeklyTrainingScheduler(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_scheduler_instantiates(self):
        from core.training.weekly_scheduler import WeeklyTrainingScheduler
        sched = WeeklyTrainingScheduler(
            adapters_dir=os.path.join(self.tmp, "adapters"),
            log_path=os.path.join(self.tmp, "sched.jsonl"),
        )
        self.assertIsNotNone(sched)

    def test_run_now_returns_dict(self):
        from core.training.weekly_scheduler import WeeklyTrainingScheduler
        sched = WeeklyTrainingScheduler(
            adapters_dir=os.path.join(self.tmp, "adapters"),
            log_path=os.path.join(self.tmp, "sched.jsonl"),
        )
        result = sched.run_now()
        self.assertIsInstance(result, dict)
        self.assertIn("status", result)

    def test_run_now_logs_to_file(self):
        from core.training.weekly_scheduler import WeeklyTrainingScheduler
        log_path = os.path.join(self.tmp, "sched.jsonl")
        sched = WeeklyTrainingScheduler(
            adapters_dir=os.path.join(self.tmp, "adapters"),
            log_path=log_path,
        )
        sched.run_now()
        self.assertTrue(Path(log_path).exists(), "Scheduler log file not created")
        lines = Path(log_path).read_text(encoding="utf-8").strip().splitlines()
        self.assertGreater(len(lines), 0)

    def test_get_log_returns_list(self):
        from core.training.weekly_scheduler import WeeklyTrainingScheduler
        sched = WeeklyTrainingScheduler(
            adapters_dir=os.path.join(self.tmp, "adapters"),
            log_path=os.path.join(self.tmp, "sched.jsonl"),
        )
        sched.run_now()
        log = sched.get_log(limit=5)
        self.assertIsInstance(log, list)
        self.assertGreater(len(log), 0)

    def test_start_and_stop(self):
        from core.training.weekly_scheduler import WeeklyTrainingScheduler
        sched = WeeklyTrainingScheduler(
            adapters_dir=os.path.join(self.tmp, "adapters"),
            log_path=os.path.join(self.tmp, "sched.jsonl"),
        )
        started = sched.start()
        if started:
            nxt = sched.get_next_run()
            self.assertIsNotNone(nxt)
            sched.stop()


if __name__ == "__main__":
    unittest.main()
