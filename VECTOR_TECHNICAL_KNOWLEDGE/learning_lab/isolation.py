"""
VECTOR Digital Twin Lab — isolation layer.

This module is the ONLY place in the lab that touches process environment
variables or VECTOR's memory-singleton lifecycle. Every other lab module
goes through `IsolatedVectorEnv`.

Why this is safe (and not a new isolation mechanism invented for this task):

`core/memory/db_utils.py::configured_db_path()` already honors a
`VECTOR_DB_PATH` environment-variable override "for repair/tests" (its own
docstring's wording) ahead of the real app config. This is the exact,
official mechanism `tests/backend/test_memory_quality.py`,
`tests/backend/test_memory_concurrency_safety.py`, and others already use to
isolate `core.memory.episodic`'s singleton connection per-test:

    monkeypatch.setenv("VECTOR_DB_PATH", str(tmp_path / "....db"))
    monkeypatch.setenv("VECTOR_DB_KEY", "test_key_...")
    import core.memory.episodic as ep
    ep.close_db_connection()
    ...
    ep.close_db_connection()

`EpisodicMemory`, `PolicyMemory`, and `GoalSystem` all route their
persistence through that SAME singleton (`core.memory.episodic.get_db_connection`
/ `get_temp_cursor`) — so setting `VECTOR_DB_PATH`/`VECTOR_DB_KEY` before
constructing any of them, and calling `close_db_connection()` on enter/exit,
isolates all three at once, using their real, unmodified production code.

`CounterfactualMemory` and `EpistemicTracker` each accept an explicit
`db_path` constructor argument in production (see their own `__main__`
self-tests) — no environment trick needed for those two; this module just
hands them a path under the same run-scoped temp directory.

Nothing in this module ever points at the real `vector_memory.db`,
`counterfactual.db`, or `epistemic.db` paths, and nothing in this module
starts, stops, or signals the running VECTOR process.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IsolatedPaths:
    run_id: str
    root: Path
    episodic_db: Path        # goes to VECTOR_DB_PATH (drives Episodic+Policy+Goal)
    counterfactual_db: Path  # explicit CounterfactualMemory(db_path=...) arg
    epistemic_db: Path       # explicit EpistemicTracker(db_path=...) arg
    memory_tree_dir: Path    # explicit VECTOR_MEMORY_TREE_PATH override
    plan_store: Path         # explicit PlanStore(path=...) argument


_active_env: "IsolatedVectorEnv | None" = None


class IsolatedVectorEnv:
    """Context manager: a fresh, disk-backed, fully isolated VECTOR memory
    environment for exactly one Digital Twin run.

    Usage:
        with IsolatedVectorEnv() as env:
            from core.memory.policy import PolicyMemory
            pm = PolicyMemory()          # real class, writes only to env.paths.episodic_db
            ...
        # env.paths.root and everything under it still exists after __exit__
        # (caller decides whether to keep or delete it — see cleanup()).
    """

    def __init__(self, run_id: str | None = None, base_dir: str | Path | None = None):
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self._base_dir = Path(base_dir) if base_dir else None
        self._owns_base_dir = base_dir is None
        self._prev_env: dict[str, str | None] = {}
        self.paths: IsolatedPaths | None = None

    def __enter__(self) -> "IsolatedVectorEnv":
        global _active_env
        if _active_env is not None:
            raise RuntimeError(
                "An IsolatedVectorEnv is already active in this process; overlapping "
                "contexts could redirect the process-global VECTOR_DB_PATH."
            )

        root = self._base_dir or Path(tempfile.mkdtemp(prefix=f"vector_twin_{self.run_id}_"))
        root = root.resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
        if not root.is_relative_to(temp_root) or not root.name.startswith("vector_twin_"):
            raise ValueError(
                f"IsolatedVectorEnv base_dir must be a run-scoped temporary directory: {root}"
            )
        root.mkdir(parents=True, exist_ok=True)
        self.paths = IsolatedPaths(
            run_id=self.run_id,
            root=root,
            episodic_db=root / "episodic_policy_goals.db",
            counterfactual_db=root / "counterfactual.db",
            epistemic_db=root / "epistemic.db",
            memory_tree_dir=root / "memory_tree",
            plan_store=root / "plans.json",
        )

        # MemoryTree treats its environment-derived path as a production
        # default and otherwise seeds it from the legacy live tree.  An empty
        # file prevents that continuity migration from importing production
        # memories into the experiment.
        self.paths.memory_tree_dir.mkdir(parents=True, exist_ok=True)
        tree_file = self.paths.memory_tree_dir / "memory_tree.json"
        if not tree_file.exists():
            tree_file.write_text("{}", encoding="utf-8")

        _active_env = self
        try:
            for key, value in (
                ("VECTOR_DB_PATH", str(self.paths.episodic_db)),
                ("VECTOR_DB_KEY", f"twin_lab_{self.run_id}"),
                ("VECTOR_MEMORY_TREE_PATH", str(self.paths.memory_tree_dir)),
            ):
                self._prev_env[key] = os.environ.get(key)
                os.environ[key] = value

            # Drop any cached singleton connection from a PRIOR isolated (or real)
            # session in this same Python process, exactly as the established test
            # fixtures do, so the next get_db_connection() call opens fresh against
            # the path we just set.
            import core.memory.episodic as ep
            ep.close_db_connection()
        except Exception:
            self._restore_environment()
            _active_env = None
            raise

        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        global _active_env
        import core.memory.episodic as ep
        ep.close_db_connection()

        self._restore_environment()

        # Re-close (with the NEXT run's/real env's path) so a later import in
        # the same process never accidentally reuses this run's connection.
        ep.close_db_connection()
        _active_env = None

    def _restore_environment(self) -> None:
        for key, prev in self._prev_env.items():
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev

    def cleanup(self) -> None:
        """Delete this run's isolated directory. Call explicitly when the
        caller no longer needs the on-disk artifacts (e.g. after asserting on
        a trace). Never touches anything outside `self.paths.root`."""
        if self.paths and self._owns_base_dir and self.paths.root.exists():
            shutil.rmtree(self.paths.root, ignore_errors=True)


def assert_isolated(path: Path) -> None:
    """Defensive guard: raise if `path` is suspiciously close to a real
    VECTOR data path, to catch a lab bug before it ever writes anywhere
    unintended. Used by tests, not required for normal lab operation."""
    forbidden_names = {"vector_memory.db", "counterfactual.db", "epistemic.db"}
    if path.name in forbidden_names and "vector_twin_" not in str(path.parent):
        raise RuntimeError(
            f"Refusing to use non-isolated-looking path: {path} "
            "(expected it under a vector_twin_* temp directory)"
        )
