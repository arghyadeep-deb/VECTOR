"""
Karpathy autoresearch loop — self-improving training experiments.

Pattern from Karpathy's autoresearch repo (integrated into VECTOR):
  1. Run current train.py baseline for fixed time budget
  2. Ask vector-reasoning to propose one architectural improvement
  3. Apply change to train.py
  4. Re-run, compare val_bpb
  5. Keep if improved; revert if not (Simplicity criterion: simpler > complex for equal improvement)
  6. Log all experiments to progress_tracker / episodic memory / Obsidian

RULE 12: Complement to manual CodeTyper sessions — runner does autonomous
         overnight experiments while user types manually during the day.
"""
import sys
import uuid
import json
import asyncio
import datetime
import subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


class AutoresearchRunner(AgentBase):
    """
    Autonomous nanoGPT experimentation loop.
    Runs timed training experiments and proposes/evaluates architectural improvements.
    RULE 2 — never crashes. RULE 8 — stores every result as reasoning chain.
    """

    TIME_BUDGET_MINUTES: int = 5   # Match Karpathy's fixed 5-min training budget
    MAX_EXPERIMENTS_PER_RUN: int = 3

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="AutoresearchRunner",
            district="karpathy_lab",
            generation=generation,
        )
        if ghost:
            self.inherit_ghost(ghost)

        self._runs_dir = Path(CONFIG["karpathy"]["runs_dir"])
        self._data_dir = Path(CONFIG["karpathy"]["data_dir"])
        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._memory = None
        self._train_script = self._runs_dir / "train.py"
        logger.info(
            f"[VECTOR][autoresearch] ready gen={generation} hp={self.health_points} "
            f"train={self._train_script}"
        )

    def _get_memory(self):
        if self._memory is None:
            from core.memory.episodic import EpisodicMemory
            self._memory = EpisodicMemory()
        return self._memory

    # ── Experiment management ─────────────────────────────────────────────────

    def _results_file(self) -> Path:
        date = datetime.date.today().isoformat()
        return self._runs_dir / f"results_{date}.jsonl"

    def _load_best_result(self) -> dict | None:
        """Load the best val_bpb result seen so far from today's results."""
        rf = self._results_file()
        if not rf.exists():
            return None
        best = None
        for line in rf.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                if best is None or r.get("val_bpb", 999) < best.get("val_bpb", 999):
                    best = r
            except json.JSONDecodeError:
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        return best

    def _save_result(self, result: dict) -> None:
        with open(self._results_file(), "a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")

    def _run_training(self) -> dict:
        """
        Execute train.py for TIME_BUDGET_MINUTES and parse the summary output.
        Returns dict with val_bpb, training_seconds, peak_vram_mb.
        """
        if not self._train_script.exists():
            logger.warning(
                f"[VECTOR][autoresearch] train.py not found at {self._train_script}. "
                "Run: python -m karpathy_autoresearch.prepare first, then copy train.py here."
            )
            return {}

        try:
            proc = subprocess.run(
                [sys.executable, str(self._train_script)],
                cwd=str(self._runs_dir),
                capture_output=True,
                text=True,
                timeout=self.TIME_BUDGET_MINUTES * 60 + 120,
            )
            output = proc.stdout + proc.stderr
            return self._parse_training_output(output)
        except subprocess.TimeoutExpired:
            logger.warning("[VECTOR][autoresearch] training timeout")
            return {}
        except Exception as e:
            logger.error(f"[VECTOR][autoresearch] training run failed: {e}")
            return {}

    @staticmethod
    def _parse_training_output(output: str) -> dict:
        """Parse Karpathy autoresearch summary block from stdout."""
        result = {}
        in_block = False
        for line in output.splitlines():
            line = line.strip()
            if line == "---":
                in_block = not in_block
                continue
            if in_block and ":" in line:
                key, _, val = line.partition(":")
                try:
                    result[key.strip()] = float(val.strip())
                except ValueError:
                    logger.debug("[VECTOR] suppressed exception", exc_info=True)
        return result

    def _propose_improvement(self, train_code: str, history: list[dict]) -> str:
        """Ask vector-reasoning to propose one architectural change to train.py."""
        history_str = json.dumps(history[-3:], indent=2) if history else "No history yet."
        hydration = ""
        try:
            from core.loop.context_engine import ContextEngine
            hydration = ContextEngine().session_hydration_prompt()
        except Exception:
            logger.debug("[VECTOR] suppressed exception", exc_info=True)

        prompt = (
            f"You are improving a nanoGPT training script. Goal: lower val_bpb.\n\n"
            f"Current train.py:\n```python\n{train_code[:3000]}\n```\n\n"
            f"Recent experiment history (val_bpb scores):\n{history_str}\n\n"
            "Propose ONE specific change to the Python code. Rules:\n"
            "- Only modify train.py (not prepare.py)\n"
            "- No new packages\n"
            "- Simpler is better for equal improvement\n"
            "- Reply with ONLY the complete modified train.py code"
        )

        try:
            from core.inference.vectorcode_llm import chat
            result = chat(
                model=CONFIG["models"]["reasoning"],
                messages=[
                    {"role": "system", "content": hydration or "You are a ML researcher."},
                    {"role": "user", "content": prompt},
                ],
                timeout=120.0,
            )
            return result or ""
        except Exception as e:
            logger.warning(f"[VECTOR][autoresearch] proposal generation failed: {e}")
            return ""

    # ── Main experiment loop ───────────────────────────────────────────────────

    async def run_experiment_cycle(self) -> dict:
        """
        Run one full experiment cycle: baseline + up to MAX_EXPERIMENTS improvements.
        Returns summary of all experiments.
        """
        if not self._train_script.exists():
            return {"status": "no_train_script", "message": str(self._train_script)}

        experiments = []
        original_code = self._train_script.read_text(encoding="utf-8")
        best_code = original_code

        # Baseline run
        logger.info("[VECTOR][autoresearch] running baseline...")
        baseline = self._run_training()
        baseline["experiment"] = 0
        baseline["description"] = "baseline"
        baseline["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self._save_result(baseline)
        experiments.append(baseline)
        best_bpb = baseline.get("val_bpb", float("inf"))
        logger.info(f"[VECTOR][autoresearch] baseline val_bpb={best_bpb:.4f}")

        # Improvement iterations
        for i in range(1, self.MAX_EXPERIMENTS_PER_RUN + 1):
            logger.info(f"[VECTOR][autoresearch] experiment {i}/{self.MAX_EXPERIMENTS_PER_RUN}")
            proposed_code = self._propose_improvement(best_code, experiments)
            if not proposed_code or "def " not in proposed_code:
                logger.warning("[VECTOR][autoresearch] no valid proposal — stopping")
                break

            # Extract Python code block if wrapped in markdown
            if "```python" in proposed_code:
                proposed_code = proposed_code.split("```python")[1].split("```")[0].strip()

            # Back up and apply
            backup = self._train_script.read_text(encoding="utf-8")
            self._train_script.write_text(proposed_code, encoding="utf-8")

            result = self._run_training()
            result["experiment"] = i
            result["timestamp"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            new_bpb = result.get("val_bpb", float("inf"))

            if new_bpb < best_bpb:
                improvement = best_bpb - new_bpb
                result["description"] = f"improved ({improvement:.4f} better)"
                best_bpb = new_bpb
                best_code = proposed_code
                self.award_points(30, f"autoresearch improvement {improvement:.4f}")
                logger.info(f"[VECTOR][autoresearch] exp {i}: IMPROVED → {new_bpb:.4f}")
            else:
                result["description"] = f"reverted (was {new_bpb:.4f}, best {best_bpb:.4f})"
                self._train_script.write_text(backup, encoding="utf-8")
                logger.info(f"[VECTOR][autoresearch] exp {i}: no improvement — reverted")

            self._save_result(result)
            experiments.append(result)
            await asyncio.sleep(0)  # yield control

        # If best isn't the original, write it permanently
        if best_code != original_code:
            self._train_script.write_text(best_code, encoding="utf-8")

        summary = {
            "experiments": len(experiments),
            "best_val_bpb": best_bpb,
            "improved": best_bpb < experiments[0].get("val_bpb", float("inf")),
            "date": datetime.date.today().isoformat(),
        }

        # RULE 8 — store reasoning chain
        try:
            self._get_memory().store_chain(
                situation="autoresearch_cycle",
                goal_ids=["karpathy_training"],
                steps=[f"exp_{e['experiment']}: {e.get('description','')}" for e in experiments],
                action="run_experiment_cycle",
                outcome=f"best_val_bpb={best_bpb:.4f} over {len(experiments)} experiments",
                reward=0.8 if summary["improved"] else 0.5,
            )
        except Exception as e:
            logger.warning(f"[VECTOR][autoresearch] chain store failed: {e}")

        logger.info(f"[VECTOR][autoresearch] cycle done — {summary}")
        return summary


    async def run(self, task: dict) -> dict:
        result = await self.run_experiment_cycle()
        return {"status": "ok", **result}


if __name__ == "__main__":
    import tempfile
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        runner = AutoresearchRunner(generation=1)
        assert runner.name == "AutoresearchRunner"
        assert runner.district == "karpathy_lab"

        # Smoke: no train.py → returns graceful status
        result = await runner.run_experiment_cycle()
        assert result.get("status") == "no_train_script"

        summary = runner._parse_training_output(
            "---\nval_bpb:          0.9979\ntraining_seconds: 300.1\npeak_vram_mb:     45060.2\n---"
        )
        assert abs(summary["val_bpb"] - 0.9979) < 0.001

        print(f"✅ autoresearch_runner OK  HP={runner.health_points}")

    asyncio.run(_smoke())
