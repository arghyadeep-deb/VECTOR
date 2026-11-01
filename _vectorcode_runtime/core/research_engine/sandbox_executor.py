"""Sandbox executor — runs experiment code in an isolated subprocess."""

import asyncio
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Optional

from loguru import logger

from .models import ExperimentDesign, ExperimentResult

_SAFE_MODULES = frozenset({
    "math", "statistics", "random", "itertools", "collections",
    "json", "csv", "re", "datetime", "typing", "functools",
    "copy", "decimal", "fractions", "string", "struct",
    "time",
})

_EXECUTOR_TEMPLATE = """\
import sys, math, statistics, random, itertools, collections
import json, csv, re, datetime, typing, functools, copy
import decimal, fractions, string, struct
from typing import Any

_blt = __builtins__ if isinstance(__builtins__, dict) else vars(__builtins__)
__builtins__ = {{k: v for k, v in _blt.items()
               if k in ("True","False","None","abs","all","any",
                        "bool","dict","enumerate","float","format",
                        "frozenset","int","isinstance","iter","len",
                        "list","map","max","min","next","object",
                        "pow","range","repr","reversed","round",
                        "set","slice","sorted","str","sum","tuple",
                        "type","zip","print")}}

{code}

if __name__ == "__main__":
    result = run_experiment()
    with open("_result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
"""


def _check_code_safety(code: str) -> None:
    tree = ast.parse(code, mode="exec")
    dangerous = (ast.Call, ast.Import, ast.ImportFrom)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = getattr(node, "func", None)
            if func and isinstance(func, ast.Attribute):
                name = func.attr if isinstance(func, ast.Attribute) else ""
                if name in ("system", "popen", "subprocess", "exec", "eval", "__import__"):
                    raise ValueError(f"Call to unsafe function '{name}' is blocked")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                base = alias.name.split(".")[0]
                if base not in _SAFE_MODULES:
                    raise ValueError(f"Import of unsafe module '{alias.name}' is blocked")


class SandboxExecutor:
    def __init__(self, timeout: int = 300, work_dir: Optional[Path] = None):
        self.timeout = timeout
        self.work_dir = work_dir

    def execute(self, experiment_design: ExperimentDesign, code: str) -> ExperimentResult:
        experiment_id = experiment_design.hypothesis_id
        tmp_dir: Optional[Path] = None

        try:
            _check_code_safety(code)

            base = self.work_dir or Path(tempfile.gettempdir()) / "vector_sandbox"
            base.mkdir(parents=True, exist_ok=True)
            tmp_dir = Path(tempfile.mkdtemp(prefix="exp_", dir=base))

            wrapper = _EXECUTOR_TEMPLATE.format(
                code=textwrap.dedent(code),
            )

            script_path = tmp_dir / "run_experiment.py"
            script_path.write_text(wrapper, encoding="utf-8")

            logger.info("Executing experiment {} in sandbox dir {}", experiment_id, tmp_dir)

            proc = self._enforce_resource_limits(
                [sys.executable, str(script_path)],
                self.timeout,
                cwd=str(tmp_dir),
            )

            is_oom = self._detect_oom(proc.stdout, proc.stderr, proc.returncode)
            if is_oom:
                logger.warning("Experiment {} was killed (OOM detected)", experiment_id)

            result_path = tmp_dir / "_result.json"
            if result_path.exists():
                raw = json.loads(result_path.read_text(encoding="utf-8"))
            else:
                raw = {"output": proc.stdout, "stderr": proc.stderr}

            plots = sorted(str(p) for p in tmp_dir.glob("*.png"))

            status = "completed"
            if proc.returncode != 0:
                status = "oom_killed" if is_oom else "failed"

            return ExperimentResult(
                experiment_id=experiment_id,
                status=status,
                raw_data=raw if isinstance(raw, list) else [raw],
                summary_stats=self._extract_stats(proc.stdout),
                plots=plots,
                error=proc.stderr if proc.returncode != 0 else None,
            )

        except subprocess.TimeoutExpired:
            logger.warning("Experiment {} timed out after {}s", experiment_id, self.timeout)
            return ExperimentResult(
                experiment_id=experiment_id,
                status="timeout",
                error=f"Timed out after {self.timeout}s",
            )
        except ValueError as exc:
            logger.warning("Safety check failed for experiment {}: {}", experiment_id, exc)
            return ExperimentResult(
                experiment_id=experiment_id,
                status="failed",
                error=str(exc),
            )
        except Exception as exc:
            logger.error("Experiment {} execution error: {}", experiment_id, exc)
            return ExperimentResult(
                experiment_id=experiment_id,
                status="error",
                error=str(exc),
            )
        finally:
            if tmp_dir and tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
                logger.warning("Cleaned up sandbox dir {}", tmp_dir)

    def _extract_stats(self, stdout: str) -> dict:
        stats: dict = {}
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("STAT:"):
                parts = line.split(":", 2)
                if len(parts) == 3:
                    key, val = parts[1].strip(), parts[2].strip()
                    try:
                        stats[key] = float(val)
                    except ValueError:
                        stats[key] = val
        return stats

    async def execute_async(self, experiment_design: ExperimentDesign, code: str) -> ExperimentResult:
        experiment_id = experiment_design.hypothesis_id
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.execute, experiment_design, code)
        except Exception as exc:
            logger.error("Async execute failed for {}: {}", experiment_id, exc)
            return ExperimentResult(
                experiment_id=experiment_id,
                status="error",
                error=str(exc),
            )

    def _check_nsjail(self) -> bool:
        return shutil.which("nsjail") is not None

    def _detect_oom(self, stdout: str, stderr: str, returncode: int) -> bool:
        oom_signals = [
            "killed", "out of memory", "oom-killer", "memory exhausted",
            "MemoryError", "Cannot allocate memory", "Killed",
        ]
        combined = f"{stdout} {stderr}"
        for signal in oom_signals:
            if signal.lower() in combined.lower():
                return True
        if returncode == -9 or returncode == 137:
            return True
        return False

    def _enforce_resource_limits(self, proc_args: list[str], timeout: int, cwd: Optional[str] = None) -> subprocess.CompletedProcess:
        kwargs = {
            "capture_output": True,
            "text": True,
            "timeout": timeout,
            "env": {"PYTHONIOENCODING": "utf-8", "PATH": os.environ.get("PATH", "")},
        }
        if cwd:
            kwargs["cwd"] = cwd
        if sys.platform == "win32":
            return subprocess.run(proc_args, **kwargs)
        try:
            import resource
            def _set_limits():
                resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout + 5))
                resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 768 * 1024 * 1024))
                resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))

            return subprocess.run(
                proc_args,
                capture_output=True,
                text=True,
                timeout=timeout,
                preexec_fn=_set_limits,
                env={"PYTHONIOENCODING": "utf-8", "PATH": os.environ.get("PATH", "")},
            )
        except ImportError:
            return subprocess.run(
                proc_args,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={"PYTHONIOENCODING": "utf-8", "PATH": os.environ.get("PATH", "")},
            )
