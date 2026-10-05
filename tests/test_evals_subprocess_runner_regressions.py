"""Regression tests for external evaluation subprocess helpers."""

from vectorcode.src.evals.backends.external import _subprocess_runner


def test_null_sampler_is_a_safe_concrete_fallback(monkeypatch) -> None:
    monkeypatch.setattr(_subprocess_runner, "_try_start_nvml", lambda: None)
    monkeypatch.setattr(_subprocess_runner, "_try_start_powermetrics", lambda: None)
    monkeypatch.setattr(_subprocess_runner, "_try_start_rocm_smi", lambda: None)
    monkeypatch.setattr(_subprocess_runner, "_try_start_rapl", lambda: None)

    sampler = _subprocess_runner._start_sampler()

    sampler.start()
    assert sampler.method == "unavailable"
    assert sampler.stop() == []


if __name__ == "__main__":
    sampler = _subprocess_runner._NullSampler()
    sampler.start()
    assert sampler.stop() == []
