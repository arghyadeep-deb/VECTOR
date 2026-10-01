"""Audit phase 3: districts/data_analytics -- failures must not read as success,
table names from task params must be allow-listed."""
import asyncio
import math
import os
import sqlite3

import pytest

from districts.data_analytics.data_engineer import DataEngineer


@pytest.fixture(autouse=True)
def _isolated_episodic_db(tmp_path):
    import core.memory.episodic as episodic

    original = os.environ.get("VECTOR_DB_PATH")
    os.environ["VECTOR_DB_PATH"] = str(tmp_path / "audit_data_analytics.db")
    episodic.close_db_connection()
    try:
        yield
    finally:
        episodic.close_db_connection()
        if original is None:
            os.environ.pop("VECTOR_DB_PATH", None)
        else:
            os.environ["VECTOR_DB_PATH"] = original
        episodic.close_db_connection()


def _run(coro):
    return asyncio.run(coro)


# ---- data_engineer ---------------------------------------------------------

@pytest.fixture
def engineer(tmp_path):
    """DataEngineer over a plain tmp sqlite DB (never the real main DB)."""
    db = tmp_path / "de.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE policy_memory (action TEXT, score REAL)")
    conn.executemany("INSERT INTO policy_memory VALUES (?, ?)", [("a", 1.0)] * 3 + [("b", 2.0)] * 2)
    conn.commit()
    conn.close()

    agent = DataEngineer()
    agent.VECTOR_DB_PATH = db

    def _open():
        c = sqlite3.connect(db, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    agent._open_db = _open
    return agent


def test_contract_rejects_non_table_names_like_sqlite_master(engineer):
    res = engineer.generate_data_contract("sqlite_master")
    assert "error" in res and res["columns"] == []


def test_profile_rejects_non_table_names_like_sqlite_master(engineer):
    res = engineer.profile_dataset("sqlite_master")
    assert "error" in res and res["profile"] == {}


def test_profile_negative_limit_is_clamped_not_unbounded(engineer):
    res = engineer.profile_dataset("policy_memory", limit=-1)
    assert res["sampled_rows"] == 1  # old code: LIMIT -1 == every row (5)


def test_bronze_dedup_works_on_tables_without_content_column(engineer):
    res = engineer.run_bronze_to_silver("policy_memory", ["deduplicate"])
    assert res["input_rows"] == 5
    assert res["processed"] == 2  # old code: rowid in the key -> 5, dedup a no-op


def test_bronze_reports_truncation(engineer):
    engineer._B2S_ROW_CAP = 3
    res = engineer.run_bronze_to_silver("policy_memory", ["strip_whitespace"])
    assert res["truncated"] is True and res["input_rows"] == 3


def test_run_contract_unknown_table_is_status_error(engineer):
    res = _run(engineer.run({"type": "contract", "params": {"table": "nope"}}))
    assert res["status"] == "error"


def test_run_profile_unknown_table_is_status_error(engineer):
    res = _run(engineer.run({"type": "profile", "params": {"table": "nope"}}))
    assert res["status"] == "error"


def test_run_bronze_invalid_table_is_status_error(engineer):
    hp = engineer.health_points
    res = _run(engineer.run({"type": "bronze_to_silver", "params": {"table": "semantic_memory"}}))
    assert res["status"] == "error"
    assert engineer.health_points <= hp  # no award for a failed ETL


def test_run_bronze_db_unavailable_is_status_error(engineer):
    engineer._open_db = lambda: None
    res = _run(engineer.run({"type": "bronze_to_silver", "params": {"table": "policy_memory"}}))
    assert res["status"] == "error"


def test_health_null_check_quotes_odd_column_names(tmp_path):
    db = tmp_path / "odd.db"
    conn = sqlite3.connect(db)
    conn.execute('CREATE TABLE policy_memory (id INTEGER, "my col" TEXT)')
    conn.executemany("INSERT INTO policy_memory VALUES (?, NULL)", [(1,), (2,)])
    conn.commit()
    conn.close()
    agent = DataEngineer()
    agent.VECTOR_DB_PATH = db
    agent._open_db = lambda: sqlite3.connect(db, check_same_thread=False)
    health = agent.inspect_pipeline_health()
    # old code: the unquoted column errored and was silently skipped -> 0.0
    assert health["tables"]["policy_memory"]["nulls_pct"] == 50.0


# ---- analytics_reporter ----------------------------------------------------

@pytest.fixture
def reporter():
    from districts.data_analytics.analytics_reporter import AnalyticsReporter

    agent = AnalyticsReporter()
    agent.written = []

    def _write_note(**kw):
        agent.written.append(kw)

    agent._obsidian.write_note = _write_note
    return agent


def test_failed_db_pull_is_not_published_as_empty_report(reporter, monkeypatch):
    import districts.data_analytics.analytics_reporter as mod

    class _Boom:
        def __enter__(self):
            raise RuntimeError("db down")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod, "get_temp_cursor", lambda: _Boom())
    res = _run(reporter.run({"type": "weekly_analytics"}))
    assert res["status"] == "error" and "mining failed" in res["error"]
    assert reporter.written == []  # old code wrote a 0-event "all quiet" report


def test_run_tolerates_bad_days_and_null_params(reporter, monkeypatch):
    seen = []

    def _mine(days=7):
        seen.append(days)
        reporter.last_mine_error = None
        return []

    monkeypatch.setattr(reporter, "mine_episodic_data", _mine)
    r1 = _run(reporter.run({"type": "weekly_analytics", "params": {"days": "abc"}}))
    r2 = _run(reporter.run({"type": "weekly_analytics", "params": None}))
    assert seen == [7, 7]  # old: "abc" passed through; params=None raised AttributeError
    assert r2["status"] == "ok" and r1["status"] == "ok"


def test_report_does_not_show_zero_percent_for_zero_task_outcomes(reporter):
    metrics = {"total_events": 5, "task_success_rate": 0.0, "tasks_completed": 0, "tasks_failed": 0,
               "by_type": {}, "by_hour": {}}
    assert reporter.write_analytics_report(metrics, [], "brief") is True
    content = reporter.written[0]["content"]
    assert "0.0%" not in content and "n/a" in content


# ---- performance_benchmarker -----------------------------------------------

@pytest.fixture
def bench():
    from districts.data_analytics.performance_benchmarker import PerformanceBenchmarker

    return PerformanceBenchmarker()


def test_all_ollama_probes_failing_is_status_error(bench, monkeypatch):
    import core.inference.vectorcode_llm as llm

    def _boom(*a, **k):
        raise RuntimeError("ollama down")

    monkeypatch.setattr(llm, "chat", _boom)
    res = _run(bench.run({"type": "ollama", "params": {"n": 2}}))
    assert res["status"] == "error"  # old: status ok with avg=-1.0


def test_n_param_is_clamped(bench, monkeypatch):
    seen = []
    monkeypatch.setattr(bench, "benchmark_memory_ops", lambda n=10: seen.append(n) or {"store": {"avg": 0.1}, "recall": {"avg": 0.1}})
    _run(bench.run({"type": "memory", "params": {"n": 10**9}}))
    _run(bench.run({"type": "memory", "params": {"n": "x"}}))
    _run(bench.run({"type": "memory", "params": {"n": -4}}))
    assert seen == [100, 10, 1]


def test_null_params_do_not_crash_dispatch(bench, monkeypatch):
    monkeypatch.setattr(bench, "benchmark_routing", lambda n=5: {"avg": 0.001, "p95": 0.001})
    res = _run(bench.run({"type": "routing", "params": None}))
    assert res["status"] == "ok"


def test_full_benchmark_with_failed_probes_is_not_ok(bench, monkeypatch):
    results = {
        "timestamp": "t",
        "ollama_focus": {"avg": -1.0, "error": "down"},
        "ollama_coder": {"avg": -1.0},
        "decision_engine": {"avg": 0.01},
        "episodic_memory": {"store": {"avg": 0.001}, "recall": {"avg": 0.001}},
        "gnn_router": {"avg": 0.001},
    }
    monkeypatch.setattr(bench, "run_full_benchmark", lambda: results)
    monkeypatch.setattr(bench, "write_benchmark_report", lambda r: True)
    monkeypatch.setattr(bench, "_memory", type("M", (), {"store": lambda self, **k: None})())
    res = _run(bench.run({"type": "full_benchmark"}))
    assert res["status"] == "error"
    assert set(res["failed_components"]) == {"ollama_focus", "ollama_coder"}
    assert res["ollama_avg_ms"] is None  # old: -1000.0


def test_failed_probe_does_not_overwrite_good_baseline(bench):
    import json

    saved = {}

    class _Mem:
        def recall_fact(self, key):
            return {"value": json.dumps({"ollama_focus": {"avg": 0.5}})}

        def remember(self, key, value, **kw):
            saved["v"] = json.loads(value)

    bench._memory = _Mem()
    bench._obsidian.write_note = lambda **kw: None
    results = {"timestamp": "t", "ollama_focus": {"avg": -1.0}, "episodic_memory": {}}
    assert bench.write_benchmark_report(results) is True
    assert saved["v"]["ollama_focus"]["avg"] == 0.5  # old: -1


# ---- DataAnalytics (__init__) ----------------------------------------------

@pytest.fixture
def da(monkeypatch):
    from districts.data_analytics import DataAnalytics

    agent = DataAnalytics()
    agent.llm_calls = []
    monkeypatch.setattr(agent, "_call_ollama", lambda prompt, model=None: agent.llm_calls.append(prompt) or "{}")
    return agent


def test_unreadable_dataset_is_an_error_not_fabricated_analysis(da, tmp_path):
    bad = tmp_path / "data.csv"
    bad.mkdir()  # exists, but read_text raises
    res = da.analyze_dataset(str(bad))
    assert "error" in res
    assert da.llm_calls == [] and da.analyses == {}


def test_report_with_no_analyses_is_no_data_not_llm_fiction(da):
    res = da.generate_report("monthly")
    assert res["status"] == "no_data" and da.llm_calls == []


def test_statistical_outliers_counted_and_indexed_by_record(da):
    data = [{"a": 1}, {"b": 5}, {"a": 1}, {"a": 2}, {"a": 1}, {"a": 100}, {"a": 2}]
    res = da.detect_anomalies(data)
    outlier = [x for x in res["anomalies"] if x["type"] == "statistical_outlier"][0]
    assert outlier["record_index"] == 5  # old: index within the field's list (4)
    assert res["severity_breakdown"]["medium"] >= 1  # old: always 0


def test_non_finite_values_are_reported_not_fed_to_quartiles(da):
    data = [{"a": 1}, {"a": 2}, {"a": float("nan")}, {"a": 3}, {"a": 2}, {"a": 1}, {"a": 2}]
    res = da.detect_anomalies(data)
    assert any(x["type"] == "non_finite" for x in res["anomalies"])
    assert all(math.isfinite(x["boundaries"]["lower"]) for x in res["anomalies"] if x["type"] == "statistical_outlier")
