"""Quota ledger — soft free-tier budget tracking per provider/model.

Owner decision (2026-07-02): soft budget + auto-rotate. Track approximate
usage against each provider's free-plan limits (from model_catalog.yaml);
at >= 90% saturation the provider/model is DEPRIORITIZED — moved after the
fresh cloud options in the attempt order — until the UTC day rolls over.
NEVER hard-blocks: a saturated provider is still tried before the ollama
terminal fallback, and unknown limits mean saturation 0 (purely reactive
handling via provider_health).

Units per provider (from the catalog, no provider-specific code here):
  groq / github_models  → requests per day per model
  cerebras              → tokens per day per model (1M/day is what binds)
  cloudflare            → neurons per day account-wide (neurons ≈ tokens)
  mistral               → per-minute TPM/RPS (sliding in-memory window)

Persistence mirrors core/metering/budget_meter.py: JSON at
~/.vector_ca/metering/provider_quota.json, UTC-day keyed, 7-day prune,
threading.Lock, throttled saves. Under pytest (no injected path) the ledger
is in-memory only — tests stay deterministic and the real file untouched.
"""

import sys
import json
import time
import datetime
import os
import tempfile
import threading
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger

_QUOTA_FILE = Path.home() / ".vector_ca" / "metering" / "provider_quota.json"
SOFT_THRESHOLD = 0.90
_PROVIDER_KEY = "__provider__"
_LOCAL_SLUGS = frozenset({"ollama", "lmstudio", "vllm"})


def _today() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


class QuotaLedger:
    def __init__(self, path: Path | None = None,
                 soft_threshold: float = SOFT_THRESHOLD, clock=time.time):
        self._lock = threading.Lock()
        self._clock = clock
        self.soft_threshold = soft_threshold
        # pytest guard: default construction under pytest never touches disk.
        if path is None and "pytest" in sys.modules:
            self._path = None
        else:
            self._path = path or _QUOTA_FILE
        self._data: dict = {}          # {day: {provider: {bucket: {requests, tokens}}}}
        self._minute: dict = {}        # {(provider, bucket): deque[(ts, tokens)]}
        self._last_save = 0.0
        self._load()

    # ── persistence (budget_meter pattern) ───────────────────────────────────

    def _load(self) -> None:
        if self._path is None:
            return
        try:
            if self._path.exists():
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[VECTOR][quota] ledger load failed (fresh start): {e}")
            self._data = {}

    def _save(self) -> None:
        # Caller holds the lock. Throttled to <= 1 write/sec.
        if self._path is None:
            return
        now = self._clock()
        if now - self._last_save < 1.0:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            # A partial write would make the next process discard the entire
            # ledger as malformed JSON and silently forget consumed quota.
            # Flush a same-directory temporary file before atomic replacement.
            temp_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    dir=self._path.parent,
                    prefix=f".{self._path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as handle:
                    temp_path = Path(handle.name)
                    json.dump(self._data, handle)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_path, self._path)
                temp_path = None
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
            self._last_save = now
        except Exception as e:
            logger.debug(f"[VECTOR][quota] ledger save failed: {e}")

    def _prune(self) -> None:
        # Caller holds the lock. Keep 7 days.
        try:
            cutoff = (datetime.datetime.now(datetime.timezone.utc)
                      - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
            for day in [d for d in self._data if d < cutoff]:
                self._data.pop(day, None)
        except Exception as e:
            logger.debug("[VECTOR][quota] ledger prune failed: {}", e)

    # ── recording ─────────────────────────────────────────────────────────────

    def record(self, provider: str, model: str, tokens: int = 0) -> None:
        """One successful call: +1 request, +tokens (both provider-wide and
        per-model buckets), plus the in-memory sliding minute window."""
        try:
            with self._lock:
                day = self._data.setdefault(_today(), {})
                pbuckets = day.setdefault(provider, {})
                for bucket in (_PROVIDER_KEY, model):
                    b = pbuckets.setdefault(bucket, {"requests": 0, "tokens": 0})
                    b["requests"] += 1
                    b["tokens"] += max(0, int(tokens))
                now = self._clock()
                for bucket in (_PROVIDER_KEY, model):
                    dq = self._minute.setdefault((provider, bucket), deque())
                    dq.append((now, max(0, int(tokens))))
                self._prune()
                self._save()
        except Exception as e:
            logger.debug(f"[VECTOR][quota] record failed: {e}")

    # ── saturation ────────────────────────────────────────────────────────────

    def _counters(self, provider: str, bucket: str) -> tuple[int, int]:
        day = self._data.get(_today(), {})
        b = day.get(provider, {}).get(bucket, {})
        return int(b.get("requests", 0)), int(b.get("tokens", 0))

    def _minute_counters(self, provider: str, bucket: str) -> tuple[int, int]:
        dq = self._minute.get((provider, bucket))
        if not dq:
            return 0, 0
        cutoff = self._clock() - 60.0
        while dq and dq[0][0] < cutoff:
            dq.popleft()
        return len(dq), sum(t for _, t in dq)

    def _limits_for(self, provider: str, model: str | None):
        """(provider_limits, model_limits) from the catalog; None when absent."""
        try:
            from core.inference.model_catalog import get_catalog
            cat = get_catalog().get(provider)
            if cat is None:
                return None, None
            ml = None
            if model and cat.per_model_quota:
                m = cat.models.get(model)
                ml = m.limits if m else None
            return cat.limits, ml
        except Exception:
            return None, None

    def _bucket_saturation(self, provider: str, bucket: str, limits) -> float:
        if limits is None:
            return 0.0
        reqs, toks = self._counters(provider, bucket)
        mreqs, mtoks = self._minute_counters(provider, bucket)
        # Separate daily and per-minute fractions: they have fundamentally
        # different time horizons.  A brief RPM burst (e.g. 5/5 on Cerebras)
        # must NOT deprioritize a provider for the rest of the UTC day when
        # 99% of the daily budget is unused.  When daily limits exist they are
        # the primary deprioritization signal; per-minute limits only drive
        # deprioritization for providers with NO daily limits (e.g. Mistral).
        daily_fractions: list[float] = []
        minute_fractions: list[float] = []
        if limits.requests_per_day:
            daily_fractions.append(reqs / limits.requests_per_day)
        if limits.tokens_per_day:
            daily_fractions.append(toks / limits.tokens_per_day)
        if limits.neurons_per_day:          # neurons ≈ tokens heuristic
            daily_fractions.append(toks / limits.neurons_per_day)
        if limits.requests_per_min:
            minute_fractions.append(mreqs / limits.requests_per_min)
        if limits.tokens_per_min:
            minute_fractions.append(mtoks / limits.tokens_per_min)
        daily_sat = max(daily_fractions) if daily_fractions else 0.0
        if daily_fractions:
            return daily_sat
        return max(minute_fractions) if minute_fractions else 0.0

    def saturation(self, provider: str, model: str | None = None) -> float:
        """Worst-case fraction of any applicable free-tier limit. 0.0 when no
        limits are known (unknown = never deprioritized)."""
        try:
            with self._lock:
                plim, mlim = self._limits_for(provider, model)
                sat = self._bucket_saturation(provider, _PROVIDER_KEY, plim)
                if model and mlim is not None:
                    sat = max(sat, self._bucket_saturation(provider, model, mlim))
                return sat
        except Exception as e:
            logger.debug(f"[VECTOR][quota] saturation failed: {e}")
            return 0.0

    def deprioritized(self, provider: str, model: str | None = None) -> bool:
        return self.saturation(provider, model) >= self.soft_threshold

    # ── ordering ──────────────────────────────────────────────────────────────

    def reorder(self, pairs: list) -> list:
        """Soft deprioritization of (LLMProvider, model) attempt pairs:
        stable partition — fresh cloud pairs keep their order, saturated cloud
        pairs follow them, local pairs stay pinned at the very end (terminal
        fallback: a saturated cloud provider is still tried BEFORE ollama).
        Never drops a pair, never blocks."""
        try:
            fresh, saturated, local = [], [], []
            for pair in pairs:
                prov = pair[0]
                slug = getattr(prov, "slug", "") if prov is not None else ""
                if prov is None or slug in _LOCAL_SLUGS:
                    local.append(pair)
                elif self.deprioritized(slug, pair[1]):
                    saturated.append(pair)
                else:
                    fresh.append(pair)
            if saturated:
                logger.info("[VECTOR][quota] deprioritized (>= {:.0%} of free tier): {}",
                            self.soft_threshold,
                            [f"{getattr(p[0], 'slug', '?')}:{p[1]}" for p in saturated])
            return fresh + saturated + local
        except Exception as e:
            logger.debug(f"[VECTOR][quota] reorder failed (order unchanged): {e}")
            return pairs

    def snapshot(self) -> dict:
        """Diagnostics: today's counters per provider."""
        with self._lock:
            return json.loads(json.dumps(self._data.get(_today(), {})))


# Module singleton
_ledger: QuotaLedger | None = None
_ledger_lock = __import__("threading").Lock()


def get_quota_ledger() -> QuotaLedger:
    global _ledger
    if _ledger is None:
        with _ledger_lock:
            if _ledger is None:  # double-checked locking
                _ledger = QuotaLedger()
    return _ledger


if __name__ == "__main__":
    # real test, no mocks — in-memory ledger against real catalog limits
    import tempfile
    t = [1000.0]
    led = QuotaLedger(path=Path(tempfile.mkdtemp()) / "q.json", clock=lambda: t[0])
    for _ in range(13000):   # groq gpt-oss-20b: 1,000/day → 13k is well past the 90% deprioritize line
        led._data.setdefault(_today(), {}).setdefault("groq", {}).setdefault(
            "openai/gpt-oss-20b", {"requests": 0, "tokens": 0})["requests"] = 13000
        break
    ok = led.deprioritized("groq", "openai/gpt-oss-20b") is True
    ok &= led.deprioritized("groq", "openai/gpt-oss-120b") is False
    led.record("cerebras", "gpt-oss-120b", tokens=950_000)   # 95% of 1M/day
    ok &= led.deprioritized("cerebras", "gpt-oss-120b") is True
    ok &= led.saturation("opencode_zen", "big-pickle") == 0.0   # no limits → never
    print("✅ quota_ledger.py OK" if ok else "❌ FAILED")
