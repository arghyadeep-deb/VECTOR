"""Audit phase 3 — districts/news_trends regression tests (no real network)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from districts.news_trends import ai_news_bot as anb
from districts.news_trends import market_trends_bot as mtb
from districts.news_trends import opportunity_spotter as osp
from districts.news_trends import social_miner as sm
from districts.news_trends.ai_news_bot import AINewsBot
from districts.news_trends.market_trends_bot import MarketTrendsBot
from districts.news_trends.opportunity_spotter import OpportunitySpotter
from districts.news_trends.problem_clusterer import ProblemClusterer
from districts.news_trends.social_miner import SocialMiner
from districts.news_trends.venture_pipeline import VenturePipeline


def _run(c):
    return asyncio.run(c)


def _mk(cls, mod):
    with patch.object(mod, "EpisodicMemory"), patch.object(mod, "ObsidianSync"):
        bot = cls()
    bot.memory = MagicMock()
    return bot


# ── AINewsBot ────────────────────────────────────────────────────────────────

def test_news_fetch_failure_is_error_not_simulated_news():
    bot = _mk(AINewsBot, anb)
    with patch.dict(anb.CONFIG["api_keys"], {"newsapi_key": ""}):
        res = bot.fetch_ai_news(3)
    assert res["status"] == "error"
    assert res["articles"] == [] and res["count"] == 0
    bot.memory.store.assert_not_called()


def test_newsapi_key_sent_in_header_not_url():
    bot = _mk(AINewsBot, anb)
    seen = {}

    def fake_get(self, url, **kw):
        seen["url"], seen["kw"] = url, kw
        return httpx.Response(200, json={"status": "ok", "articles": []},
                              request=httpx.Request("GET", url))

    with patch.dict(anb.CONFIG["api_keys"], {"newsapi_key": "SECRET123"}), \
         patch.object(httpx.Client, "get", fake_get):
        res = bot.fetch_ai_news(2)
    assert "SECRET123" not in seen["url"]
    assert "SECRET123" not in json.dumps(seen["kw"].get("params", {}))
    assert seen["kw"]["headers"]["X-Api-Key"] == "SECRET123"
    assert res.get("status") != "error"


def test_newsapi_error_body_is_error():
    bot = _mk(AINewsBot, anb)

    def fake_get(self, url, **kw):
        return httpx.Response(200, json={"status": "error", "code": "apiKeyInvalid"},
                              request=httpx.Request("GET", url))

    with patch.dict(anb.CONFIG["api_keys"], {"newsapi_key": "k"}), \
         patch.object(httpx.Client, "get", fake_get):
        res = bot.fetch_ai_news(2)
    assert res["status"] == "error"


def test_alert_breaking_fetch_failure_not_low_alert():
    bot = _mk(AINewsBot, anb)
    with patch.dict(anb.CONFIG["api_keys"], {"newsapi_key": ""}):
        res = bot.alert_breaking("LLM")
    assert res["status"] == "error"
    assert res["alert_level"] == "UNKNOWN"


def test_summary_blocks_ssrf_url():
    bot = _mk(AINewsBot, anb)
    bot._call_ollama = MagicMock(return_value="summary")
    res = bot.generate_summary("http://169.254.169.254/latest/meta-data")
    assert res["status"] == "error"
    bot._call_ollama.assert_not_called()


def test_summary_fetch_failure_does_not_summarise_placeholder():
    bot = _mk(AINewsBot, anb)
    bot._call_ollama = MagicMock(return_value="invented summary")

    def boom(self, url, **kw):
        raise httpx.ConnectError("down")

    with patch.object(httpx.Client, "get", boom):
        res = bot.generate_summary("https://example.com/a")
    assert res["status"] == "error"
    bot._call_ollama.assert_not_called()
    bot.memory.store.assert_not_called()


def test_news_run_without_url_fetches_news_and_empty_summary_errors():
    bot = _mk(AINewsBot, anb)
    bot.fetch_ai_news = MagicMock(return_value={"articles": [], "count": 0})
    res = _run(bot.run({"type": "news", "params": {}}))
    bot.fetch_ai_news.assert_called_once()
    assert res["status"] == "ok"


# ── MarketTrendsBot ──────────────────────────────────────────────────────────

def test_track_trends_llm_failure_is_error():
    bot = _mk(MarketTrendsBot, mtb)
    bot._call_ollama = MagicMock(return_value="")
    res = _run(bot.run({"params": {"keywords": ["AI"]}}))
    assert res["status"] == "error"
    assert res["trends"] == [] and bot.tracked_trends == {}
    bot.memory.store.assert_not_called()


def test_anomaly_empty_llm_is_error_not_clean():
    bot = _mk(MarketTrendsBot, mtb)
    bot.tracked_trends["AI"] = [{"analysis": "a"}, {"analysis": "b"}]
    bot._call_ollama = MagicMock(return_value="")
    res = bot.alert_anomaly("AI")
    assert res["status"] == "error"


def test_anomaly_non_numeric_confidence_does_not_crash_and_string_false():
    bot = _mk(MarketTrendsBot, mtb)
    bot.tracked_trends["AI"] = [{"analysis": "a"}, {"analysis": "b"}]
    bot._call_ollama = MagicMock(return_value='{"is_anomaly": "false", "confidence": "high", "message": "m"}')
    res = bot.alert_anomaly("AI")
    assert res["is_anomaly"] is False
    assert bot.anomalies == []


def test_trend_report_empty_llm_is_error():
    bot = _mk(MarketTrendsBot, mtb)
    bot._call_ollama = MagicMock(return_value="  ")
    assert bot.generate_trend_report("AI")["status"] == "error"


# ── OpportunitySpotter ───────────────────────────────────────────────────────

def test_scan_empty_llm_is_error_not_fabricated_opportunity():
    bot = _mk(OpportunitySpotter, osp)
    bot._call_ollama = MagicMock(return_value="")
    res = _run(bot.run({"params": {"industry": "AI"}}))
    assert res["status"] == "error"
    assert res["opportunities"] == [] and res["count"] == 0


def test_evaluate_unparseable_is_error_not_default_fives():
    bot = _mk(OpportunitySpotter, osp)
    bot._call_ollama = MagicMock(return_value="no json here")
    res = bot.evaluate_opportunity({"name": "x"})
    assert res["status"] == "error"
    assert res["evaluation"] is None
    bot.memory.store.assert_not_called()


# ── SocialMiner ──────────────────────────────────────────────────────────────

def test_mine_all_every_fetch_failing_is_error_and_no_snapshot(tmp_path):
    with patch.dict(sm.CONFIG, {"venture": {"data_dir": str(tmp_path), "subreddits": ["saas"]}}):
        miner = SocialMiner()
        with patch("httpx.get", side_effect=httpx.ConnectError("down")), \
             patch.object(sm.time, "sleep"):
            res = miner.mine_all()
    assert res["status"] == "error"
    assert list(tmp_path.glob("mined_*.json")) == []


def test_invalid_subreddit_name_not_fetched():
    miner = SocialMiner()
    with patch("httpx.get") as g:
        assert miner.mine_reddit("../../api/v1/me") == []
    g.assert_not_called()


# ── ProblemClusterer ─────────────────────────────────────────────────────────

def test_label_cluster_prompt_echo_does_not_mark_solvable():
    pc = ProblemClusterer()
    cluster = {"posts": [{"title": "Why is there no simple offline PDF viewer for fonts"}]}

    def echo(prompt):
        return prompt  # what vchat() returns when the LLM is unreachable

    pc.vchat = echo
    out = pc.label_cluster(cluster)
    assert out["software_solvable"] is False
    assert not out["problem"].startswith("<")


def test_analyze_without_snapshot_is_error(tmp_path):
    with patch.dict("districts.news_trends.problem_clusterer.CONFIG",
                    {"venture": {"data_dir": str(tmp_path)}}):
        res = _run(ProblemClusterer().run({"params": {}}))
    assert res["status"] == "error"


# ── VenturePipeline ──────────────────────────────────────────────────────────

def _vp(tmp_path):
    vp = VenturePipeline()
    vp.data_dir = tmp_path
    return vp


def test_unverified_validation_is_flagged(tmp_path):
    vp = _vp(tmp_path)
    err = {"status": "error", "error": "LLM unavailable", "verdict": "UNVERIFIED", "idea_name": "x"}
    with patch("districts.startups.idea_validator.IdeaValidator") as IV, \
         patch("districts.startups.revenue_modeler.RevenueModeler") as RM:
        IV.return_value.run = MagicMock(side_effect=lambda t: asyncio.sleep(0, err))
        RM.return_value.run = MagicMock(side_effect=lambda t: asyncio.sleep(0, {"status": "ok", "mrr": 1}))
        out = _run(vp._validate_idea({"product_idea": "x", "problem": "p"}))
    assert out["verified"] is False


def test_pipeline_does_not_recommend_unverified_idea(tmp_path):
    vp = _vp(tmp_path)
    cluster = {"software_solvable": True, "product_idea": "bad idea", "problem": "p",
               "demand_score": 9, "size": 2}

    async def fake_validate(c):
        return {"idea": "bad idea", "problem": "p", "validation": {"verdict": "UNVERIFIED"},
                "revenue": {}, "verified": False}

    vp._validate_idea = fake_validate
    vp._draft_content = MagicMock()
    vp._notify = MagicMock()
    mined = {"count": 3, "posts": [{"title": "t"}]}
    clustered = {"cluster_count": 1, "software_solvable": 1, "top_clusters": [cluster]}
    with patch("districts.news_trends.social_miner.SocialMiner") as SM, \
         patch("districts.news_trends.problem_clusterer.ProblemClusterer") as PC, \
         patch("core.memory.episodic.EpisodicMemory"):
        SM.return_value.mine_all.return_value = mined
        PC.return_value.analyze.return_value = clustered
        res = _run(vp.execute())
    assert res["top_idea"] == ""
    assert res["validated_ideas"] == 0
    assert res["status"] != "ok"
    vp._draft_content.assert_not_called()


def test_pipeline_mining_failure_aborts_without_report(tmp_path):
    vp = _vp(tmp_path)
    vp._notify = MagicMock()
    with patch("districts.news_trends.social_miner.SocialMiner") as SM:
        SM.return_value.mine_all.return_value = {"status": "error", "error": "down", "count": 0, "posts": []}
        res = _run(vp.execute())
    assert res["status"] == "error"
    assert list(tmp_path.glob("venture_report_*.md")) == []
    vp._notify.assert_not_called()


def test_draft_prompt_echo_is_not_a_script():
    vp = VenturePipeline()
    vp.vchat = lambda p: p
    with patch("districts.content.script_generator.ScriptGenerator", side_effect=RuntimeError("x")):
        out = _run(vp._draft_content({"idea": "i"}))
    assert "script" not in out and "error" in out


def test_report_mirror_does_not_write_stray_dir_in_cwd(tmp_path, monkeypatch):
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)
    vp = _vp(tmp_path / "data")
    with patch("districts.news_trends.venture_pipeline.CONFIG", {"vault_path": ""}):
        vp._write_report({"count": 0}, {}, [], [])
    assert not (work / "02 Projects").exists()


def test_report_mirrors_into_configured_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    vp = _vp(tmp_path / "data")
    with patch("districts.news_trends.venture_pipeline.CONFIG", {"vault_path": str(vault)}):
        p = vp._write_report({"count": 0}, {}, [], [])
    assert (vault / "02 Projects" / p.name).exists()
