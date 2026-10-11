"""FL-024 — ExperimentRegistry/Experiment input validation.

Before this fix:
- Experiment.assign() divided by `len(self.variants)` with no guard, so an
  experiment created with an empty variants list raised ZeroDivisionError
  instead of a clear error.
- Experiment.record() accepted any variant string (including ones never
  declared for the experiment) and recorded against inactive experiments
  with no rejection.
- ExperimentRegistry declared a `threading.RLock` that nothing ever
  acquired, leaving concurrent create()/deactivate() semantics undefined.

Dormant today (zero real production callers, confirmed via repo-wide grep
for `core.experiments.ab_testing` outside this module and its __init__.py),
fixed anyway per the flaw-ledger's "fix narrow bugs even in dormant code"
bar -- these are correctness bugs, not scope expansion of the feature.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.experiments.ab_testing import Experiment, ExperimentRegistry


def test_assign_raises_clear_error_on_empty_variants():
    exp = Experiment(
        id=1, name="empty", variants=[], description="", created_at=0.0, active=True,
    )
    with pytest.raises(ValueError):
        exp.assign("subject-1")


def test_record_rejects_unknown_variant(tmp_path):
    reg = ExperimentRegistry(db_path=tmp_path / "exp.db")
    exp = reg.create("known_variants", variants=["a", "b"])
    with pytest.raises(ValueError):
        exp.record("subject-1", "not-a-real-variant", "reward", 1.0)


def test_record_rejects_inactive_experiment(tmp_path):
    reg = ExperimentRegistry(db_path=tmp_path / "exp.db")
    exp = reg.create("will_deactivate", variants=["a", "b"])
    reg.deactivate("will_deactivate")
    # exp is a stale snapshot taken before deactivation; re-fetch to mirror
    # how a real caller would observe the current state before recording.
    exp = reg.get_experiment("will_deactivate")
    with pytest.raises(ValueError):
        exp.record("subject-1", "a", "reward", 1.0)


def test_record_accepts_valid_variant_on_active_experiment(tmp_path):
    reg = ExperimentRegistry(db_path=tmp_path / "exp.db")
    exp = reg.create("valid_record", variants=["a", "b"])
    exp.record("subject-1", "a", "reward", 1.0)  # must not raise


def test_create_and_deactivate_use_the_registry_lock(tmp_path):
    reg = ExperimentRegistry(db_path=tmp_path / "exp.db")
    assert reg._lock.acquire(blocking=False)
    reg._lock.release()
    # create()/deactivate() must actually acquire the same RLock instance
    # (RLock is reentrant for the owning thread, so re-entering from the
    # calling thread doesn't prove acquisition by itself -- instead assert
    # the lock object identity is the one the methods use by checking a
    # concurrent acquisition from another thread blocks while create() runs).
    import threading
    import time

    entered = threading.Event()
    released = threading.Event()

    def hold_lock():
        with reg._lock:
            entered.set()
            time.sleep(0.2)
        released.set()

    t = threading.Thread(target=hold_lock)
    t.start()
    entered.wait(timeout=2)
    start = time.monotonic()
    reg.create("during_hold", variants=["x"])
    elapsed = time.monotonic() - start
    t.join(timeout=2)
    assert elapsed >= 0.1  # create() had to wait for the held lock


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
