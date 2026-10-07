"""Regression coverage for the second top-level VectorCode remainder audit."""

from types import SimpleNamespace


def test_credential_env_source_uses_keyring_aware_secret_manager(monkeypatch):
    from core.security import secrets_manager
    from vectorcode.src.credentials import PooledCredential

    monkeypatch.delenv("VECTOR_AUDIT_TEST_KEY", raising=False)
    monkeypatch.setattr(
        secrets_manager,
        "get_secret",
        lambda name: "keyring-value" if name == "VECTOR_AUDIT_TEST_KEY" else "",
    )

    credential = PooledCredential.from_env("audit", "VECTOR_AUDIT_TEST_KEY")

    assert credential is not None
    assert credential.api_key == "keyring-value"


def test_swarm_does_not_report_assignment_when_claim_is_rejected(monkeypatch):
    from vectorcode.src.swarm import AgentState, SwarmCoordinator

    class RejectingClaimService:
        def claim(self, *_args, **_kwargs):
            return None

    state = AgentState(SimpleNamespace(id="agent-1", name="Agent One", hp=500))
    monkeypatch.setattr(state, "_claim_svc", lambda: RejectingClaimService())
    coordinator = SwarmCoordinator()
    coordinator._states.append(state)

    assert coordinator.assign_task("agent-1", "exclusive task") is False
    assert state.status == "idle"
    assert state.current_task == ""
    assert state.current_issue_id == ""


def test_coherence_violations_can_reduce_privileges():
    from vectorcode.src.guidance import CoherenceScheduler, PrivilegeLevel

    scheduler = CoherenceScheduler()
    for _ in range(10):
        scheduler.record_event("agent-1", "violation", success=False, intent="task")

    score = scheduler.compute_score("agent-1")

    assert score.violation_component == 0.0
    assert scheduler.get_privilege_level("agent-1").value == PrivilegeLevel.restricted.value


def test_reasoning_bank_persistence_uses_atomic_writer(monkeypatch, tmp_path):
    import vectorcode.src.reasoning_bank as reasoning_bank

    writes = []
    monkeypatch.setattr(
        reasoning_bank,
        "atomic_json_write",
        lambda path, payload: writes.append((path, payload)),
    )
    bank = reasoning_bank.ReasoningBank(
        path=tmp_path / "bank.json", auto_load=False, pattern_learner=None
    )

    bank.save()

    assert writes and writes[0][0] == tmp_path / "bank.json"
    assert writes[0][1]["version"] == 1


def test_session_persistence_uses_atomic_writer(monkeypatch, tmp_path):
    import vectorcode.src.session as session

    writes = []
    monkeypatch.setattr(
        session,
        "atomic_json_write",
        lambda path, payload: writes.append((path, payload)),
    )

    saved = session.VectorCodeSession().save(tmp_path)

    assert saved == writes[0][0]
    assert writes[0][1]["id"]


def test_neural_checkpoint_model_and_metadata_use_atomic_writer(monkeypatch, tmp_path):
    import sys
    import vectorcode.src.neural_training as neural_training

    monolith = sys.modules["_vector_neural_training_monolith"]

    writes = []
    monkeypatch.setattr(
        monolith,
        "atomic_json_write",
        lambda path, payload: writes.append((path, payload)),
    )
    trainer = neural_training.VECTORTrainer("q-learning", state_dim=4, action_dim=2)

    trainer.save_checkpoint(tmp_path / "checkpoint.json")

    assert [path.name for path, _payload in writes] == [
        "checkpoint.json",
        "checkpoint.meta.json",
    ]


def test_hybrid_checkpoint_switches_control_approval_gates():
    from vectorcode.src.hybrid import CheckpointGate, VectorHybrid

    hybrid = VectorHybrid()
    hybrid.disable_checkpoint(CheckpointGate.RED_ACTION)
    hybrid.disable_checkpoint(CheckpointGate.PLAN_APPROVAL)

    assert hybrid.needs_approval("delete_files") is False
    assert hybrid.needs_approval("plan_approval") is False
