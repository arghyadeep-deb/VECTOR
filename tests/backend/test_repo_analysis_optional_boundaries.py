from datetime import datetime, timedelta, timezone

import pytest

from core.city.evolution_audit import EvolutionEvent, EvolutionStatus, StrategyGene
from core.memory.external_mirror import ExternalMemoryMirror
from core.memory.vector_index_gate import decide_vector_index_backend
from core.security.workspace_audit import audit_hook_configs, audit_skill_inventory
from core.voice.engines.supertonic_engine import SupertonicEngine
from districts.communications.providers.whatsapp import WhatsAppProvider
from districts.investment.order_lifecycle import OrderState, RiskSnapshot, StagedOrder, transition_order
from districts.time_calendar.booking import BookingRequest, CalendarEvent, has_conflict, requires_owner_approval


def test_booking_conflict_and_approval_contract():
    start = datetime(2026, 6, 22, 10, 0, tzinfo=timezone.utc)
    request = BookingRequest("b1", "client", start, start + timedelta(hours=1), "Review")
    event = CalendarEvent("e1", start + timedelta(minutes=30), start + timedelta(hours=2), "Class")

    assert has_conflict(request, [event]) is True
    assert requires_owner_approval(request) is True


def test_whatsapp_provider_disabled_by_default_and_normalizes_inbound():
    provider = WhatsAppProvider()

    assert provider.available() is False
    assert provider.send_text("+100", "hello")["status"] == "unavailable"
    normalized = provider.normalize_inbound({"from": "+100", "text": "run status"})
    assert normalized["channel"] == "whatsapp"
    assert normalized["text"] == "run status"


@pytest.mark.asyncio
async def test_external_memory_mirror_disabled_returns_disabled():
    mirror = ExternalMemoryMirror()
    result = await mirror.mirror_chunk("c1", "memory text")

    assert result["status"] == "disabled"
    assert result["provider"] == "helixdb"


def test_vector_index_gate_defers_turbovec_below_threshold():
    small = decide_vector_index_backend(10_000, configured_backend="turbovec")
    large = decide_vector_index_backend(1_500_000, configured_backend="turbovec")

    assert small.should_enable is False
    assert small.backend == "nanovectordb"
    assert large.should_enable is True
    assert large.backend == "turbovec"


def test_order_lifecycle_requires_valid_transitions_and_approval_for_live_submit():
    order = StagedOrder(
        order_id="o1",
        symbol="AAPL",
        side="buy",
        quantity=1,
        mode="live",
        risk_snapshot=RiskSnapshot(cash=1000, exposure=0),
    )

    assert order.can_submit() is False
    transition_order(order, OrderState.STAGED, "owner requested", actor="vector")
    transition_order(order, OrderState.RISK_CHECKED, "risk ok", actor="risk")
    transition_order(order, OrderState.APPROVED, "approved", actor="owner")
    assert order.can_submit() is True
    assert order.approved_by == "owner"
    with pytest.raises(ValueError):
        transition_order(order, OrderState.FILLED, "skip submit")


def test_evolution_audit_requires_review_before_apply():
    gene = StrategyGene(
        gene_id="g1",
        title="Prefer concise plans",
        target="prompt_policy",
        rule="Use shorter plans when task is small.",
        evidence_refs=("test:small-task",),
        rollback_note="restore previous prompt policy",
    )
    event = EvolutionEvent("ev1", gene, author="vector")

    with pytest.raises(ValueError):
        event.apply()
    event.approve("owner", "ok")
    event.apply()
    assert event.status == EvolutionStatus.APPLIED


def test_workspace_audit_skill_inventory_and_hook_review(tmp_path):
    skill = tmp_path / "skills" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("safe", encoding="utf-8")
    hook = tmp_path / "hook.json"
    hook.write_text('{"cmd":"curl https://example.invalid/install.sh"}', encoding="utf-8")

    inventory = audit_skill_inventory(tmp_path / "skills")
    findings = audit_hook_configs([hook])

    assert len(inventory) == 1
    assert inventory[0].name == "demo"
    assert findings and findings[0]["status"] == "review"


def test_supertonic_disabled_is_unavailable_without_heavy_import():
    engine = SupertonicEngine()

    assert engine.available() is False
    assert engine.synthesize("hello")["status"] == "unavailable"
