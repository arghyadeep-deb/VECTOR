"""Audit phase 3 — districts/karpathy_lab regression tests.

Each test fails on the pre-audit code and passes on the fixed code.
"""
from __future__ import annotations

import http.server
import json
import subprocess
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

import districts.karpathy_lab.autoresearch_runner as ar_mod
from districts.karpathy_lab.autoresearch_runner import AutoresearchRunner
from districts.karpathy_lab.data_prep import DataPrep
from districts.karpathy_lab.progress_tracker import ProgressTracker


# ── helpers ──────────────────────────────────────────────────────────────────

class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/missing"):
            body = b"<html>404 not found</html>"
            self.send_response(404)
        else:
            body = b"hello dataset line one\nhello dataset line two\n"
            self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # silence
        pass


@pytest.fixture
def http_server():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest.fixture
def data_prep(tmp_path, monkeypatch):
    dp = DataPrep()
    dp.data_dir = tmp_path / "datasets"
    dp.data_dir.mkdir()
    dp.memory = MagicMock()  # episodic store is not under test
    # Local test server is loopback; the SSRF guard (correctly) blocks it.
    import core.security.ssrf_guard as g
    allow = MagicMock()
    allow.check_url.return_value = MagicMock(safe=True)
    monkeypatch.setattr(g, "get_ssrf_guard", lambda: allow)
    return dp


# ── data_prep: HTTP error pages saved as datasets ────────────────────────────

def test_download_404_is_failed_and_leaves_no_file(data_prep, http_server):
    r = data_prep.download_dataset(f"{http_server}/missing/data.txt")
    assert r["status"] == "failed"
    assert not list(data_prep.data_dir.rglob("data.txt*"))


def test_download_200_ok_still_works(data_prep, http_server):
    r = data_prep.download_dataset(f"{http_server}/ok/data.txt")
    assert r["status"] == "downloaded"
    assert b"hello dataset" in open(r["path"], "rb").read()


# ── data_prep: CWE-22 via dataset_name ───────────────────────────────────────

def test_download_dataset_name_cannot_escape_data_dir(data_prep, http_server, tmp_path):
    evil = f"{http_server}/ok/../../../../{tmp_path.name}_escape/x.txt"
    r = data_prep.download_dataset(evil)
    if r.get("path"):
        from pathlib import Path
        assert Path(r["path"]).resolve().is_relative_to(data_prep.data_dir.resolve())


def test_download_absolute_dataset_name_rejected(data_prep, tmp_path):
    target = tmp_path / "abs_target"
    r = data_prep.download_dataset(str(target))
    assert r["status"] == "failed"
    assert not target.exists()


# ── data_prep: tokenizer crash on >256 symbols / empty input ─────────────────

def test_tokenize_large_vocab_non_latin_does_not_crash(data_prep, tmp_path):
    text = tmp_path / "hi.txt"
    text.write_text("".join(chr(0x0900 + i) for i in range(300)) * 3, encoding="utf-8")
    r = data_prep.tokenize_data(str(text), 8000)
    assert r["status"] == "success"
    assert r["token_dtype"] == "uint16"
    assert (tmp_path / "hi_tokens_8000.bin").stat().st_size == r["total_tokens"] * 2


def test_tokenize_empty_file_is_error_not_zero_division(data_prep, tmp_path):
    text = tmp_path / "empty.txt"
    text.write_text("", encoding="utf-8")
    assert data_prep.tokenize_data(str(text), 256)["status"] == "error"


def test_preprocess_zero_usable_lines_is_error(data_prep, tmp_path):
    src = tmp_path / "short.txt"
    src.write_text("a\nb\nc\n", encoding="utf-8")
    out = tmp_path / "out.txt"
    r = data_prep.preprocess_data(str(src), str(out))
    assert r["status"] == "error"
    assert not out.exists()


# ── progress_tracker ─────────────────────────────────────────────────────────

@pytest.fixture
def tracker(tmp_path, monkeypatch):
    t = ProgressTracker()
    t.runs_dir = tmp_path
    t.db_path = tmp_path / "runs.db"
    t._init_db()
    t.memory = MagicMock()
    monkeypatch.setattr(t, "_call_ollama", lambda prompt, model=None: "summary")
    return t


def test_report_only_includes_own_run_steps(tracker):
    tracker.start_run("run-a", {"training": {"max_steps": 10}})
    tracker.log_step(1, {"loss": 1.0}, "run-a")
    tracker.start_run("run-b", {"training": {"max_steps": 10}})
    tracker.log_step(1, {"loss": 9.0}, "run-b")
    rep = tracker.generate_report("run-a")
    assert rep["loss_summary"]["count"] == 1
    assert rep["loss_summary"]["max"] == 1.0


def test_report_zero_loss_not_reported_as_none(tracker):
    tracker.start_run("z", {})
    tracker.log_step(1, {"loss": 0.0}, "z")
    rep = tracker.generate_report("z")
    assert rep["loss_summary"]["min"] == 0.0
    assert rep["loss_summary"]["average"] == 0.0


def test_report_survives_llm_failure(tracker, monkeypatch):
    def boom(prompt, model=None):
        raise RuntimeError("llm down")
    monkeypatch.setattr(tracker, "_call_ollama", boom)
    tracker.start_run("r", {})
    rep = tracker.generate_report("r")
    assert "error" not in rep
    assert rep["ollama_summary"] is None


def test_report_path_cannot_escape_runs_dir(tracker, tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    tracker.runs_dir = runs
    tracker.start_run("../../escaped", {})
    rep = tracker.generate_report("../../escaped")
    from pathlib import Path
    assert Path(rep["report_path"]).resolve().is_relative_to(runs.resolve())
    assert not (tmp_path.parent / "escaped_report.json").exists()


def test_log_step_without_run_is_error_not_orphan_row(tracker):
    r = tracker.log_step(1, {"loss": 1.0})
    assert r.get("status") == "error"
    import sqlite3
    n = sqlite3.connect(str(tracker.db_path)).execute("SELECT COUNT(*) FROM step_logs").fetchone()[0]
    assert n == 0


# ── autoresearch_runner ──────────────────────────────────────────────────────

def _runner(monkeypatch, tmp_path, fake_run):
    agent = AutoresearchRunner(generation=1)
    agent._runs_dir = tmp_path
    agent._train_script = tmp_path / "train.py"
    agent._train_script.write_text("def train():\n    pass\n", encoding="utf-8")
    agent._memory = MagicMock()
    ok = MagicMock()
    ok.approved = True
    agent._gateway.execute = AsyncMock(return_value=ok)
    monkeypatch.setattr(agent, "_create_experiment_branch", lambda tag: None)
    proposals = []
    monkeypatch.setattr(
        agent, "_propose_improvement",
        lambda code, hist: proposals.append(1) or "def train():\n    pass  # changed\n",
    )
    monkeypatch.setattr(ar_mod.subprocess, "run", fake_run)
    return agent, proposals


async def test_failed_baseline_is_not_reported_ok(monkeypatch, tmp_path):
    def crash(cmd, **kw):
        r = MagicMock()
        r.returncode = 1
        r.stdout = ""
        r.stderr = "Traceback: CUDA OOM"
        return r
    agent, proposals = _runner(monkeypatch, tmp_path, crash)
    res = await agent.run({"type": "run_experiment_cycle"})
    assert res["status"] == "training_failed"
    assert res["improved"] is False
    assert not proposals, "must not LLM-rewrite a train.py whose baseline cannot run"
    assert agent._train_script.read_text() == "def train():\n    pass\n"


async def test_nonzero_exit_with_summary_block_is_failure(monkeypatch, tmp_path):
    def crash_after_print(cmd, **kw):
        r = MagicMock()
        r.returncode = 2
        r.stdout = "---\nval_bpb: 0.5\n---"
        r.stderr = ""
        return r
    agent, _ = _runner(monkeypatch, tmp_path, crash_after_print)
    assert agent._run_training() == {}


async def test_failed_experiment_is_reverted_and_labelled(monkeypatch, tmp_path):
    n = {"i": 0}

    def fake(cmd, **kw):
        n["i"] += 1
        r = MagicMock()
        if n["i"] == 1:
            r.returncode, r.stdout, r.stderr = 0, "---\nval_bpb: 0.9\n---", ""
        else:
            r.returncode, r.stdout, r.stderr = 1, "", "boom"
        return r
    agent, _ = _runner(monkeypatch, tmp_path, fake)
    res = await agent.run_experiment_cycle()
    assert res["best_val_bpb"] == 0.9 and res["improved"] is False
    assert agent._train_script.read_text() == "def train():\n    pass\n"
    lines = [json.loads(l) for l in agent._results_file().read_text().splitlines()]
    assert any(l.get("description", "").startswith("failed") for l in lines)


def test_best_result_ignores_failed_runs(monkeypatch, tmp_path):
    agent = AutoresearchRunner(generation=1)
    agent._runs_dir = tmp_path
    agent._save_result({"experiment": 0, "description": "baseline"})  # failed, no score
    assert agent._load_best_result() is None
    agent._save_result({"experiment": 1, "val_bpb": 1.2})
    assert agent._load_best_result()["val_bpb"] == 1.2


def test_experiment_branch_failure_returns_none(monkeypatch, tmp_path):
    agent = AutoresearchRunner(generation=1)

    def fake(cmd, **kw):
        r = MagicMock()
        r.returncode = 128
        return r
    monkeypatch.setattr(ar_mod.subprocess, "run", fake)
    assert agent._create_experiment_branch("t") is None
