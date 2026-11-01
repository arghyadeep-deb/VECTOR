"""
Experiment Tracker — manages A/B experiments on VECTOR's own behaviors.

Tracks hypotheses, runs controlled experiments, measures outcomes,
and generates evidence-based recommendations for improving VECTOR.
"""

import asyncio
import datetime
import json
import os
import tempfile
from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.inference.vectorcode_llm import chat

class ExperimentTracker(AgentBase):
    """
    Designs and tracks controlled experiments on VECTOR's behaviors.
    Hypothesis → Design → Run → Measure → Conclude.
    """

    _EXPERIMENTS_FILE = Path.home() / ".vector" / "experiments.json"

    def __init__(self):
        super().__init__(agent_id="experiment_tracker_001", name="ExperimentTracker", district="projects")
        self.capabilities = ["analyze", "create", "experiment", "observe", "project", "seed", "tracking"]
        self._memory: EpisodicMemory | None = None
        self._obsidian: ObsidianSync | None = None
        self._model = CONFIG.get("models", {}).get("reasoning", "vector-reasoning")
        logger.info("[VECTOR][experiment_tracker] initialized")

    def _get_memory(self):
        if self._memory is None:
            self._memory = EpisodicMemory()
        return self._memory

    def _get_obsidian(self):
        if self._obsidian is None:
            self._obsidian = ObsidianSync()
        return self._obsidian

    def _load_experiments(self) -> dict:
        """Load experiment registry from disk."""
        self._EXPERIMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not self._EXPERIMENTS_FILE.exists():
            return {"experiments": [], "next_id": 1}
        try:
            return json.loads(self._EXPERIMENTS_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            # Don't let the next save silently overwrite (and destroy) an
            # unreadable registry: keep a copy of the bad file first.
            logger.error("[VECTOR][experiment_tracker] registry unreadable, starting empty: {}", e)
            try:
                bak = self._EXPERIMENTS_FILE.with_suffix(".corrupt.json")
                bak.write_bytes(self._EXPERIMENTS_FILE.read_bytes())
            except Exception as be:
                logger.warning("[VECTOR][experiment_tracker] corrupt-registry backup failed: {}", be)
            return {"experiments": [], "next_id": 1}

    def _save_experiments(self, data: dict) -> bool:
        """Persist experiment registry. Returns False if the write failed.

        Writes via tempfile+fsync+os.replace so a crash mid-write (process
        kill, OOM, power loss) can never leave a truncated experiments.json
        -- the same registry _load_experiments() already defends against by
        backing up an unreadable file, but which this write path could
        itself cause.
        """
        try:
            path = self._EXPERIMENTS_FILE
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=".experiments.", suffix=".tmp", dir=str(path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                    json.dump(data, tmp, indent=2, ensure_ascii=False)
                    tmp.flush()
                    os.fsync(tmp.fileno())
                os.replace(tmp_name, path)
            except BaseException:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
            return True
        except Exception as e:
            logger.warning("[VECTOR][experiment_tracker] save failed: {}", e)
            return False

    def create_experiment(self, hypothesis: str, control: str, variant: str,
                          metric: str, duration_days: int = 7) -> dict:
        """Register a new experiment."""
        data = self._load_experiments()
        exp_id = f"EXP-{data['next_id']:03d}"
        exp = {
            "id": exp_id,
            "hypothesis": hypothesis,
            "control": control,
            "variant": variant,
            "metric": metric,
            "duration_days": duration_days,
            "status": "running",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "ends_at": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=duration_days)).isoformat(),
            "observations": [],
            "conclusion": None,
        }
        data["experiments"].append(exp)
        data["next_id"] += 1
        if not self._save_experiments(data):
            raise OSError(f"could not persist experiment {exp_id}")
        logger.info("[VECTOR][experiment_tracker] created: {} — {}", exp_id, hypothesis[:60])
        return exp

    def add_observation(self, exp_id: str, variant: str, outcome: float, note: str = "") -> bool:
        """Record an observation for an experiment."""
        if variant not in ("control", "variant"):
            # analyze_experiment only counts these two arms; anything else would be silently dropped.
            logger.warning("[VECTOR][experiment_tracker] invalid variant {!r} (use 'control' or 'variant')", variant)
            return False
        data = self._load_experiments()
        for exp in data["experiments"]:
            if exp["id"] == exp_id:
                exp["observations"].append({
                    "variant": variant,
                    "outcome": outcome,
                    "note": note,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                })
                return self._save_experiments(data)
        logger.warning("[VECTOR][experiment_tracker] experiment not found: {}", exp_id)
        return False

    async def analyze_experiment(self, exp: dict) -> dict:
        """Analyze experiment results with LLM assistance."""
        obs = exp.get("observations", [])
        if len(obs) < 2:
            return {"conclusion": "insufficient_data", "confidence": 0.0, "recommendation": "collect more data"}

        control_obs = [o["outcome"] for o in obs if o["variant"] == "control"]
        variant_obs = [o["outcome"] for o in obs if o["variant"] == "variant"]

        if not control_obs or not variant_obs:
            # One arm missing: averaging it as 0 would fabricate a huge "improvement".
            return {"conclusion": "insufficient_data", "confidence": 0.0,
                    "recommendation": "collect observations for both control and variant"}

        control_avg = sum(control_obs) / len(control_obs)
        variant_avg = sum(variant_obs) / len(variant_obs)
        improvement = round((variant_avg - control_avg) / max(0.001, abs(control_avg)) * 100, 1)

        prompt = (
            f"Analyze this VECTOR AI experiment:\n\n"
            f"Hypothesis: {exp['hypothesis']}\n"
            f"Control: {exp['control']} — avg outcome: {control_avg:.3f} ({len(control_obs)} obs)\n"
            f"Variant: {exp['variant']} — avg outcome: {variant_avg:.3f} ({len(variant_obs)} obs)\n"
            f"Metric: {exp['metric']}\n"
            f"Improvement: {improvement:+.1f}%\n\n"
            f"Provide JSON:\n"
            f'{{"conclusion": "adopt_variant|keep_control|inconclusive", '
            f'"confidence": 0.0-1.0, '
            f'"reasoning": "1 sentence", '
            f'"recommendation": "specific action to take"}}'
        )
        try:
            import re as _re
            response = chat(model=self._model, messages=[{"role": "user", "content": prompt}], timeout=20.0)
            match = _re.search(r'\{.*\}', response, _re.DOTALL)
            if match:
                result = json.loads(match.group())
                result["control_avg"] = control_avg
                result["variant_avg"] = variant_avg
                result["improvement_pct"] = improvement
                return result
        except Exception as e:
            logger.warning("[VECTOR][experiment_tracker] analysis failed: {}", e)

        return {
            "conclusion": "adopt_variant" if improvement > 5 else "keep_control",
            "confidence": 0.7,
            "reasoning": f"Variant shows {improvement:+.1f}% improvement on {exp['metric']}",
            "recommendation": "Adopt variant" if improvement > 5 else "Keep control configuration",
            "control_avg": control_avg,
            "variant_avg": variant_avg,
            "improvement_pct": improvement,
            "source": "heuristic_fallback",  # LLM analysis failed; not an LLM judgement
        }

    def get_active_experiments(self) -> list[dict]:
        """Return all currently running experiments."""
        data = self._load_experiments()
        now = datetime.datetime.now(datetime.timezone.utc)
        active = []
        for exp in data["experiments"]:
            if exp["status"] != "running":
                continue
            try:
                ends_at = datetime.datetime.fromisoformat(exp["ends_at"])
                if ends_at.tzinfo is None:
                    ends_at = ends_at.replace(tzinfo=datetime.timezone.utc)
                if ends_at > now:
                    active.append(exp)
                else:
                    exp["status"] = "completed"
            except Exception:
                active.append(exp)
        self._save_experiments(data)
        return active

    def generate_experiment_ideas(self) -> list[dict]:
        """Generate default VECTOR improvement experiments to track."""
        return [
            {
                "hypothesis": "Using vector-reasoning model for decisions improves goal alignment",
                "control": "vector-focus model for decision scoring",
                "variant": "vector-reasoning model for decision scoring",
                "metric": "goal_alignment_score",
                "duration_days": 7,
            },
            {
                "hypothesis": "Injecting past reasoning chains improves decision quality",
                "control": "no ReasoningBank injection",
                "variant": "inject top-3 past chains before scoring",
                "metric": "winner_total_score",
                "duration_days": 5,
            },
            {
                "hypothesis": "Running curiosity module improves exploration of new action types",
                "control": "A2C without curiosity",
                "variant": "A2C with CuriosityModule",
                "metric": "action_type_diversity",
                "duration_days": 7,
            },
        ]

    async def run(self, task: dict) -> dict:
        # 2026-09-30 (Phase 3 codebase audit finding): the real governor
        # dispatch shape is {"type": ..., "params": {...}} -- every branch
        # below read its arguments straight off `task`, never
        # `task["params"]`, so a real dispatch always fell back to the
        # hardcoded defaults. Flattening params into task once (params
        # values win on overlap) keeps every existing flat-shape
        # caller/test working unchanged while fixing all branches at once.
        # 2026-09-30 (Codex third independent review, same cycle): capture
        # task_type from the UNMERGED task first -- if a nested params dict
        # happens to carry its own "type" key (a real field name for some
        # capabilities, not just VECTOR's own dispatch key), merging params
        # over task before reading task_type would let params["type"]
        # silently hijack routing. See districts/communications/email_agent.py's
        # identical fix for the full evidence.
        task_type = task.get("type", "status")
        task = {**task, **(task.get("params") or {})}
        try:
            if task_type == "create":
                exp = self.create_experiment(
                    task.get("hypothesis", ""),
                    task.get("control", ""),
                    task.get("variant", ""),
                    task.get("metric", "outcome"),
                    task.get("duration_days", 7),
                )
                self.award_points(20, "experiment_created")
                return {"status": "ok", "experiment": exp}

            elif task_type == "observe":
                ok = self.add_observation(
                    task.get("exp_id", ""),
                    task.get("variant", "control"),
                    float(task.get("outcome", 0.0)),
                    task.get("note", ""),
                )
                if not ok:
                    return {"status": "error", "recorded": False,
                            "error": "observation not recorded (unknown experiment, invalid variant, or save failed)"}
                self.award_points(10, "observation_recorded")
                return {"status": "ok", "recorded": ok}

            elif task_type == "analyze":
                data = self._load_experiments()
                exp_id = task.get("exp_id", "")
                exp = next((e for e in data["experiments"] if e["id"] == exp_id), None)
                if not exp:
                    return {"status": "error", "error": f"Experiment {exp_id} not found"}
                analysis = await self.analyze_experiment(exp)
                if analysis.get("conclusion") == "insufficient_data":
                    # Don't close an experiment that still needs observations.
                    return {"status": "insufficient_data", "analysis": analysis}
                exp["conclusion"] = analysis
                exp["status"] = "concluded"
                if not self._save_experiments(data):
                    return {"status": "error", "error": "could not persist conclusion", "analysis": analysis}
                self.award_points(30, "experiment_analyzed")
                return {"status": "ok", "analysis": analysis}

            elif task_type == "seed":
                ideas = self.generate_experiment_ideas()
                created = []
                for idea in ideas:
                    exp = self.create_experiment(**idea)
                    created.append(exp["id"])
                self.award_points(25, "experiments_seeded")
                return {"status": "ok", "created": created}

            else:  # status
                active = self.get_active_experiments()
                data = self._load_experiments()
                completed = [e for e in data["experiments"] if e["status"] == "concluded"]

                # Store status in memory
                self._get_memory().store(
                    event_type="experiment_status",
                    content=f"Experiments: {len(active)} active, {len(completed)} concluded",
                    tags=["projects", "experiments"],
                    context={"active": len(active), "completed": len(completed)},
                    source="experiment_tracker",
                )

                self.award_points(15, "experiments_checked")
                return {
                    "status": "ok",
                    "active_count": len(active),
                    "completed_count": len(completed),
                    "active_experiments": [
                        {"id": e["id"], "hypothesis": e["hypothesis"][:80],
                         "observations": len(e.get("observations", [])),
                         "ends_at": e.get("ends_at", "unknown")}
                        for e in active
                    ],
                }

        except Exception as e:
            logger.error("[VECTOR][experiment_tracker] {}", e)
            self.deduct_points(30, "experiment_tracker_failed")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import sys as _sys
    _sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        import tempfile, pathlib as _pl
        agent = ExperimentTracker()
        # Override file path for smoke test
        agent._EXPERIMENTS_FILE = _pl.Path(tempfile.mktemp(suffix=".json"))

        # Create an experiment
        exp = agent.create_experiment(
            "MoE routing improves task routing accuracy",
            "keyword-only routing",
            "MoE + keyword routing",
            "routing_accuracy",
            duration_days=3,
        )
        print(f"[OK] create: {exp['id']}")

        # Add observations
        agent.add_observation(exp["id"], "control", 0.72)
        agent.add_observation(exp["id"], "variant", 0.89)
        agent.add_observation(exp["id"], "control", 0.75)
        agent.add_observation(exp["id"], "variant", 0.91)
        print(f"[OK] add_observations: 4 recorded")

        # Analyze
        analysis = await agent.analyze_experiment(exp)
        print(f"[OK] analyze: conclusion={analysis.get('conclusion')} improvement={analysis.get('improvement_pct'):+.1f}%")

        result = await agent.run({"type": "status"})
        print(f"[OK] status: active={result.get('active_count')}")

        ideas = agent.generate_experiment_ideas()
        print(f"[OK] ideas: {len(ideas)} experiments ready to seed")
        print("experiment_tracker.py OK")

    asyncio.run(_smoke())
