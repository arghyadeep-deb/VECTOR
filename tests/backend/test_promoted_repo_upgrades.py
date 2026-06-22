from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone


def test_browser_governance_blocks_high_risk_browser_actions() -> None:
    from core.browser.governance import get_browser_governance

    gov = get_browser_governance()
    decision = gov.classify(
        "type",
        url="https://checkout.example",
        inputs={"content": "buy now with credit card"},
    )

    assert decision.level == "RED"
    assert decision.allowed is False
    assert decision.requires_owner is True
    assert decision.permission_action == "hand_browser"


def test_browser_governance_receipt_hashes_screenshot_and_redacts_text() -> None:
    from core.browser.governance import get_browser_governance

    gov = get_browser_governance()
    decision = gov.classify("screenshot", url="https://example.com")
    receipt = gov.make_receipt(
        decision,
        url="https://example.com",
        operator_id="owner",
        session_id="s1",
        screenshot_bytes=b"fake-png",
        visible_text="Logged in as user@example.com",
    ).to_dict()

    assert receipt["screenshot_hash"]
    assert receipt["redactions"]
    assert receipt["operator_id"] == "owner"


def test_browser_controller_uses_governance_before_execution() -> None:
    from core.vision_control.browser_controller import BrowserController

    class DummyPage:
        url = "https://checkout.example"

    result = asyncio.run(
        BrowserController().execute_browser_action(
            DummyPage(),
            {
                "action_type": "type",
                "action_inputs": {"content": "submit payment"},
            },
        )
    )

    assert result["status"] == "blocked"
    assert result["level"] == "RED"


def test_extraction_artifact_cleans_html_and_tracks_hash() -> None:
    from core.research_engine.content_fetcher.extraction import (
        build_extraction_artifact,
        html_to_markdown,
    )

    markdown, links, title = html_to_markdown(
        "<html><head><title>Example</title></head>"
        "<body><script>secret()</script><h1>Hello</h1>"
        "<a href='/pricing'>Pricing</a></body></html>",
        base_url="https://example.com",
    )
    artifact = build_extraction_artifact(
        "https://example.com",
        markdown,
        title=title,
        links=links,
        query="pricing",
    )

    assert artifact.title == "Example"
    assert "secret()" not in artifact.markdown
    assert artifact.content_hash
    assert artifact.links[0]["url"] == "https://example.com/pricing"


def test_context_budget_compacts_and_retrieves_handles() -> None:
    from districts.memory_curator.context_budget import ContextBudgetManager

    manager = ContextBudgetManager(max_message_chars=80, head_chars=20, tail_chars=20)
    compacted, handles = manager.compact_messages(
        [{"role": "tool", "content": "alpha " * 100}]
    )

    assert handles
    handle = handles[0]["handle"]
    assert "retrieval_handle=" in compacted[0]["content"]
    assert manager.retrieve(handle).startswith("alpha")
    assert manager.stats()["handles"] == 1


def test_competitor_xray_normalizes_targets_and_ranks_threats() -> None:
    from districts.marketing.competitor_xray import (
        build_empty_brief,
        make_claim,
        normalize_target,
        rank_threats,
        score_threat,
    )

    assert normalize_target("@creator")["type"] == "social_handle"
    assert normalize_target("example.com")["type"] == "url"

    a = build_empty_brief("@creator", confidence="medium")
    a.icp.append(make_claim("Sells to agency owners", "CONFIRMED", "https://example.com"))
    a.threat_score = score_threat(maturity=80, momentum=60, evidence_quality=90)

    b = build_empty_brief("SmallCo")
    b.threat_score = score_threat(maturity=20, momentum=30, evidence_quality=40)

    ranked = rank_threats([b, a])
    assert ranked[0]["target"] == "@creator"
    assert ranked[0]["threat_score"] > ranked[1]["threat_score"]


def test_last30days_scores_recent_high_confidence_signals_first() -> None:
    from districts.research.last30days import RecentSignal, build_brief

    now = datetime.now(timezone.utc)
    old = RecentSignal(
        source="hn",
        title="Old",
        url="https://example.com/old",
        published_at=(now - timedelta(days=25)).isoformat(),
        engagement=900,
        confidence=0.9,
    )
    recent = RecentSignal(
        source="reddit",
        title="Recent",
        url="https://example.com/recent",
        published_at=(now - timedelta(days=1)).isoformat(),
        engagement=100,
        confidence=0.8,
    )

    brief = build_brief("agent tools", [old, recent], degraded_sources=["x"])
    data = brief.to_dict()

    assert data["signals"][0]["title"] == "Recent"
    assert data["degraded_sources"] == ["x"]

