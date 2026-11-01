"""Inference Observability Layer — unified LLM call telemetry for VECTOR.

Records every LLM call (provider, model, tokens, latency, caller, domain)
to a dedicated SQLite table. Exposes daily aggregation, provider/domain
breakdowns, quota saturation bridging, alert checks, and a daily report.

Bridges existing systems (QuotaLedger, ProviderHealth) rather than
replacing them. Privacy-preserving: no prompt/response content logged.

Persistence: <project_root>/data/telemetry.db (same DB as TelemetryStore).
Buffered writes: accumulates in memory, flushes at most once/second.
Thread-safe via threading.Lock.

Owner decision 2026-08-13: instrument first, collect baseline, do NOT
optimize routing until 24h+ of real data exists.
"""

import sys
import json
import time
import datetime
import sqlite3
import statistics
import threading
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger
from core.memory.db_utils import apply_pragmas

from core.runtime_paths import data_path

_DB_PATH = data_path("telemetry.db")

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS inference_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       REAL    NOT NULL,
    utc_date        TEXT    NOT NULL,
    caller_id       TEXT    NOT NULL DEFAULT '',
    district        TEXT    NOT NULL DEFAULT '',
    domain          TEXT    NOT NULL DEFAULT '',
    tier            TEXT    NOT NULL DEFAULT '',
    provider        TEXT    NOT NULL DEFAULT '',
    model           TEXT    NOT NULL DEFAULT '',
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    latency_ms      REAL    NOT NULL DEFAULT 0.0,
    providers_tried INTEGER NOT NULL DEFAULT 1,
    is_ollama       INTEGER NOT NULL DEFAULT 0,
    is_autonomous   INTEGER NOT NULL DEFAULT 0,
    sensitive       INTEGER NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'ok',
    error_kind      TEXT    NOT NULL DEFAULT '',
    metadata        TEXT    NOT NULL DEFAULT '{}'
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ic_date ON inference_calls(utc_date);",
    "CREATE INDEX IF NOT EXISTS idx_ic_provider ON inference_calls(provider, utc_date);",
    "CREATE INDEX IF NOT EXISTS idx_ic_caller ON inference_calls(caller_id, utc_date);",
    "CREATE INDEX IF NOT EXISTS idx_ic_domain ON inference_calls(domain, utc_date);",
    "CREATE INDEX IF NOT EXISTS idx_ic_autonomous ON inference_calls(is_autonomous, utc_date);",
]

_INSERT = """\
INSERT INTO inference_calls (
    timestamp, utc_date, caller_id, district, domain, tier,
    provider, model, input_tokens, output_tokens,
    latency_ms, providers_tried, is_ollama, is_autonomous,
    sensitive, status, error_kind, metadata
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

# Callers that originate from the autonomous loop (not user-triggered).
_AUTONOMOUS_CALLERS = frozenset({
    "coding_companion", "nudge_engine", "synthesis_bridge",
    "red_team_agent", "hypothesis_engine", "subconscious_loop",
    "anticipation",
})

# Caller prefixes that indicate autonomous operation.
_AUTONOMOUS_PREFIXES = ("vc_llm_", "governor_")

# Callers that are user-triggered (API / voice / HUD).
_USER_CALLERS = frozenset({
    "openai_compat", "api_command", "api_command_translate",
    "realtime_voice", "voice_classify", "voice_intent",
    "web_ui_chat", "web_ui_ws_chat", "web_ui_task",
    "terminal_ui_chat", "terminal_ui_bg_task", "channel_runtime_fallback",
    "api_tasks_submit", "api_inference_run",
})

# Caller-to-domain mapping for callers that have a known domain.
_CALLER_DOMAIN_MAP = {
    "coding_companion": "coding",
    "code_reviewer": "coding.review",
    "code_conductor_agent": "coding.review",
    "bug_hunter": "coding.review",
    "architect_bot": "coding.architecture",
    "test_writer": "coding",
    "python_reviewer": "coding.review",
    "fastapi_reviewer": "coding.review",
    "security_reviewer": "security",
    "stock_analyst": "finance.analysis",
    "fundamentals_bot": "finance.analysis",
    "technical_bot": "finance.analysis",
    "sentiment_bot": "finance.analysis",
    "trading_conductor_agent": "finance",
    "mock_interviewer": "interview_prep",
    "report_generator": "interview_prep",
    "feedback_analyst": "interview_prep",
    "company_researcher": "interview_prep",
    "content_strategist": "content.strategy",
    "script_generator": "content.script",
    "video_generator": "content.video",
    "caption_generator": "content.video",
    "call_screener": "calls",
    "transcription_bot": "calls",
    "voice_responder": "calls",
    "synthesis_bridge": "orchestration",
    "red_team_agent": "security",
    "hypothesis_engine": "reasoning",
    "nudge_engine": "orchestration",
}


def _today_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


def _now_epoch() -> float:
    return time.time()


def extract_domain(caller_id: str, model: str | None = None) -> str:
    """Extract domain from caller_id or model parameter.

    Priority:
    1. model="domain:X" → return X
    2. caller_id in _CALLER_DOMAIN_MAP → return mapped domain
    3. caller_id starts with "vc_llm_" → strip prefix, return rest
    4. caller_id starts with "governor_" → return "orchestration"
    5. Fall back to ""
    """
    # model="domain:coding.review"
    if model and model.startswith("domain:"):
        return model[7:]

    # Known caller → domain map
    if caller_id in _CALLER_DOMAIN_MAP:
        return _CALLER_DOMAIN_MAP[caller_id]

    # vc_llm_coding.review → coding.review
    if caller_id.startswith("vc_llm_"):
        remainder = caller_id[7:]
        # Strip trailing truncation (caller_id is truncated to 24 chars)
        # Keep the domain as-is even if truncated
        return remainder

    # governor calls → orchestration
    if caller_id.startswith("governor_"):
        return "orchestration"

    # User-triggered API calls
    if caller_id in ("api_command", "api_command_translate"):
        return "conversation"
    if caller_id == "openai_compat":
        return "api_proxy"
    if caller_id in ("realtime_voice", "voice_classify", "voice_intent"):
        return "voice"

    return ""


def is_autonomous_caller(caller_id: str) -> bool:
    """Classify caller as autonomous or user-triggered.

    Autonomous = initiated by VECTOR's internal loops/agents.
    User-triggered = initiated by external API calls or voice interaction.
    """
    if caller_id in _USER_CALLERS:
        return False
    if caller_id in _AUTONOMOUS_CALLERS:
        return True
    # vc_llm_* callers are district agents running autonomously
    if caller_id.startswith("vc_llm_"):
        return True
    # governor_* callers are autonomous routing decisions
    if caller_id.startswith("governor_"):
        return True
    # Default: treat unknown as autonomous (most VECTOR calls are)
    return True


class InferenceObservability:
    """Thin observability layer for inference calls.

    Records call-level telemetry to SQLite. Thread-safe (threading.Lock).
    Batched writes: accumulates in memory, flushes to DB at most once/sec.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._buffer: list[tuple] = []
        self._last_flush = 0.0

        if db_path is None and "pytest" in sys.modules:
            self._db_path = None
            self._conn = None
            return

        self._db_path = db_path or _DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False
        )
        apply_pragmas(self._conn)
        with self._lock:
            self._conn.execute(_CREATE_TABLE)
            for idx_sql in _CREATE_INDEXES:
                self._conn.execute(idx_sql)
            self._conn.commit()
        logger.debug("[VECTOR][observability] inference_calls table ready at {}", self._db_path)

    # ── Recording ──────────────────────────────────────────────────────────

    def record(
        self,
        caller_id: str = "system",
        district: str = "",
        domain: str = "",
        tier: str = "",
        provider: str = "",
        model: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0.0,
        providers_tried: int = 1,
        is_ollama: bool = False,
        is_autonomous: bool = True,
        sensitive: bool = False,
        status: str = "ok",
        error_kind: str = "",
        metadata: dict | None = None,
    ) -> None:
        """Record a single inference call. Non-blocking, buffered."""
        row = (
            _now_epoch(),
            _today_utc(),
            caller_id,
            district,
            domain,
            tier,
            provider,
            model,
            input_tokens,
            output_tokens,
            latency_ms,
            providers_tried,
            1 if is_ollama else 0,
            1 if is_autonomous else 0,
            1 if sensitive else 0,
            status,
            error_kind,
            json.dumps(metadata or {}),
        )
        with self._lock:
            self._buffer.append(row)
            self._maybe_flush()

    def flush(self) -> None:
        """Force-flush buffered records to disk — unconditional, ignores the
        opportunistic once/sec throttle (see _maybe_flush). Also used by
        _ensure_flushed() before every aggregation query, so a caller
        reading daily_summary()/provider_summary()/etc. immediately after
        record() always sees that record — the throttle only paces
        record()'s own internal auto-flush, never an explicit read/flush."""
        with self._lock:
            self._flush_locked(force=True)

    def _flush_locked(self, force: bool = False) -> None:
        """Flush buffer to DB. Caller must hold self._lock."""
        if not self._buffer or self._conn is None:
            return
        now = time.monotonic()
        if not force and now - self._last_flush < 1.0 and len(self._buffer) < 50:
            return  # throttle: flush at most once/sec unless buffer is large
        try:
            self._conn.executemany(_INSERT, self._buffer)
            self._conn.commit()
            self._buffer.clear()
            self._last_flush = now
        except Exception as e:
            logger.warning("[VECTOR][observability] flush failed: {}", e)
            # Don't clear buffer on failure — retry next time

    def _maybe_flush(self) -> None:
        """Flush if enough time has passed or buffer is large. Caller must hold lock."""
        if self._conn is None:
            return
        now = time.monotonic()
        if len(self._buffer) >= 50 or now - self._last_flush >= 1.0:
            self._flush_locked()

    # ── Aggregation queries ────────────────────────────────────────────────

    def _ensure_flushed(self) -> None:
        """Flush pending writes before querying — unconditional (force=True),
        so every aggregation read reflects records written moments ago,
        not just ones older than the once/sec opportunistic-flush throttle."""
        with self._lock:
            self._flush_locked(force=True)

    def daily_summary(self, date: str | None = None) -> dict[str, Any]:
        """Aggregate metrics for a given day (default: today UTC)."""
        self._ensure_flushed()
        if self._conn is None:
            return self._empty_summary()

        target_date = date or _today_utc()
        cur = self._conn.execute(
            """
            SELECT
                COUNT(*)                                           as total_calls,
                SUM(input_tokens)                                  as total_input_tokens,
                SUM(output_tokens)                                 as total_output_tokens,
                SUM(input_tokens + output_tokens)                  as total_tokens,
                AVG(latency_ms)                                    as avg_latency_ms,
                SUM(CASE WHEN is_ollama = 1 THEN 1 ELSE 0 END)    as ollama_calls,
                SUM(CASE WHEN is_autonomous = 1 THEN 1 ELSE 0 END) as autonomous_calls,
                SUM(CASE WHEN is_autonomous = 0 THEN 1 ELSE 0 END) as user_calls,
                SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END)   as error_calls,
                AVG(providers_tried)                                as avg_providers_tried,
                SUM(CASE WHEN sensitive = 1 THEN 1 ELSE 0 END)    as sensitive_calls,
                SUM(CASE WHEN providers_tried > 1 THEN 1 ELSE 0 END) as fallback_calls
            FROM inference_calls
            WHERE utc_date = ?
            """,
            (target_date,),
        )
        row = cur.fetchone()
        if row is None or row[0] == 0:
            return self._empty_summary()

        # Percentiles — need raw latency values
        latencies = self._get_latencies(target_date)
        retry = self._get_retry_stats(target_date)

        total_calls = row[0] or 0
        ollama_calls = row[5] or 0
        error_calls = row[8] or 0
        fallback_calls = row[11] or 0

        return {
            "date": target_date,
            "total_calls": total_calls,
            "total_input_tokens": row[1] or 0,
            "total_output_tokens": row[2] or 0,
            "total_tokens": row[3] or 0,
            "avg_latency_ms": round(row[4] or 0, 1),
            "p50_latency_ms": round(latencies.get("p50", 0), 1),
            "p95_latency_ms": round(latencies.get("p95", 0), 1),
            "ollama_calls": ollama_calls,
            "ollama_pct": round(ollama_calls / total_calls * 100, 1) if total_calls else 0,
            "cloud_calls": total_calls - ollama_calls,
            "autonomous_calls": row[6] or 0,
            "user_calls": row[7] or 0,
            "error_calls": error_calls,
            "failure_rate_pct": round(error_calls / total_calls * 100, 1) if total_calls else 0,
            "avg_providers_tried": round(row[9] or 1, 1),
            "sensitive_calls": row[10] or 0,
            # Raw fallback count (report #6) — calls where providers_tried > 1,
            # i.e. at least one provider was tried and failed/skipped before a
            # later one succeeded (or all failed). Distinct from
            # avg_providers_tried, which only shows the mean, not a count.
            "fallback_calls": fallback_calls,
            "fallback_rate_pct": round(fallback_calls / total_calls * 100, 1) if total_calls else 0,
            # Retry rate (report #8) — see _get_retry_stats() docstring for
            # exactly what this can and cannot observe.
            "retry_calls": retry["retry_calls"],
            "retry_rate_pct": retry["retry_rate_pct"],
            "retry_coverage_calls": retry["coverage_calls"],
        }

    def _get_retry_stats(self, date: str) -> dict[str, Any]:
        """Retry rate (report #8) — coverage-scoped, not codebase-wide.

        Only calls that went through ProviderClient._call_with_retry() (the
        cloud-provider drivers reached via provider_client.py's success
        path) stamp metadata.retry_attempts — see provider_client.py's
        "Observability only" comment at the _call_with_retry() success
        return. Ollama-direct calls (ollama_safe.py) and the vectorcode_llm
        legacy fallback chain never populate this field: ollama_safe.chat()
        has no key-pool/retry wrapper at all (Ollama is local, unauthenticated,
        single-daemon — nothing to retry against), and the legacy chain's
        _try_gemini/_try_anthropic/_try_openrouter each make exactly one
        HTTP attempt with no retry loop of their own.

        "retry_rate_pct" is therefore computed over retry_coverage_calls
        (rows where retry_attempts is present), not total_calls — mixing in
        the uninstrumented rows would silently understate the true retry
        rate among calls that CAN retry. Reported as retry_coverage_calls
        alongside so callers can see what fraction of the day's traffic this
        metric actually covers.
        """
        if self._conn is None:
            return {"retry_calls": 0, "retry_rate_pct": 0, "coverage_calls": 0}
        cur = self._conn.execute(
            "SELECT metadata FROM inference_calls WHERE utc_date = ? AND status = 'ok'",
            (date,),
        )
        coverage = 0
        retried = 0
        for (raw,) in cur.fetchall():
            try:
                meta = json.loads(raw) if raw else {}
            except Exception:
                continue
            attempts = meta.get("retry_attempts")
            if attempts is None:
                continue
            coverage += 1
            if attempts > 0:
                retried += 1
        return {
            "retry_calls": retried,
            "retry_rate_pct": round(retried / coverage * 100, 1) if coverage else 0,
            "coverage_calls": coverage,
        }

    def _get_latencies(self, date: str) -> dict[str, float]:
        """Compute latency percentiles for a given day."""
        if self._conn is None:
            return {}
        cur = self._conn.execute(
            "SELECT latency_ms FROM inference_calls WHERE utc_date = ? AND latency_ms > 0",
            (date,),
        )
        values = sorted(row[0] for row in cur.fetchall())
        if not values:
            return {"p50": 0, "p95": 0, "p99": 0}
        return {
            "p50": _percentile(values, 50),
            "p95": _percentile(values, 95),
            "p99": _percentile(values, 99),
        }

    def provider_summary(self, date: str | None = None) -> list[dict]:
        """Per-provider breakdown for a day."""
        self._ensure_flushed()
        if self._conn is None:
            return []
        target_date = date or _today_utc()
        cur = self._conn.execute(
            """
            SELECT
                provider,
                COUNT(*)                    as calls,
                SUM(input_tokens + output_tokens) as tokens,
                AVG(latency_ms)             as avg_latency_ms,
                SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END) as errors,
                AVG(providers_tried)         as avg_providers_tried
            FROM inference_calls
            WHERE utc_date = ?
            GROUP BY provider
            ORDER BY calls DESC
            """,
            (target_date,),
        )
        return [
            {
                "provider": row[0],
                "calls": row[1],
                "tokens": row[2] or 0,
                "avg_latency_ms": round(row[3] or 0, 1),
                "errors": row[4] or 0,
                "avg_providers_tried": round(row[5] or 1, 1),
            }
            for row in cur.fetchall()
        ]

    def domain_summary(self, date: str | None = None) -> list[dict]:
        """Per-domain breakdown for a day."""
        self._ensure_flushed()
        if self._conn is None:
            return []
        target_date = date or _today_utc()
        cur = self._conn.execute(
            """
            SELECT
                domain,
                COUNT(*)                    as calls,
                SUM(input_tokens + output_tokens) as tokens,
                AVG(latency_ms)             as avg_latency_ms
            FROM inference_calls
            WHERE utc_date = ? AND domain != ''
            GROUP BY domain
            ORDER BY calls DESC
            """,
            (target_date,),
        )
        return [
            {
                "domain": row[0],
                "calls": row[1],
                "tokens": row[2] or 0,
                "avg_latency_ms": round(row[3] or 0, 1),
            }
            for row in cur.fetchall()
        ]

    def model_summary(self, date: str | None = None) -> list[dict]:
        """Per-model breakdown for a day — tokens by model (report #4)."""
        self._ensure_flushed()
        if self._conn is None:
            return []
        target_date = date or _today_utc()
        cur = self._conn.execute(
            """
            SELECT
                model,
                COUNT(*)                    as calls,
                SUM(input_tokens)            as input_tokens,
                SUM(output_tokens)           as output_tokens,
                SUM(input_tokens + output_tokens) as tokens,
                AVG(latency_ms)             as avg_latency_ms
            FROM inference_calls
            WHERE utc_date = ? AND model != ''
            GROUP BY model
            ORDER BY tokens DESC
            """,
            (target_date,),
        )
        return [
            {
                "model": row[0],
                "calls": row[1],
                "input_tokens": row[2] or 0,
                "output_tokens": row[3] or 0,
                "tokens": row[4] or 0,
                "avg_latency_ms": round(row[5] or 0, 1),
            }
            for row in cur.fetchall()
        ]

    def autonomy_token_summary(self, date: str | None = None) -> dict[str, Any]:
        """Autonomous vs. user-triggered token consumption (reports #11, #12).

        Complements daily_summary()'s autonomous_calls/user_calls (call
        counts) with the token sums those counts don't carry."""
        self._ensure_flushed()
        if self._conn is None:
            return {"autonomous": {"calls": 0, "tokens": 0}, "user": {"calls": 0, "tokens": 0}}
        target_date = date or _today_utc()
        cur = self._conn.execute(
            """
            SELECT
                is_autonomous,
                COUNT(*)                    as calls,
                SUM(input_tokens)            as input_tokens,
                SUM(output_tokens)           as output_tokens,
                SUM(input_tokens + output_tokens) as tokens
            FROM inference_calls
            WHERE utc_date = ?
            GROUP BY is_autonomous
            """,
            (target_date,),
        )
        result = {
            "autonomous": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "tokens": 0},
            "user": {"calls": 0, "input_tokens": 0, "output_tokens": 0, "tokens": 0},
        }
        for row in cur.fetchall():
            key = "autonomous" if row[0] else "user"
            result[key] = {
                "calls": row[1] or 0,
                "input_tokens": row[2] or 0,
                "output_tokens": row[3] or 0,
                "tokens": row[4] or 0,
            }
        return result

    def token_exactness_summary(self, date: str | None = None) -> dict[str, Any]:
        """How many of the day's token counts are provider-reported exact
        values vs. char-count estimates — so token totals in every other
        report are never silently treated as more precise than they are.

        Exact: ProviderClient's cloud drivers (OpenAI-compat/Anthropic/
        Gemini) read prompt_tokens/completion_tokens straight from the
        provider's own API response usage field; ollama_safe.chat() and
        chat_stream() read prompt_eval_count/eval_count from the Ollama SDK
        response (both non-streaming and the streaming final chunk).
        Estimated: any path with no such field available — AirLLM,
        LiteLLM/Apple-FM/Gemma-C++ fallback engines, and the vectorcode_llm
        legacy chain's _try_gemini/_try_anthropic/_try_openrouter (which
        computes usage via _estimate_tokens(), a ~4-chars/token heuristic,
        because it never reads the provider's usage field).
        """
        self._ensure_flushed()
        if self._conn is None:
            return {"exact_calls": 0, "estimated_calls": 0, "unknown_calls": 0, "exact_pct": 0}
        target_date = date or _today_utc()
        cur = self._conn.execute(
            "SELECT metadata FROM inference_calls WHERE utc_date = ?",
            (target_date,),
        )
        exact = estimated = unknown = 0
        for (raw,) in cur.fetchall():
            try:
                meta = json.loads(raw) if raw else {}
            except Exception:
                meta = {}
            flag = meta.get("token_exact")
            if flag is True:
                exact += 1
            elif flag is False:
                estimated += 1
            else:
                unknown += 1
        total = exact + estimated + unknown
        return {
            "exact_calls": exact,
            "estimated_calls": estimated,
            "unknown_calls": unknown,
            "exact_pct": round(exact / total * 100, 1) if total else 0,
        }

    def caller_summary(self, date: str | None = None) -> list[dict]:
        """Per-caller breakdown for a day (top 20)."""
        self._ensure_flushed()
        if self._conn is None:
            return []
        target_date = date or _today_utc()
        cur = self._conn.execute(
            """
            SELECT
                caller_id,
                COUNT(*)                    as calls,
                SUM(input_tokens + output_tokens) as tokens,
                is_autonomous
            FROM inference_calls
            WHERE utc_date = ?
            GROUP BY caller_id
            ORDER BY calls DESC
            LIMIT 20
            """,
            (target_date,),
        )
        return [
            {
                "caller_id": row[0],
                "calls": row[1],
                "tokens": row[2] or 0,
                "is_autonomous": bool(row[3]),
            }
            for row in cur.fetchall()
        ]

    def hourly_snapshot(self) -> dict[str, Any]:
        """Last hour's metrics — for monitoring dashboards."""
        self._ensure_flushed()
        if self._conn is None:
            return self._empty_summary()

        one_hour_ago = _now_epoch() - 3600
        cur = self._conn.execute(
            """
            SELECT
                COUNT(*)                                           as total_calls,
                SUM(input_tokens + output_tokens)                  as total_tokens,
                AVG(latency_ms)                                    as avg_latency_ms,
                SUM(CASE WHEN is_ollama = 1 THEN 1 ELSE 0 END)    as ollama_calls,
                SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END)   as error_calls
            FROM inference_calls
            WHERE timestamp >= ?
            """,
            (one_hour_ago,),
        )
        row = cur.fetchone()
        if row is None or row[0] == 0:
            return {"total_calls": 0, "total_tokens": 0, "avg_latency_ms": 0,
                    "ollama_calls": 0, "error_calls": 0, "period": "last_hour"}

        total = row[0] or 0
        return {
            "period": "last_hour",
            "total_calls": total,
            "total_tokens": row[1] or 0,
            "avg_latency_ms": round(row[2] or 0, 1),
            "ollama_calls": row[3] or 0,
            "ollama_pct": round(row[3] / total * 100, 1) if total else 0,
            "error_calls": row[4] or 0,
        }

    # ── Quota saturation (bridged from QuotaLedger) ────────────────────────

    def quota_saturation(self) -> list[dict]:
        """Current quota saturation from QuotaLedger — bridged, not duplicated."""
        try:
            from core.inference.quota_ledger import get_quota_ledger
            ledger = get_quota_ledger()
            snapshot = ledger.snapshot()
            result = []
            for provider, models in snapshot.items():
                provider_data = models.get("__provider__", {})
                for model_id, data in models.items():
                    if model_id == "__provider__":
                        continue
                    try:
                        sat = ledger.saturation(provider, model_id)
                    except Exception:
                        sat = 0.0
                    result.append({
                        "provider": provider,
                        "model": model_id,
                        "requests": data.get("requests", 0),
                        "tokens": data.get("tokens", 0),
                        "saturation": round(sat * 100, 1),
                    })
            return sorted(result, key=lambda x: x["saturation"], reverse=True)
        except Exception as e:
            logger.debug("[VECTOR][observability] quota saturation unavailable: {}", e)
            return []

    # ── Alerts ─────────────────────────────────────────────────────────────

    def alert_check(self) -> list[str]:
        """Check alert conditions. Returns list of alert messages (empty = all clear).

        Conditions:
        1. Cloud quota saturation > 80% (any provider)
        2. Ollama fallback rate > 40% in last hour
        3. Provider failure count > 10 in last hour
        4. Total daily calls > 5000
        """
        alerts = []

        # 1. Quota saturation > 80%
        for sat in self.quota_saturation():
            if sat["saturation"] > 80:
                alerts.append(
                    f"QUOTA: {sat['provider']}:{sat['model']} at "
                    f"{sat['saturation']:.0f}% saturation "
                    f"({sat['requests']} req, {sat['tokens']} tok)"
                )

        # 2-4. Time-window checks
        if self._conn is not None:
            self._ensure_flushed()
            one_hour_ago = _now_epoch() - 3600
            today = _today_utc()

            # 2. Ollama fallback spike in last hour
            cur = self._conn.execute(
                """
                SELECT COUNT(*),
                       SUM(CASE WHEN is_ollama = 1 THEN 1 ELSE 0 END)
                FROM inference_calls WHERE timestamp >= ?
                """,
                (one_hour_ago,),
            )
            row = cur.fetchone()
            if row and row[0] and row[0] > 10:
                total_h = row[0]
                ollama_h = row[1] or 0
                ollama_pct = ollama_h / total_h * 100
                if ollama_pct > 40:
                    alerts.append(
                        f"OLLAMA SPIKE: {ollama_pct:.0f}% of last hour's "
                        f"{total_h} calls hit Ollama (>{40}% threshold)"
                    )

            # 3. Error burst in last hour
            cur = self._conn.execute(
                """
                SELECT provider, COUNT(*) as cnt
                FROM inference_calls
                WHERE timestamp >= ? AND status != 'ok'
                GROUP BY provider
                HAVING cnt > 10
                ORDER BY cnt DESC
                """,
                (one_hour_ago,),
            )
            for row in cur.fetchall():
                alerts.append(
                    f"FAILURES: {row[0]} had {row[1]} errors in the last hour"
                )

            # 4. Anomalous daily volume
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM inference_calls WHERE utc_date = ?",
                (today,),
            )
            row = cur.fetchone()
            if row and row[0] and row[0] > 5000:
                alerts.append(
                    f"VOLUME: {row[0]} calls today — above 5000 anomaly threshold"
                )

        # Log alerts
        for alert in alerts:
            logger.warning("[VECTOR][observability] ALERT: {}", alert)

        return alerts

    # ── Daily report ───────────────────────────────────────────────────────

    def generate_daily_report(self, date: str | None = None) -> str:
        """Generate human-readable daily report (Markdown format)."""
        target_date = date or _today_utc()
        summary = self.daily_summary(target_date)
        providers = self.provider_summary(target_date)
        domains = self.domain_summary(target_date)
        models = self.model_summary(target_date)
        callers = self.caller_summary(target_date)
        autonomy_tokens = self.autonomy_token_summary(target_date)
        exactness = self.token_exactness_summary(target_date)
        quota = self.quota_saturation()
        alerts = self.alert_check()

        lines = []
        lines.append(f"=== VECTOR Inference Daily Report — {target_date} ===")
        lines.append("")

        # Summary
        lines.append("Summary:")
        lines.append(f"  Total calls:          {summary['total_calls']:,}")
        lines.append(
            f"  Total tokens:         {summary['total_tokens']:,} "
            f"(in: {summary['total_input_tokens']:,} | out: {summary['total_output_tokens']:,}) "
            f"— {exactness['exact_pct']:.0f}% provider-exact, rest estimated"
        )
        lines.append(
            f"  Cloud calls:          {summary['cloud_calls']:,} "
            f"({100 - summary['ollama_pct']:.1f}%)"
        )
        lines.append(
            f"  Ollama calls:         {summary['ollama_calls']:,} "
            f"({summary['ollama_pct']:.1f}%)"
        )
        lines.append(f"  Avg latency:          {summary['avg_latency_ms']:,.0f}ms")
        lines.append(f"  P50 latency:          {summary['p50_latency_ms']:,.0f}ms")
        lines.append(f"  P95 latency:          {summary['p95_latency_ms']:,.0f}ms")

        auto_total = summary["autonomous_calls"]
        user_total = summary["user_calls"]
        all_calls = auto_total + user_total
        auto_pct = auto_total / all_calls * 100 if all_calls else 0
        lines.append(
            f"  Autonomous calls:     {auto_total:,} ({auto_pct:.1f}%) — "
            f"{autonomy_tokens['autonomous']['tokens']:,} tokens"
        )
        lines.append(
            f"  User-triggered:       {user_total:,} ({100 - auto_pct:.1f}%) — "
            f"{autonomy_tokens['user']['tokens']:,} tokens"
        )
        lines.append(f"  Error calls:          {summary['error_calls']:,} "
                     f"({summary['failure_rate_pct']:.1f}% failure rate)")
        lines.append(f"  Avg providers tried:  {summary['avg_providers_tried']:.1f}")
        lines.append(
            f"  Fallback calls:       {summary['fallback_calls']:,} "
            f"({summary['fallback_rate_pct']:.1f}% of calls tried >1 provider)"
        )
        if summary["retry_coverage_calls"]:
            lines.append(
                f"  Retry rate:           {summary['retry_rate_pct']:.1f}% "
                f"(of {summary['retry_coverage_calls']:,} cloud-provider calls measured — "
                f"Ollama-direct and legacy-chain calls have no retry loop to measure)"
            )
        else:
            lines.append("  Retry rate:           n/a (no cloud-provider calls with retry data today)")
        lines.append("")

        # Provider breakdown
        if providers:
            lines.append("Provider Breakdown:")
            for p in providers:
                lines.append(
                    f"  {p['provider']:<16s} {p['calls']:>5d} calls  "
                    f"{p['tokens']:>10,d} tokens  avg {p['avg_latency_ms']:>7,.0f}ms  "
                    f"{p['errors']} errors"
                )
            lines.append("")

        # Domain breakdown
        if domains:
            lines.append("Domain Breakdown:")
            for d in domains:
                lines.append(
                    f"  {d['domain']:<24s} {d['calls']:>5d} calls  "
                    f"{d['tokens']:>10,d} tokens"
                )
            lines.append("")

        # Model breakdown (report #4 — tokens by model)
        if models:
            lines.append("Model Breakdown (tokens by model):")
            for m in models:
                lines.append(
                    f"  {m['model']:<28s} {m['calls']:>5d} calls  "
                    f"{m['tokens']:>10,d} tokens "
                    f"(in: {m['input_tokens']:,} | out: {m['output_tokens']:,})  "
                    f"avg {m['avg_latency_ms']:>7,.0f}ms"
                )
            lines.append("")

        # Caller breakdown
        if callers:
            lines.append("Top Callers:")
            for c in callers:
                kind = "AUTO" if c["is_autonomous"] else "USER"
                lines.append(
                    f"  [{kind}] {c['caller_id']:<30s} {c['calls']:>5d} calls  "
                    f"{c['tokens']:>10,d} tokens"
                )
            lines.append("")

        # Alerts
        if alerts:
            lines.append("Alerts:")
            for alert in alerts:
                lines.append(f"  !! {alert}")
            lines.append("")

        # Quota saturation
        if quota:
            lines.append("Quota Saturation:")
            for q in quota[:10]:  # top 10
                flag = " — WARNING" if q["saturation"] > 80 else ""
                lines.append(
                    f"  {q['provider']}:{q['model']:<30s} "
                    f"{q['saturation']:>5.1f}% "
                    f"({q['requests']} req, {q['tokens']} tok){flag}"
                )
            lines.append("")

        return "\n".join(lines)

    # ── Maintenance ────────────────────────────────────────────────────────

    def prune(self, days: int = 30) -> int:
        """Delete records older than N days. Returns count deleted."""
        if self._conn is None:
            return 0
        self._ensure_flushed()
        cutoff = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=days)
        ).strftime("%Y-%m-%d")
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM inference_calls WHERE utc_date < ?",
                (cutoff,),
            )
            count = cur.fetchone()[0]
            if count > 0:
                self._conn.execute(
                    "DELETE FROM inference_calls WHERE utc_date < ?",
                    (cutoff,),
                )
                self._conn.commit()
                logger.info("[VECTOR][observability] pruned {} records older than {}", count, cutoff)
        return count

    # ── Helpers ────────────────────────────────────────────────────────────

    def _empty_summary(self) -> dict:
        return {
            "date": _today_utc(),
            "total_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "avg_latency_ms": 0,
            "p50_latency_ms": 0,
            "p95_latency_ms": 0,
            "ollama_calls": 0,
            "ollama_pct": 0,
            "cloud_calls": 0,
            "autonomous_calls": 0,
            "user_calls": 0,
            "error_calls": 0,
            "failure_rate_pct": 0,
            "avg_providers_tried": 1,
            "sensitive_calls": 0,
            "fallback_calls": 0,
            "fallback_rate_pct": 0,
            "retry_calls": 0,
            "retry_rate_pct": 0,
            "retry_coverage_calls": 0,
        }


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Compute percentile from a sorted list of values."""
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    k = (pct / 100) * (n - 1)
    f = int(k)
    c = f + 1
    if c >= n:
        return sorted_values[-1]
    d = k - f
    return sorted_values[f] + d * (sorted_values[c] - sorted_values[f])


# ── Singleton ──────────────────────────────────────────────────────────────

_observability_singleton: InferenceObservability | None = None
_observability_init = False


def get_inference_observability() -> InferenceObservability:
    """Return the singleton InferenceObservability instance."""
    global _observability_singleton, _observability_init
    if _observability_init:
        return _observability_singleton  # type: ignore[return-value]
    _observability_init = True
    try:
        _observability_singleton = InferenceObservability()
    except Exception as e:
        logger.warning("[VECTOR][observability] init failed, using no-op: {}", e)
        # Use a temp file that won't fail on any OS
        import tempfile
        _noop_path = Path(tempfile.gettempdir()) / "vector_obs_noop.db"
        _observability_singleton = InferenceObservability(db_path=_noop_path)
    return _observability_singleton


# ── Self-test ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    # Test with temp DB
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_path = Path(f.name)

    try:
        obs = InferenceObservability(db_path=test_path)

        # Record some test calls
        obs.record(
            caller_id="code_reviewer",
            district="coding",
            domain="coding.review",
            tier="coding",
            provider="groq",
            model="llama-3.3-70b",
            input_tokens=1500,
            output_tokens=800,
            latency_ms=234.5,
            providers_tried=1,
        )
        obs.record(
            caller_id="realtime_voice",
            district="",
            domain="voice",
            tier="conversation",
            provider="ollama",
            model="vector-focus",
            input_tokens=300,
            output_tokens=150,
            latency_ms=45.2,
            is_ollama=True,
            is_autonomous=False,
        )
        obs.record(
            caller_id="synthesis_bridge",
            district="intelligence",
            domain="orchestration",
            tier="agentic",
            provider="gemini",
            model="gemini-2.5-flash",
            input_tokens=5000,
            output_tokens=2000,
            latency_ms=890.3,
            providers_tried=2,
        )

        # Flush to disk
        obs.flush()

        # Test domain extraction
        assert extract_domain("code_reviewer") == "coding.review"
        assert extract_domain("vc_llm_finance.analysis") == "finance.analysis"
        assert extract_domain("system", "domain:security") == "security"
        assert extract_domain("governor_classify") == "orchestration"

        # Test autonomous classification
        assert is_autonomous_caller("code_reviewer") is True
        assert is_autonomous_caller("vc_llm_coding") is True
        assert is_autonomous_caller("realtime_voice") is False
        assert is_autonomous_caller("api_command") is False

        # Test daily summary
        summary = obs.daily_summary()
        assert summary["total_calls"] == 3
        assert summary["ollama_calls"] == 1
        assert summary["autonomous_calls"] == 2
        assert summary["user_calls"] == 1

        # Test provider summary
        providers = obs.provider_summary()
        assert len(providers) == 3
        assert providers[0]["provider"] in ("groq", "gemini", "ollama")

        # Test domain summary
        domains = obs.domain_summary()
        assert len(domains) == 3

        # Test report generation
        report = obs.generate_daily_report()
        assert "VECTOR Inference Daily Report" in report
        assert "groq" in report or "gemini" in report

        print("inference_observability OK")
    finally:
        if obs._conn is not None:
            obs._conn.close()
        test_path.unlink(missing_ok=True)
