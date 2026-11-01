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

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.loop.permission_gateway import PermissionGateway, Action


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
        self.capabilities = ["karpathy_lab", "run_experiment_cycle"]
        if ghost:
            self.inherit_ghost(ghost)

        self._gateway = PermissionGateway()
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
                if not isinstance(r.get("val_bpb"), (int, float)):
                    continue  # failed run (no score) is not a "best" result
                if best is None or r.get("val_bpb", 999) < best.get("val_bpb", 999):
                    best = r
            except json.JSONDecodeError:
                logger.debug("[VECTOR] suppressed exception", exc_info=True)
        return best

    def _save_result(self, result: dict) -> None:
        with open(self._results_file(), "a", encoding="utf-8") as f:
            f.write(json.dumps(result) + "\n")

    def _get_python_cmd(self, train_dir: str) -> list[str]:
        """Return the correct Python command: uv run if uv.lock exists, else sys.executable."""
        import os
        uv_lock = os.path.join(train_dir, "uv.lock")
        if os.path.exists(uv_lock):
            return ["uv", "run", "python"]
        return [sys.executable]

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
            python_cmd = self._get_python_cmd(str(self._runs_dir))
            cmd = python_cmd + [str(self._train_script)]
            proc = subprocess.run(
                cmd,
                cwd=str(self._runs_dir),
                capture_output=True,
                text=True,
                timeout=self.TIME_BUDGET_MINUTES * 60 + 120,
            )
            output = proc.stdout + proc.stderr
            if proc.returncode != 0:
                logger.warning(
                    "[VECTOR][autoresearch] training exited rc={}: {}",
                    proc.returncode, output[-300:],
                )
                return {}
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

    # ── Git branch management ──────────────────────────────────────────────────

    def _create_experiment_branch(self, tag: str) -> str | None:
        """Create a git branch for this experiment run. Returns branch name or None."""
        try:
            branch = f"autoresearch/{tag}"
            proc = subprocess.run(
                ["git", "checkout", "-b", branch],
                capture_output=True, check=False,
                cwd=str(Path(__file__).parent.parent.parent),
            )
            if proc.returncode != 0:
                logger.warning("[VECTOR][autoresearch] git checkout -b {} failed rc={}", branch, proc.returncode)
                return None
            logger.info("[VECTOR][autoresearch] Created experiment branch: {}", branch)
            return branch
        except Exception as e:
            logger.debug("[VECTOR][autoresearch] Could not create branch: {}", e)
            return None

    def _commit_experiment_result(self, branch: str, tag: str, result: dict) -> None:
        """Commit experiment result to git."""
        try:
            import json as _json
            cwd = str(Path(__file__).parent.parent.parent)
            subprocess.run(["git", "add", "data/training_runs/"],
                          capture_output=True, cwd=cwd)
            val_bpb = result.get("val_bpb")
            bpb_str = f"{val_bpb:.4f}" if isinstance(val_bpb, float) else str(val_bpb or "?")
            msg = f"autoresearch/{tag}: bpb={bpb_str}"
            subprocess.run(["git", "commit", "-m", msg, "--no-verify"],
                          capture_output=True, cwd=cwd)
            logger.info("[VECTOR][autoresearch] Committed result: {}", msg)
        except Exception as e:
            logger.debug("[VECTOR][autoresearch] Could not commit: {}", e)

    # ── Main experiment loop ───────────────────────────────────────────────────

    async def run_experiment_cycle(self) -> dict:
        """
        Run one full experiment cycle: baseline + up to MAX_EXPERIMENTS improvements.
        Returns summary of all experiments.

        RED-gated (58D remediation — VECTOR_TECHNICAL_KNOWLEDGE/58D_KARPATHY_
        AUTORESEARCH_PERMISSION_REMEDIATION.md, closing Task 59 Finding D):
        this whole cycle — including the baseline run of the existing
        train.py, every LLM-proposed rewrite of it, and the real local
        subprocess execution of each version — is one consequential local
        code-execution operation and is authorized as a single unit before
        any of it happens. Neither the baseline subprocess run, nor any
        write to train.py, nor any later subprocess run may occur unless
        gate_result.approved is True.
        """
        if not self._train_script.exists():
            return {"status": "no_train_script", "message": str(self._train_script)}

        try:
            gate_result = await self._gateway.execute(Action(
                action_type="run_experiment_cycle",
                params={
                    "max_experiments": self.MAX_EXPERIMENTS_PER_RUN,
                    "time_budget_minutes_per_run": self.TIME_BUDGET_MINUTES,
                    "train_script": str(self._train_script),
                    "summary": (
                        f"Run a Karpathy autoresearch cycle: a baseline run of the "
                        f"current train.py, then up to {self.MAX_EXPERIMENTS_PER_RUN} "
                        f"LLM-proposed rewrites of it (~{self.TIME_BUDGET_MINUTES} min "
                        f"each), each written to disk and executed locally as a real "
                        f"Python subprocess, unsandboxed."
                    ),
                },
                proposed_by=self.name,
            ))
        except Exception as e:
            # Fail closed — never let a gateway-unreachable condition fall
            # through to a real local write/execute (mirrors
            # hedgebot_agent.py's solana_swap_execute pattern).
            logger.error("[VECTOR][autoresearch] gateway unavailable — refusing run_experiment_cycle: {}", e)
            return {"status": "blocked", "reason": f"gateway unavailable: {e}"}

        if not gate_result.approved:
            logger.warning("[VECTOR][autoresearch] run_experiment_cycle blocked by gateway: {}", gate_result.reason)
            return {"status": "blocked", "reason": gate_result.reason}

        # Create a git branch for this experiment cycle
        cycle_tag = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        experiment_branch = self._create_experiment_branch(cycle_tag)

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
        if "val_bpb" not in baseline:
            # The baseline produced no score (crash / timeout / missing
            # summary). Never report that as a successful cycle, and never
            # let the LLM rewrite a train.py we could not even run.
            baseline["description"] = "baseline failed"
            logger.error("[VECTOR][autoresearch] baseline run failed — aborting cycle")
            return {
                "status": "training_failed",
                "reason": "baseline run produced no val_bpb",
                "experiments": len(experiments),
                "best_val_bpb": None,
                "improved": False,
                "date": datetime.date.today().isoformat(),
            }
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
            elif "val_bpb" not in result:
                result["description"] = "failed (no val_bpb) — reverted"
                self._train_script.write_text(backup, encoding="utf-8")
                logger.warning(f"[VECTOR][autoresearch] exp {i}: training failed — reverted")
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

        # Commit results to the experiment branch if one was created
        if experiment_branch:
            self._commit_experiment_result(experiment_branch, cycle_tag, summary)

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


    def _answer_karpathy_question(self, query: str) -> str:
        """Answer a free-text question about training status/architecture
        grounded in real state — never triggers a training run. This is the
        fallback for anything that doesn't explicitly ask to run a cycle."""
        best = self._load_best_result()
        rf = self._results_file()
        history_lines: list[str] = []
        if rf.exists():
            for line in rf.read_text(encoding="utf-8").splitlines()[-5:]:
                try:
                    r = json.loads(line)
                    history_lines.append(
                        f"exp {r.get('experiment', '?')}: val_bpb={r.get('val_bpb', '?')} — {r.get('description', '')}"
                    )
                except json.JSONDecodeError:
                    continue

        context = (
            f"Best val_bpb today: {best.get('val_bpb') if best else 'no runs yet'}. "
            f"train.py present: {self._train_script.exists()}. "
            f"Recent experiments:\n" + ("\n".join(history_lines) if history_lines else "none yet")
        )
        prompt = (
            f"You are VECTOR's Karpathy autoresearch lab assistant. Answer the owner's "
            f"question using ONLY this real state — do not invent numbers:\n\n{context}\n\n"
            f"Question: {query}\n\nBe concise and specific."
        )
        try:
            from core.inference.vectorcode_llm import chat
            result = chat(
                model=CONFIG["models"]["reasoning"],
                messages=[{"role": "user", "content": prompt}],
                timeout=45.0,
            )
            return result or context
        except Exception as e:
            logger.warning(f"[VECTOR][autoresearch] answer generation failed: {e}")
            return context

    async def run(self, task: dict) -> dict:
        # 2026-07-28: run() used to unconditionally call
        # run_experiment_cycle() for EVERY dispatch regardless of
        # task["type"] — a stray free-text chat message classified into
        # karpathy_lab could trigger a real training subprocess, LLM-driven
        # mutation of train.py, and a git commit. Now gated behind an
        # explicit task_type; everything else gets a real answer grounded
        # in actual training history, never a side-effecting action.
        p = task.get("params", {})
        task_type = task.get("type", "")
        if task_type == "run_experiment_cycle":
            result = await self.run_experiment_cycle()
            return {"status": "ok", **result}

        query = p.get("query") or p.get("content") or task.get("query") or task.get("text") or ""
        if query:
            return {"status": "ok", "response": self._answer_karpathy_question(query)}

        # No real question and no explicit run request — report status,
        # same grounded data the answer path uses, no training triggered.
        best = self._load_best_result()
        return {
            "status": "ok",
            "response": f"Best val_bpb today: {best.get('val_bpb') if best else 'no runs yet'}.",
        }


if __name__ == "__main__":
    import tempfile
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        runner = AutoresearchRunner(generation=1)
        assert runner.name == "AutoresearchRunner"
        assert runner.district == "karpathy_lab"

        # Smoke: either no train.py (graceful status, pre-gate) or train.py
        # exists and the 58D RED gate correctly refuses without real owner
        # approval (this script runs no mocks and taps nothing, so an
        # unapproved RED request must come back "blocked", never proceed to
        # a real write/execute) — both are safe, side-effect-free outcomes.
        # Which branch fires depends on whether this machine already has a
        # train.py at runner._train_script (a real, valid environment state,
        # not something this smoke test should assume away).
        result = await runner.run_experiment_cycle()
        assert result.get("status") in ("no_train_script", "blocked"), result

        summary = runner._parse_training_output(
            "---\nval_bpb:          0.9979\ntraining_seconds: 300.1\npeak_vram_mb:     45060.2\n---"
        )
        assert abs(summary["val_bpb"] - 0.9979) < 0.001

        # run() must NOT trigger a real training cycle for a free-text
        # question — only an explicit task_type="run_experiment_cycle" may.
        r = await runner.run({"type": "chat", "params": {"query": "how is training going?"}})
        assert r["status"] == "ok" and "response" in r
        r2 = await runner.run({"type": "chat", "params": {}})
        assert r2["status"] == "ok" and "response" in r2

        print(f"✅ autoresearch_runner OK  HP={runner.health_points}")

    asyncio.run(_smoke())
