"""Phase 3 audit regressions for districts/design."""
import asyncio

from districts.design import knowledge
from districts.design.ui_designer import UIDesigner


def test_corpus_rejects_path_traversal(tmp_path):
    secret = tmp_path / "secret.csv"
    secret.write_text("a,b\nTOPSECRET,1\n", encoding="utf-8")
    knowledge._cache.clear()
    for name in (str(secret), "../../../../../../" + str(secret).lstrip("/")):
        assert knowledge.load_corpus(name) == []
        assert knowledge.search_design_corpus("topsecret", corpora=[name]) == []


def test_corpus_still_loads_legit_files():
    knowledge._cache.clear()
    assert knowledge.load_corpus("ux-guidelines.csv")
    assert knowledge.load_corpus("react.csv")  # stacks/ subdir


def test_audit_failure_not_reported_as_score(monkeypatch):
    agent = UIDesigner()

    def boom(prompt, timeout):
        raise RuntimeError("llm down")

    monkeypatch.setattr(agent, "_llm", boom)
    res = asyncio.run(agent.run({"type": "audit", "html": "<div></div>"}))
    assert res["status"] == "error"
    assert res["audit"]["consistency_score"] is None


def test_audit_reads_params_html(monkeypatch):
    agent = UIDesigner()
    seen = {}

    def fake(prompt, timeout):
        seen["p"] = prompt
        return '{"issues": [], "consistency_score": 90}'

    monkeypatch.setattr(agent, "_llm", fake)
    res = asyncio.run(agent.run({"type": "audit", "params": {"html": "<p id='zzmarker'></p>"}}))
    assert res["status"] == "ok" and res["audit"]["consistency_score"] == 90
    assert "zzmarker" in seen["p"]
