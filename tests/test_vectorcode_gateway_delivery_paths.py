"""Regression tests for delivery output path confinement."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


SOURCE_ROOT = Path("vectorcode/src").resolve()
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from gateway.config import GatewayConfig  # noqa: E402
from gateway.delivery import DeliveryRouter  # noqa: E402


@pytest.mark.parametrize("job_id", ("../escape", "..\\escape", ".", ".."))
def test_local_delivery_rejects_job_ids_that_escape_output_directory(
    tmp_path: Path,
    job_id: str,
) -> None:
    router = DeliveryRouter(GatewayConfig())
    router.output_dir = tmp_path / "output"

    with pytest.raises(ValueError, match="safe path component"):
        router._deliver_local("secret", job_id, None, None)

    assert not (tmp_path / "escape").exists()


def test_truncated_output_rejects_job_id_path_injection(tmp_path: Path, monkeypatch) -> None:
    router = DeliveryRouter(GatewayConfig())
    monkeypatch.setattr("gateway.delivery.get_vector_home", lambda: tmp_path)

    with pytest.raises(ValueError, match="safe path component"):
        router._save_full_output("secret", "../../escape")

    assert not (tmp_path.parent / "escape").exists()
