"""
VECTOR Budget Meter — per-agent token cost tracking with quota enforcement.

Tracks LLM token usage and cost per agent across hourly/daily/monthly windows.
Alerts when budgets exceeded. Persists to ~/.vector_ca/metering/budgets.json.

Ported from the agent OS kernel MeteringEngine.
VECTOR uses Ollama locally (free) but budget tracking still applies for:
  - Cloud fallback calls (Claude API in build sessions)
  - ElevenLabs TTS API calls
  - Any future paid API integrations
"""
from __future__ import annotations

__all__ = [
    "AgentBudget",
    "BudgetMeter",
    "BudgetStatus",
    "DEFAULT_PRICING",
    "estimate_cost",
    "get_budget_meter",
]


import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Literal

from loguru import logger

_METER_DIR = Path.home() / ".vector_ca" / "metering"
_BUDGET_FILE = _METER_DIR / "budgets.json"

# Per-million-token pricing (USD) — used for cost estimation
MODEL_PRICING: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-opus-4":    {"input": 15.0,  "output": 75.0},
    "claude-sonnet-4":  {"input": 3.0,   "output": 15.0},
    "claude-haiku-4":   {"input": 0.25,  "output": 1.25},
    # OpenAI
    "gpt-4o":           {"input": 5.0,   "output": 15.0},
    "gpt-4o-mini":      {"input": 0.15,  "output": 0.6},
    "o1":               {"input": 15.0,  "output": 60.0},
    # ElevenLabs (per 1k chars)
    "elevenlabs":       {"input": 0.18,  "output": 0.0},
    # Ollama local — free
    "ollama":           {"input": 0.0,   "output": 0.0},
}

DEFAULT_PRICING = {"input": 3.0, "output": 15.0}  # fallback for unknown cloud models

# Model families served locally via Ollama (always $0)
_OLLAMA_FREE_PREFIXES = frozenset({
    "qwen", "gemma", "llama", "mistral", "deepseek", "devstral", "phi",
    "codellama", "solar", "vicuna", "orca", "falcon", "mpt", "starcoder",
    "vector", "nomic", "yi", "dolphin", "openchat", "wizardcoder",
    "stablelm", "neural", "zephyr", "orca-mini", "tinyllama",
})


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Estimate USD cost for a completion.
    Ollama-served models (local) are always $0.
    Cloud models use per-million-token pricing.
    """
    base = model.split(":")[0].lower().replace("-", "").replace("_", "")
    # Explicit free entry
    if model.lower() in ("ollama", "local"):
        return 0.0
    # Known Ollama model families
    if any(base.startswith(prefix.replace("-", "")) for prefix in _OLLAMA_FREE_PREFIXES):
        return 0.0
    pricing = MODEL_PRICING.get(base, None)
    if pricing is None:
        # Unknown model — assume cloud, use Sonnet pricing as conservative estimate
        pricing = DEFAULT_PRICING
    return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000


@dataclass
class AgentBudget:
    """Budget configuration for a single agent."""
    agent_id: str
    hourly_usd: float = 0.50
    daily_usd: float = 5.0
    monthly_usd: float = 50.0
    # Counters (reset periodically)
    hourly_spent: float = 0.0
    daily_spent: float = 0.0
    monthly_spent: float = 0.0
    total_spent: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    last_reset_hourly: float = field(default_factory=time.time)
    last_reset_daily: float = field(default_factory=time.time)
    last_reset_monthly: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AgentBudget":
        return cls(**d)


@dataclass
class BudgetStatus:
    agent_id: str
    hourly_spent: float
    hourly_limit: float
    daily_spent: float
    daily_limit: float
    monthly_spent: float
    monthly_limit: float
    total_spent: float
    total_tokens: int
    blocked: bool
    block_reason: str = ""

    @property
    def hourly_pct(self) -> float:
        return (self.hourly_spent / self.hourly_limit * 100) if self.hourly_limit else 0

    @property
    def daily_pct(self) -> float:
        return (self.daily_spent / self.daily_limit * 100) if self.daily_limit else 0


class BudgetMeter:
    """
    Per-agent token cost tracker with quota enforcement.

    Usage:
        meter = BudgetMeter()
        # After each LLM call:
        allowed, reason = meter.check_quota("agent_001", "claude-sonnet-4")
        if allowed:
            meter.record("agent_001", "claude-sonnet-4", input_tokens=500, output_tokens=200)
        else:
            logger.warning("Budget exceeded: {}", reason)
    """

    _HOUR = 3600
    _DAY = 86400
    _MONTH = 2_592_000  # 30 days

    def __init__(self, budget_file: Path | None = None) -> None:
        self._file = budget_file or _BUDGET_FILE
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._budgets: dict[str, AgentBudget] = {}
        self._global_daily_limit: float = 20.0
        self._global_monthly_limit: float = 100.0
        self._load()

    # ── Quota check ───────────────────────────────────────────────────────────

    def check_quota(self, agent_id: str, model: str = "ollama") -> tuple[bool, str]:
        """
        Check if agent is within budget before making an LLM call.
        Returns (allowed, reason). reason is empty string if allowed.
        """
        with self._lock:
            budget = self._get_or_create(agent_id)
            self._maybe_reset(budget)

            if budget.hourly_spent >= budget.hourly_usd:
                return False, f"Hourly budget exceeded (${budget.hourly_spent:.4f} / ${budget.hourly_usd})"
            if budget.daily_spent >= budget.daily_usd:
                return False, f"Daily budget exceeded (${budget.daily_spent:.4f} / ${budget.daily_usd})"
            if budget.monthly_spent >= budget.monthly_usd:
                return False, f"Monthly budget exceeded (${budget.monthly_spent:.4f} / ${budget.monthly_usd})"

            # Global check -- reset every agent's own window first, not just
            # the requester's. An agent that goes quiet keeps a stale,
            # un-reset daily_spent forever (nothing else ever calls
            # _maybe_reset on it), so without this the global sum can
            # include a ghost charge from a prior day and wrongly block
            # every OTHER agent's real, current-day activity.
            for other in self._budgets.values():
                self._maybe_reset(other)
            all_daily = sum(b.daily_spent for b in self._budgets.values())
            if all_daily >= self._global_daily_limit:
                return False, f"Global daily budget exceeded (${all_daily:.2f} / ${self._global_daily_limit})"

            return True, ""

    def record(
        self,
        agent_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """Record token usage after a successful LLM call. Returns cost in USD."""
        cost = estimate_cost(model, input_tokens, output_tokens)
        with self._lock:
            budget = self._get_or_create(agent_id)
            self._maybe_reset(budget)
            budget.hourly_spent += cost
            budget.daily_spent += cost
            budget.monthly_spent += cost
            budget.total_spent += cost
            budget.total_input_tokens += input_tokens
            budget.total_output_tokens += output_tokens
            self._save()

        if cost > 0:
            logger.debug(
                "[VECTOR][budget] agent={} model={} tokens={}/{} cost=${:.6f}",
                agent_id, model, input_tokens, output_tokens, cost,
            )
        return cost

    def status(self, agent_id: str) -> BudgetStatus:
        with self._lock:
            budget = self._get_or_create(agent_id)
            self._maybe_reset(budget)
            allowed, reason = True, ""
            if budget.hourly_spent >= budget.hourly_usd:
                allowed, reason = False, "hourly limit"
            elif budget.daily_spent >= budget.daily_usd:
                allowed, reason = False, "daily limit"
            elif budget.monthly_spent >= budget.monthly_usd:
                allowed, reason = False, "monthly limit"
            return BudgetStatus(
                agent_id=agent_id,
                hourly_spent=budget.hourly_spent,
                hourly_limit=budget.hourly_usd,
                daily_spent=budget.daily_spent,
                daily_limit=budget.daily_usd,
                monthly_spent=budget.monthly_spent,
                monthly_limit=budget.monthly_usd,
                total_spent=budget.total_spent,
                total_tokens=budget.total_input_tokens + budget.total_output_tokens,
                blocked=not allowed,
                block_reason=reason,
            )

    def set_limits(
        self,
        agent_id: str,
        hourly_usd: float | None = None,
        daily_usd: float | None = None,
        monthly_usd: float | None = None,
    ) -> None:
        with self._lock:
            budget = self._get_or_create(agent_id)
            if hourly_usd is not None:
                budget.hourly_usd = hourly_usd
            if daily_usd is not None:
                budget.daily_usd = daily_usd
            if monthly_usd is not None:
                budget.monthly_usd = monthly_usd
            self._save()

    def all_statuses(self) -> list[BudgetStatus]:
        return [self.status(aid) for aid in list(self._budgets)]

    # ── Internals ─────────────────────────────────────────────────────────────

    def _get_or_create(self, agent_id: str) -> AgentBudget:
        if agent_id not in self._budgets:
            self._budgets[agent_id] = AgentBudget(agent_id=agent_id)
        return self._budgets[agent_id]

    def _maybe_reset(self, budget: AgentBudget) -> None:
        now = time.time()
        if now - budget.last_reset_hourly >= self._HOUR:
            budget.hourly_spent = 0.0
            budget.last_reset_hourly = now
        if now - budget.last_reset_daily >= self._DAY:
            budget.daily_spent = 0.0
            budget.last_reset_daily = now
        if now - budget.last_reset_monthly >= self._MONTH:
            budget.monthly_spent = 0.0
            budget.last_reset_monthly = now

    def _save(self) -> None:
        data = {aid: b.to_dict() for aid, b in self._budgets.items()}
        self._file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            self._budgets = {aid: AgentBudget.from_dict(d) for aid, d in data.items()}
        except Exception as e:
            logger.warning("[VECTOR][budget] load failed: {}", e)


_meter: BudgetMeter | None = None


def get_budget_meter() -> BudgetMeter:
    global _meter
    if _meter is None:
        _meter = BudgetMeter()
    return _meter


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        meter = BudgetMeter(budget_file=Path(d) / "budgets.json")
        # hourly_usd must exceed a single real call's cost below (~$0.0105
        # for 1000/500 tokens at Sonnet pricing) -- it previously didn't,
        # so status.blocked was already True on the very next assert.
        meter.set_limits("agent_001", hourly_usd=0.02, daily_usd=0.05)

        # Record some usage
        cost = meter.record("agent_001", "claude-sonnet-4", 1000, 500)
        assert cost > 0

        # Check status
        status = meter.status("agent_001")
        assert status.daily_spent > 0
        assert not status.blocked

        # Exhaust budget
        meter.record("agent_001", "claude-sonnet-4", 100000, 50000)
        allowed, reason = meter.check_quota("agent_001", "claude-sonnet-4")
        assert not allowed, "Should be blocked after exceeding budget"
        assert "budget exceeded" in reason.lower()

        # Ollama is free
        cost_local = estimate_cost("qwen3:14b", 10000, 5000)
        assert cost_local == 0.0

        print(f"OK budget_meter.py — cost tracking, quota enforcement, Ollama=free")
