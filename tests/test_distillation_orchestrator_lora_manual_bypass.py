"""FL-025 — DistillationOrchestrator.run() must not bypass the tested
MANUAL/LORA_FINETUNE approval path.

execute/loop.py's execute_edits() implements and tests a specific carve-out:
a MANUAL-tier edit is normally skipped outright, EXCEPT a LORA_FINETUNE edit
may be authorized by an explicit RED owner approval through the
PermissionGateway. The top-level orchestrator (orchestrator.py's run())
reimplements the whole MANUAL-tier routing loop itself instead of calling
execute_edits(), and that reimplementation had no LORA_FINETUNE carve-out at
all -- every LoRA edit was unconditionally "skipped" before it could ever
reach the Gateway. Fixed by mirroring execute_edits()'s exact branch via a
new _lora_finetune_gateway_reason() helper.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import pytest

from core.loop.permission_gateway import GatewayResult, PermissionGateway
from learning.distillation.models import Edit, EditOp, EditPillar, EditRiskTier
import learning.distillation.orchestrator as orch_mod
from learning.distillation.orchestrator import DistillationOrchestrator


def _lora_edit() -> Edit:
    return Edit(
        id="edit-lora-1",
        pillar=EditPillar.INTELLIGENCE,
        op=EditOp.LORA_FINETUNE,
        target="students.vector_focus",
        payload={"base_model": "qwen2.5-7b", "training_data": ["a", "b"]},
        rationale="improve weak cluster",
        expected_improvement="cluster-1",
        risk_tier=EditRiskTier.MANUAL,
    )


class _FakeGateway:
    def __init__(self, approved: bool) -> None:
        self.approved = approved
        self.calls: list[tuple[str, dict, str]] = []

    async def evaluate_external(self, action_type, params, source):
        self.calls.append((action_type, params, source))
        return GatewayResult(
            approved=self.approved,
            level="RED",
            executed=False,
            result={},
            reason="owner rejected" if not self.approved else "owner approved",
        )


def test_lora_finetune_gateway_reason_empty_when_approved(monkeypatch):
    gateway = _FakeGateway(approved=True)
    monkeypatch.setattr(PermissionGateway, "get_shared", classmethod(lambda cls: gateway))

    reason = DistillationOrchestrator._lora_finetune_gateway_reason(
        _lora_edit(), "session-x"
    )
    assert reason == ""
    assert gateway.calls[0][0] == "lora_finetune_execute"
    assert gateway.calls[0][2] == "distillation_orchestrator"


def test_lora_finetune_gateway_reason_nonempty_when_denied(monkeypatch):
    gateway = _FakeGateway(approved=False)
    monkeypatch.setattr(PermissionGateway, "get_shared", classmethod(lambda cls: gateway))

    reason = DistillationOrchestrator._lora_finetune_gateway_reason(
        _lora_edit(), "session-x"
    )
    assert reason == "owner rejected"


def _orchestrator(vector_home: Path, *, checkpoint_sha="deadbeef") -> DistillationOrchestrator:
    return DistillationOrchestrator(
        teacher_engine=None,
        teacher_model="mock",
        trace_store=SimpleNamespace(count=lambda: 0),
        benchmark_samples=[],
        student_runner=None,
        judge=None,
        session_store=SimpleNamespace(save_session=lambda session: None),
        checkpoint_store=SimpleNamespace(current_sha=lambda: checkpoint_sha),
        vector_home=vector_home,
        min_traces=0,
    )


def _patch_pipeline(monkeypatch, edit: Edit) -> None:
    """Replace DiagnosisRunner/LearningPlanner with fakes that hand run()
    exactly one edit, so we can observe how run() routes it without needing
    a real teacher engine/trace store."""

    class _FakeDiagResult:
        cost_usd = 0.0
        clusters = ["cluster-1"]
        diagnosis_md = "diagnosis"

    class _FakeDiagnosisRunner:
        def __init__(self, **kwargs):
            pass

        def run(self):
            return _FakeDiagResult()

    class _FakePlan:
        def __init__(self, edits):
            self.edits = edits
            self.estimated_cost_usd = 0.0

    class _FakeLearningPlanner:
        def __init__(self, **kwargs):
            pass

        def run(self, diagnosis_md, clusters):
            return _FakePlan(edits=[edit])

    monkeypatch.setattr(orch_mod, "DiagnosisRunner", _FakeDiagnosisRunner)
    monkeypatch.setattr(orch_mod, "LearningPlanner", _FakeLearningPlanner)


def test_run_blocks_lora_edit_via_gateway_instead_of_skipping(monkeypatch, tmp_path):
    gateway = _FakeGateway(approved=False)
    monkeypatch.setattr(PermissionGateway, "get_shared", classmethod(lambda cls: gateway))
    edit = _lora_edit()
    _patch_pipeline(monkeypatch, edit)

    orch = _orchestrator(tmp_path)
    session = orch.run(SimpleNamespace(kind="on_demand", metadata={}))

    assert len(session.edit_outcomes) == 1
    outcome = session.edit_outcomes[0]
    # The old bug: status="skipped", error="manual tier, requires explicit
    # approval" -- never reaching the gateway at all.
    assert outcome.status != "skipped"
    assert outcome.error != "manual tier, requires explicit approval"
    assert outcome.status == "blocked"
    assert outcome.error == "owner rejected"
    # Proves the real Gateway was actually consulted for this edit.
    assert gateway.calls == [
        (
            "lora_finetune_execute",
            {
                "edit_id": "edit-lora-1",
                "op": "lora_finetune",
                "target": "students.vector_focus",
                "base_model": "qwen2.5-7b",
                "training_sample_count": 2,
                "session_id": session.id,
            },
            "distillation_orchestrator",
        )
    ]


def test_run_does_not_skip_lora_edit_when_approved(monkeypatch, tmp_path):
    gateway = _FakeGateway(approved=True)
    monkeypatch.setattr(PermissionGateway, "get_shared", classmethod(lambda cls: gateway))
    edit = _lora_edit()
    _patch_pipeline(monkeypatch, edit)

    orch = _orchestrator(tmp_path)
    session = orch.run(SimpleNamespace(kind="on_demand", metadata={}))

    assert len(session.edit_outcomes) == 1
    outcome = session.edit_outcomes[0]
    # Approved -- must fall through to validate/apply, never the old
    # unconditional "skipped" bypass.
    assert outcome.status != "skipped"
    assert outcome.error != "manual tier, requires explicit approval"
    assert gateway.calls, "gateway must have been consulted"


def test_non_lora_manual_edit_is_still_skipped_outright(monkeypatch, tmp_path):
    """Only LORA_FINETUNE gets the Gateway carve-out -- every other MANUAL
    edit must keep the original skip behavior unchanged."""
    gateway = _FakeGateway(approved=True)
    monkeypatch.setattr(PermissionGateway, "get_shared", classmethod(lambda cls: gateway))

    other_edit = Edit(
        id="edit-other-1",
        pillar=EditPillar.AGENT,
        op=EditOp.REPLACE_SYSTEM_PROMPT,
        target="agents.simple.system_prompt",
        payload={"new_prompt": "x"},
        rationale="test",
        expected_improvement="cluster-1",
        risk_tier=EditRiskTier.MANUAL,
    )
    _patch_pipeline(monkeypatch, other_edit)

    orch = _orchestrator(tmp_path)
    session = orch.run(SimpleNamespace(kind="on_demand", metadata={}))

    assert len(session.edit_outcomes) == 1
    outcome = session.edit_outcomes[0]
    assert outcome.status == "skipped"
    assert outcome.error == "manual tier, requires explicit approval"
    assert gateway.calls == []  # never consulted for a non-LoRA MANUAL edit


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
