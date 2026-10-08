from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from core.config import CONFIG
from core.loop.permission_gateway import OWNER_APPROVAL_ONLY, PermissionGateway
from vectorcode.src.learning.distillation.execute.appliers.lora_stub import (
    LoraStubApplier,
    _snapshot_adapter_state,
)
from vectorcode.src.learning.distillation.execute.base import (
    ApplyContext,
    ApplyResult,
    EditApplierRegistry,
    ValidationResult,
)
from vectorcode.src.learning.distillation.execute.loop import execute_edits
from vectorcode.src.learning.distillation.models import (
    AutonomyMode,
    Edit,
    EditOp,
    EditPillar,
    EditRiskTier,
)


def _lora_edit(edit_id: str = "lora-edit") -> Edit:
    return Edit(
        id=edit_id,
        pillar=EditPillar.INTELLIGENCE,
        op=EditOp.LORA_FINETUNE,
        target="models.student",
        payload={
            "base_model": "local/student",
            "training_data": [{"input": "before", "output": "after"}],
        },
        rationale="Improve a measured failure cluster",
        expected_improvement="cluster-1",
        risk_tier=EditRiskTier.MANUAL,
    )


class _RecordingGateway:
    def __init__(self, approved: bool, reason: str = "Owner decision") -> None:
        self.approved = approved
        self.reason = reason
        self.calls: list[tuple[str, dict, str]] = []

    async def evaluate_external(self, action_type: str, params: dict, source: str):
        self.calls.append((action_type, params, source))
        return SimpleNamespace(
            approved=self.approved,
            level="RED",
            reason=self.reason,
        )


class _RecordingApplier:
    op = EditOp.LORA_FINETUNE

    def __init__(self) -> None:
        self.validated = 0
        self.applied = 0

    def validate(self, edit: Edit, ctx: ApplyContext) -> ValidationResult:
        self.validated += 1
        return ValidationResult(ok=True)

    def apply(self, edit: Edit, ctx: ApplyContext) -> ApplyResult:
        self.applied += 1
        return ApplyResult(changed_files=[])

    def rollback(self, edit: Edit, ctx: ApplyContext) -> None:
        raise AssertionError("rollback is not expected")


def _registry(applier: _RecordingApplier) -> EditApplierRegistry:
    registry = EditApplierRegistry()
    registry.register(applier)
    return registry


def test_lora_manual_edit_routes_through_exact_red_gateway_shape(tmp_path: Path) -> None:
    edit = _lora_edit()
    gateway = _RecordingGateway(approved=False, reason="Owner rejected training")
    applier = _RecordingApplier()

    outcomes = execute_edits(
        edits=[edit],
        ctx=ApplyContext(vector_home=tmp_path, session_id="session-1"),
        autonomy_mode=AutonomyMode.TIERED,
        registry=_registry(applier),
        permission_gateway=gateway,
    )

    assert gateway.calls == [
        (
            "lora_finetune_execute",
            {
                "edit_id": edit.id,
                "op": "lora_finetune",
                "target": "models.student",
                "base_model": "local/student",
                "training_sample_count": 1,
                "session_id": "session-1",
            },
            "distillation_execute_loop",
        )
    ]
    assert outcomes[0].status == "blocked"


def test_lora_gateway_denial_has_no_applier_side_effects(tmp_path: Path) -> None:
    gateway = _RecordingGateway(approved=False, reason="Owner rejected training")
    applier = _RecordingApplier()

    outcome = execute_edits(
        edits=[_lora_edit()],
        ctx=ApplyContext(vector_home=tmp_path, session_id="session-1"),
        autonomy_mode=AutonomyMode.AUTO,
        registry=_registry(applier),
        permission_gateway=gateway,
    )[0]

    assert outcome.model_dump() | {"applied_at": None} == {
        "edit_id": "lora-edit",
        "status": "blocked",
        "benchmark_delta": None,
        "cluster_deltas": {},
        "error": "Owner rejected training",
        "applied_at": None,
    }
    assert (applier.validated, applier.applied) == (0, 0)


def test_lora_gateway_approval_reaches_applier(tmp_path: Path) -> None:
    gateway = _RecordingGateway(approved=True)
    applier = _RecordingApplier()

    outcome = execute_edits(
        edits=[_lora_edit()],
        ctx=ApplyContext(vector_home=tmp_path, session_id="session-1"),
        autonomy_mode=AutonomyMode.AUTO,
        registry=_registry(applier),
        permission_gateway=gateway,
    )[0]

    assert outcome.status == "applied"
    assert (applier.validated, applier.applied) == (1, 1)


def test_lora_snapshot_restores_concrete_pre_training_adapter(tmp_path: Path) -> None:
    edit = _lora_edit()
    ctx = ApplyContext(vector_home=tmp_path, session_id="session-1")
    adapter_dir = tmp_path / "lora_adapters" / edit.id
    adapter_dir.mkdir(parents=True)
    weights = adapter_dir / "adapter_model.safetensors"
    weights.write_bytes(b"known-pre-training-state")

    snapshot = _snapshot_adapter_state(edit, ctx)
    weights.write_bytes(b"bad-trained-state")
    (adapter_dir / "new-file.json").write_text("bad", encoding="utf-8")

    LoraStubApplier().rollback(edit, ctx)

    assert weights.read_bytes() == b"known-pre-training-state"
    assert not (adapter_dir / "new-file.json").exists()
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    assert manifest == {
        "edit_id": edit.id,
        "had_adapter": True,
        "session_id": "session-1",
    }
    assert (snapshot / "pre_training_adapter" / weights.name).read_bytes() == (
        b"known-pre-training-state"
    )
    assert snapshot.parent == (tmp_path / "lora_rollbacks").resolve()


def test_lora_action_is_red_and_owner_approval_only() -> None:
    assert "lora_finetune_execute" in CONFIG["permission"]["red"]
    assert "lora_finetune_execute" in OWNER_APPROVAL_ONLY
    assert PermissionGateway()._classify("lora_finetune_execute") == "RED"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
