# SPEC-05: Predictive Analytics & Forecasting Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This spec requires 2 parallel agents after shared schema phase.

**Goal:** Transform VECTOR's academic prediction modules (HypothesisEngine, CausalGraph, CounterfactualReasoner) into a production-grade predictive analytics pipeline that forecasts financial trends, health metrics, productivity patterns, and deadline risk — with Monte Carlo simulation, anomaly prediction, and actionable strategy recommendations.

**Architecture:** Build 5-layer prediction stack. TimeSeriesForecaster runs Prophet + ARIMA on historical data. CausalSimulator uses the existing causal graph for what-if Monte Carlo scenarios. AnomalyPredictor detects deviations from predicted baselines. StrategyRecommender converts predictions into actionable recommendations. PredictionStore tracks accuracy over time.

**Tech Stack:** Prophet (time series), statsmodels (ARIMA), numpy (Monte Carlo), SQLite + time-series tables, Pydantic (schemas), loguru (logging), asyncio (scheduled prediction cycles)

**Score:** Current 28/100 — Target 80/100

---

## 1. Problem Statement

### 1.1 Current Limitations

| Dimension | Score | Issue |
|-----------|-------|-------|
| Time-Series Forecasting | 15/100 | No operational forecasting. Financial, health, productivity data exists in context_engine but is never projected forward. |
| Causal Simulation | 30/100 | CausalGraph module exists but is academic — no production scenario testing, no Monte Carlo, no "what if" capability. |
| Anomaly Prediction | 20/100 | Anomalies are detected after they happen (e.g., ThreatScout finds suspicious process). No predictive anomaly detection — "this metric is diverging from forecast." |
| Strategy Recommendations | 10/100 | No actionable recommendations from data. VECTOR can analyze but cannot say "you'll miss deadline X, block 2 hours tomorrow." |
| Accuracy Tracking | 25/100 | Predictions are made and forgotten. No system tracks what was predicted vs what actually happened to improve models. |

### 1.2 Root Causes

1. **Academic, not operational:** The HypothesisEngine, CausalGraph, and CounterfactualReasoner in core/research_engine/ are designed for research queries, not operational forecasting. They lack production data pipelines, scheduled execution, and actionable output.

2. **No time-series infrastructure:** No Prophet, no ARIMA, no forecast data store. Historical data exists in context_engine (14 domains) and episodic memory but is not collected into time-series format suitable for forecasting.

3. **No prediction loop:** The autonomous loop has think/act/observe/reflect/schedule cycles but no "predict" cycle. Predictions are ad-hoc, not systematic.

4. **No feedback loop:** Predictions are made but never validated against reality. Without accuracy tracking, models cannot improve and user cannot trust outputs.

### 1.3 Measured Impact

- Financial forecast: none
- Deadline risk prediction: none
- Health trend projection: none
- What-if simulation: manual only via CausalGraph API
- Recommendation generation: none
- Prediction accuracy tracking: none
- User-facing predictions: zero

---

## 2. Current Architecture

### 2.1 Research Engine Prediction Modules

| Module | File(s) | Capability | Gap |
|--------|---------|-----------|-----|
| HypothesisEngine | `core/research_engine/...` | Generates testable hypotheses from data | No execution, no scheduling |
| CausalGraph | `core/research_engine/...` | Builds causal DAGs from observations | Academic, no production simulation |
| CounterfactualReasoner | `core/research_engine/...` | Answers "what if" queries | Research-only, no automated use |

### 2.2 Data Sources Available

| Source | Location | Update Frequency |
|--------|----------|-----------------|
| World State (context engine) | `core/loop/context_engine.py` | 14 domains, polled per cycle |
| Health metrics | `districts/health/`, `core/sensing/health_monitor.py` | Per cycle (camera), daily (sleep/exercise) |
| Security events | `districts/security/` (when SPEC-04 is done) | Real-time via event bus |
| Research activity | `core/research_engine/` | On-demand |
| System load | `core/sensing/health_monitor.py` | Per cycle (psutil) |
| Financial data | `districts/finance/` (if exists) | Polling |
| Task/deadline data | context engine domains | Per cycle |
| Phone node heartbeats | `phone_node/ambient_server.py` | Every 60s |

### 2.3 Existing Infrastructure

- **Context engine:** 14-domain world state with time-series capable structure
- **Episodic memory:** Stores past observations, can be queried for history
- **Config:** Pydantic V2 via core/config.py
- **Event bus:** Planned in specs-02 — this spec uses direct integration with event bus adapter later
- **SQLite:** Already used in several modules for persistent storage
- **Pushover:** For sending prediction-based alerts

---

## 3. Target Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Prediction Loop (new cycle)                  │
│           Runs every 15min / on_event: context_engine updated    │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│              TimeSeriesForecaster                                │
│  Prophet (trend + seasonality) + ARIMA (short-term)             │
│  Domains: financial, health, productivity, system, deadline     │
└──────┬──────────────────────────┬───────────────────────────────┘
       │                          │
       ▼                          ▼
┌──────────────┐       ┌──────────────────────┐
│ Prediction   │       │  CausalSimulator      │
│ Store        │       │  Monte Carlo (10k+)   │
│ (SQLite)     │       │  "what if" scenarios  │
└──────┬───────┘       └──────────┬───────────┘
       │                          │
       ▼                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              AnomalyPredictor                                    │
│  Detects deviation from forecasted baseline + confidence bands  │
│  "Heart rate is 2 std devs above forecast"                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              StrategyRecommender                                 │
│  Combines predictions + simulations → actionable suggestions    │
│  "Miss deadline at current pace → block 2h tomorrow"            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Output Channels       │
              ├────────────────────────┤
              │ • Context engine       │
              │ • Pushover (critical)  │
              │ • Dashboard            │
              │ • Episodic memory      │
              └────────────────────────┘
```

### 3.1 Prediction Cycle

1. **Data Collection (every 15 min):** Gather latest metrics from context engine, health monitor, system sensors, task/deadline data.
2. **Forecasting:** TimeSeriesForecaster runs Prophet + ARIMA on each metric. Produces point forecast + 80%/95% confidence intervals for 7-day horizon.
3. **Simulation (every 60 min):** CausalSimulator runs Monte Carlo what-if scenarios on the causal graph. E.g., "What if sleep drops to 5h for 3 days?" → effect on fatigue, productivity, health.
4. **Anomaly Detection (every cycle):** AnomalyPredictor compares actual values to forecasted ranges. Flags deviations > 1.5 std devs or outside 80% CI.
5. **Strategy (every cycle, if anomalies exist):** StrategyRecommender combines all predictions + simulation results → prioritized actionable recommendations.
6. **Store & Output:** All predictions stored in PredictionStore with timestamps. Critical predictions sent to Pushover. All written to context engine domain "predictions" and episodic memory.

---

## 4. Component Breakdown

### 4.1 TimeSeriesForecaster

**Purpose:** Generate time-series forecasts for all measurable VECTOR metrics with confidence intervals.

**File:** `districts/predictive_analytics/time_series_forecaster.py`

**Models:**
- **Prophet:** Primary model for metrics with strong seasonality (health, sleep, productivity, system load). Handles holidays, changepoints, missing data.
- **ARIMA (statsmodels):** Secondary model for short-term (1-48h) forecasts on stationary metrics. Used when Prophet is too slow or data is too sparse.
- **Ensemble:** Weighted average of Prophet + ARIMA for robust forecasts.

**Metrics to forecast:**
```python
FORECAST_METRICS = {
    "health.fatigue_score": {"model": "prophet", "period": "1h", "horizon_days": 7},
    "health.energy_level": {"model": "prophet", "period": "1h", "horizon_days": 3},
    "health.sleep_hours": {"model": "prophet", "period": "1d", "horizon_days": 14},
    "health.sleep_quality": {"model": "prophet", "period": "1d", "horizon_days": 14},
    "health.hrv": {"model": "prophet", "period": "1h", "horizon_days": 3},
    "health.heart_rate": {"model": "arima", "period": "15min", "horizon_days": 1},
    "productivity.focus_minutes": {"model": "prophet", "period": "1h", "horizon_days": 7},
    "productivity.tasks_completed": {"model": "prophet", "period": "1d", "horizon_days": 14},
    "system.cpu_percent": {"model": "arima", "period": "5min", "horizon_hours": 6},
    "system.ram_percent": {"model": "arima", "period": "5min", "horizon_hours": 6},
    "system.battery_level": {"model": "arima", "period": "5min", "horizon_hours": 4},
    "finance.portfolio_value": {"model": "prophet", "period": "1d", "horizon_days": 30},
    "deadline.risk_score": {"model": "prophet", "period": "1d", "horizon_days": 14},
    "security.alert_rate": {"model": "arima", "period": "1h", "horizon_days": 3},
}
```

**Class structure:**
```python
class TimeSeriesForecaster:
    async def initialize(self)
    async def forecast_all(self) -> dict[str, ForecastResult]
    async def forecast_metric(self, metric_key: str) -> ForecastResult
    async def _collect_history(self, metric_key: str, hours: int) -> pd.DataFrame
    async def _run_prophet(self, df: pd.DataFrame, horizon: str) -> ForecastResult
    async def _run_arima(self, df: pd.DataFrame, horizon: str) -> ForecastResult
    async def _run_ensemble(self, prophet_result, arima_result) -> ForecastResult
    def _calculate_confidence(self, forecast) -> tuple[float, float]  # 80% CI
    def get_feature_importance(self) -> dict
```

**ForecastResult schema:**
```python
@dataclass
class ForecastResult:
    metric_key: str
    timestamp: datetime
    model: str  # "prophet", "arima", "ensemble"
    horizon_days: int
    point_forecast: list[float]   # one per time step
    lower_80: list[float]
    upper_80: list[float]
    lower_95: list[float]
    upper_95: list[float]
    timestamps: list[datetime]
    actual_values: list[float | None]  # last known values
    confidence_score: float  # 0-1 based on recent accuracy
    metadata: dict
```

**Configuration:**
```python
FORECASTER_MODEL: str = "ensemble"  # "prophet", "arima", "ensemble"
FORECASTER_CYCLE_MINUTES: int = 15
FORECASTER_MIN_HISTORY_HOURS: int = 48
FORECASTER_PROPHET_CHANGEPOINT_PRIOR: float = 0.05
FORECASTER_PROPHET_SEASONALITY_PRIOR: float = 10.0
FORECASTER_ARIMA_ORDER: tuple = (5, 1, 2)
FORECASTER_CONFIDENCE_INTERVAL: float = 0.80
```

### 4.2 CausalSimulator

**Purpose:** Run Monte Carlo simulations on the causal graph to answer "what if" questions with probabilistic outcomes.

**File:** `districts/predictive_analytics/causal_simulator.py`

**Capabilities:**
- Load the causal graph from the existing CausalGraph module in research_engine
- Define scenario templates: "what if sleep_debt increases by X for Y days"
- Run Monte Carlo simulations: sample from probability distributions, propagate through graph, collect outcome distributions
- Support chained scenarios: multiple variables changing simultaneously
- Output: probability distributions for each outcome variable (fatigue, productivity, health_score, etc.)
- Calibrate simulation parameters against historical data

**Scenario templates (YAML):**
```yaml
scenarios:
  - id: "low_sleep_3_days"
    name: "3 Days of Low Sleep"
    description: "What happens if sleep drops below 5 hours for 3 consecutive days"
    interventions:
      - variable: "sleep_hours"
        distribution: "truncated_normal"
        params: { mean: 4.5, std: 0.5, min: 3.0, max: 5.5 }
        duration_hours: 72
    outcomes:
      - "fatigue_score"
      - "energy_level"
      - "productivity.focus_minutes"
      - "health.heart_rate"
      - "health.hrv"
    runs: 10000

  - id: "deadline_crunch"
    name: "Impending Deadline Crunch"
    description: "What happens if workload increases 50% for 5 days before deadline"
    interventions:
      - variable: "tasks_per_day"
        multiplier: 1.5
        duration_hours: 120
      - variable: "focus_minutes"
        distribution: "normal"
        params: { mean: 180, std: 45 }
        duration_hours: 120
    outcomes:
      - "fatigue_score"
      - "stress_level"
      - "deadline_risk_score"
      - "productivity.tasks_completed"
    runs: 5000

  - id: "exercise_improvement"
    name: "Exercise Regimen Impact"
    description: "Effect of 30min daily exercise for 14 days on all health metrics"
    interventions:
      - variable: "exercise_minutes"
        value: 30
        duration_hours: 336
    outcomes:
      - "health.sleep_quality"
      - "health.hrv"
      - "health.fatigue_score"
      - "health.heart_rate"
    runs: 5000
```

**Class structure:**
```python
class CausalSimulator:
    async def initialize(self, causal_graph_path: str = None)
    async def run_scenario(self, scenario_id: str) -> SimulationResult
    async def run_custom_scenario(self, interventions: list[Intervention],
                                   outcomes: list[str], runs: int) -> SimulationResult
    async def _load_graph(self) -> nx.DiGraph
    async def _monte_carlo(self, graph, interventions, outcomes, runs) -> SimulationResult
    def _sample_distribution(self, dist_config: dict) -> float
    def _propagate_intervention(self, graph, node, value) -> dict
    def _calculate_outcome_stats(self, samples: np.ndarray) -> dict
    async def suggest_scenarios(self) -> list[str]
```

**SimulationResult schema:**
```python
@dataclass
class SimulationResult:
    scenario_id: str
    timestamp: datetime
    runs: int
    outcomes: dict[str, OutcomeDistribution]
    execution_time_ms: float
    convergence: bool  # did results stabilize?

@dataclass
class OutcomeDistribution:
    mean: float
    median: float
    std: float
    p10: float  # 10th percentile
    p25: float
    p75: float
    p90: float
    samples: list[float]  # sampled values (for plots)
    histogram: list[tuple[float, float]]  # (bin_center, count)
```

**Configuration:**
```python
CAUSAL_SIMULATOR_ENABLED: bool = True
CAUSAL_SIMULATOR_CYCLE_MINUTES: int = 60
CAUSAL_SIMULATOR_DEFAULT_RUNS: int = 10000
CAUSAL_SIMULATOR_CONVERGENCE_THRESHOLD: float = 0.01  # std change < 1% = converged
CAUSAL_SIMULATOR_MAX_TIME_SECONDS: int = 300
CAUSAL_SIMULATOR_SCENARIO_DIR: str = "data/predictive/scenarios"
```

### 4.3 AnomalyPredictor

**Purpose:** Detect deviations from predicted baselines before they become problems — early warning system.

**File:** `districts/predictive_analytics/anomaly_predictor.py`

**Capabilities:**
- Compare actual metric values against forecasted ranges
- Detect: value outside 80% CI, value outside 95% CI, consecutive values trending away from forecast, rate of change exceeding forecasted rate
- Multi-signal anomalies: correlated deviations across multiple metrics (e.g., fatigue up + HR up + focus down)
- Severity scoring: number of std devs from forecast, persistence of deviation, number of correlated signals
- Configurable sensitivity per metric domain
- Generate AnomalyEvent with: metric, actual vs forecast, severity, trend direction, probable cause (from causal graph)

**Anomaly types:**
```python
class AnomalyType(Enum):
    VALUE_OUT_OF_RANGE = "value_out_of_range"     # single point outside CI
    TREND_DIVERGENCE = "trend_divergence"          # 3+ points trending away
    RATE_ACCELERATION = "rate_acceleration"        # change rate exceeds forecast
    COMPOUND_ANOMALY = "compound_anomaly"          # multi-metric correlation
    MISSING_EXPECTED = "missing_expected"          # expected data point not received
```

**Class structure:**
```python
class AnomalyPredictor:
    async def analyze(self, forecasts: dict[str, ForecastResult],
                      actuals: dict[str, float]) -> list[AnomalyEvent]
    async def _check_value_range(self, metric, actual, forecast) -> AnomalyEvent | None
    async def _check_trend(self, metric, history, forecast) -> AnomalyEvent | None
    async def _check_rate(self, metric, history, forecast) -> AnomalyEvent | None
    async def _detect_compound(self, anomalies: list) -> list[AnomalyEvent]
    def _score_severity(self, anomaly: AnomalyEvent) -> int
    def _estimate_cause(self, anomaly: AnomalyEvent, causal_graph) -> list[str]
    def _format_alert(self, anomaly: AnomalyEvent) -> str  # Pushover message
```

**Configuration:**
```python
ANOMALY_PREDICTOR_ENABLED: bool = True
ANOMALY_PREDICTOR_CI_THRESHOLD: float = 0.80  # outside 80% CI = anomaly
ANOMALY_PREDICTOR_TREND_POINTS: int = 3       # consecutive divergent points
ANOMALY_PREDICTOR_RATE_FACTOR: float = 2.0    # 2x forecasted rate
ANOMALY_PREDICTOR_MIN_SEVERITY_FOR_ALERT: int = 6
ANOMALY_PREDICTOR_PUSHOVER_ENABLED: bool = True
```

### 4.4 StrategyRecommender

**Purpose:** Convert predictions, simulations, and anomaly detections into actionable, prioritized recommendations.

**File:** `districts/predictive_analytics/strategy_recommender.py`

**Recommendation types:**
```python
class RecommendationType(Enum):
    TIME_MANAGEMENT = "time_management"       # "block 2h tomorrow"
    HEALTH_ACTION = "health_action"           # "take a break, fatigue predicted"
    PRODUCTIVITY_OPT = "productivity_opt"     # "focus time will peak at 10am"
    RISK_MITIGATION = "risk_mitigation"       # "deadline risk, consider scope reduction"
    SECURITY_WARNING = "security_warning"     # "attack probability increased"
    SYSTEM_MAINTENANCE = "system_maintenance" # "battery will drain in 2h at current rate"
    LIFESTYLE_SUGGESTION = "lifestyle_suggestion"  # "sleep quality down 3 days"
```

**Recommendation generation logic:**
```python
# For each domain, a set of rule-based generators:

class StrategyRecommender:
    async def generate_all(self) -> list[Recommendation]

    async def _time_management_recs(self) -> list[Recommendation]
        # If deadline_risk > 0.7 and pace < required → suggest blocking time
        # If focus_peak predicted in morning → suggest scheduling work then

    async def _health_recs(self) -> list[Recommendation]
        # If fatigue trending > 7/10 → suggest break
        # If sleep_deficit accumulating → suggest earlier bedtime
        # If exercise minutes below target → suggest activity

    async def _productivity_recs(self) -> list[Recommendation]
        # If tasks_completed < forecast → suggest workload reduction
        # If focus_time below baseline → suggest pomodoro technique

    async def _risk_recs(self) -> list[Recommendation]
        # If deadline at current pace > available time → suggest reprioritization
        # If system resource trend critical → suggest cleanup

    async def _composite_recs(self) -> list[Recommendation]
        # Cross-domain: e.g., low sleep + high deadline pressure → "rest is critical for deadline performance"
```

**Recommendation schema:**
```python
@dataclass
class Recommendation:
    id: str
    type: RecommendationType
    title: str                        # "Block 2 hours for project X tomorrow"
    description: str                  # Full explanation with evidence
    priority: int                     # 1 (critical) to 5 (suggestion)
    domain: str                       # "health", "productivity", "security", etc.
    evidence: list[str]               # supporting predictions/simulations
    actionable: bool                  # Can the user act on this?
    suggested_action: str | None      # "schedule_block", "take_break", etc.
    expires_at: datetime | None       # Recommendation TTL
    source: str                       # "forecast", "simulation", "anomaly", "composite"
```

**Configuration:**
```python
STRATEGY_RECOMMENDER_ENABLED: bool = True
STRATEGY_RECOMMENDER_CYCLE_MINUTES: int = 30
STRATEGY_RECOMMENDER_MIN_PRIORITY_FOR_PUSHOVER: int = 2
STRATEGY_RECOMMENDER_MAX_RECOMMENDATIONS: int = 5  # per cycle
STRATEGY_RECOMMENDER_TTL_HOURS: int = 24
```

### 4.5 PredictionStore

**Purpose:** Persistent storage for all predictions, simulations, and accuracy tracking.

**File:** `districts/predictive_analytics/prediction_store.py`

**SQLite schema:**
```sql
-- Forecast storage
CREATE TABLE forecasts (
    id TEXT PRIMARY KEY,
    metric_key TEXT NOT NULL,
    model TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    horizon_start TEXT NOT NULL,
    horizon_end TEXT NOT NULL,
    point_forecast TEXT NOT NULL,    -- JSON array
    lower_80 TEXT NOT NULL,          -- JSON array
    upper_80 TEXT NOT NULL,          -- JSON array
    lower_95 TEXT NOT NULL,          -- JSON array
    upper_95 TEXT NOT NULL,          -- JSON array
    timestamps TEXT NOT NULL,        -- JSON array
    confidence_score REAL,
    metadata TEXT                    -- JSON dict
);
CREATE INDEX idx_forecasts_metric ON forecasts(metric_key, generated_at);

-- Simulation storage
CREATE TABLE simulations (
    id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    run_at TEXT NOT NULL,
    runs INTEGER NOT NULL,
    outcomes TEXT NOT NULL,          -- JSON dict: metric → OutcomeDistribution
    execution_time_ms REAL,
    convergence INTEGER             -- boolean
);
CREATE INDEX idx_simulations_scenario ON simulations(scenario_id, run_at);

-- Anomaly storage
CREATE TABLE anomalies (
    id TEXT PRIMARY KEY,
    metric_key TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    anomaly_type TEXT NOT NULL,
    severity INTEGER NOT NULL,
    actual_value REAL,
    forecast_value REAL,
    deviation_std REAL,
    trend_direction TEXT,            -- "up", "down", "flat"
    probable_causes TEXT,            -- JSON array
    resolved INTEGER DEFAULT 0,
    resolved_at TEXT
);
CREATE INDEX idx_anomalies_metric ON anomalies(metric_key, detected_at);
CREATE INDEX idx_anomalies_severity ON anomalies(severity);

-- Accuracy tracking
CREATE TABLE prediction_accuracy (
    id TEXT PRIMARY KEY,
    forecast_id TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    predicted_at TEXT NOT NULL,
    actual_at TEXT NOT NULL,
    predicted_value REAL,
    actual_value REAL,
    error REAL,                      -- absolute error
    error_pct REAL,                  -- percentage error
    within_80_ci INTEGER,            -- boolean
    within_95_ci INTEGER,            -- boolean
    FOREIGN KEY (forecast_id) REFERENCES forecasts(id)
);
CREATE INDEX idx_accuracy_metric ON prediction_accuracy(metric_key, actual_at);

-- Recommendations
CREATE TABLE recommendations (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    priority INTEGER NOT NULL,
    domain TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    expires_at TEXT,
    actionable INTEGER DEFAULT 1,
    acted_upon INTEGER DEFAULT 0,
    acted_at TEXT,
    user_feedback TEXT               -- "helpful", "ignored", "dismissed"
);
```

**Accuracy calculation:**
```python
class PredictionStore:
    async def check_accuracy(self, metric_key: str = None) -> dict:
        # Compare all past forecasts to actual values at corresponding times
        # Returns: {rmse, mae, mape, within_80_pct, within_95_pct, by_model}
        # Updates prediction_accuracy table with new comparisons

    async def get_model_leaderboard(self) -> list[dict]:
        # Which model (prophet/arima/ensemble) performs best per metric domain
        # Returns sorted by MAPE ascending
```

**Configuration:**
```python
PREDICTION_DB_PATH: str = "data/predictive/predictions.db"
PREDICTION_RETENTION_DAYS: int = 90  # auto-prune older forecasts
PREDICTION_ACCURACY_CHECK_INTERVAL_HOURS: int = 24
```

---

## 5. Agent Dispatch Plan

### Agent A: TimeSeriesForecaster + AnomalyPredictor + PredictionStore

**Focus:** Time-series infrastructure, forecasting, anomaly detection, and storage.

**Tasks:**
1. Install dependencies: `prophet`, `statsmodels`, `pandas`
2. Implement `districts/predictive_analytics/prediction_store.py` — SQLite schema, CRUD, accuracy tracking
3. Implement `districts/predictive_analytics/time_series_forecaster.py` — Prophet + ARIMA + ensemble
4. Implement historical data collection from context_engine (14 domains)
5. Implement `districts/predictive_analytics/anomaly_predictor.py` — all 4 anomaly types
6. Wire forecast cycle into autonomous loop (predict_cycle coroutine)
7. Register config in core/config.py
8. Write unit tests

**Estimated effort:** 5-6 hours

### Agent B: CausalSimulator + StrategyRecommender + Dashboard Integration

**Focus:** Simulation, strategy, and user-facing prediction outputs.

**Tasks:**
1. Implement `districts/predictive_analytics/causal_simulator.py` — Monte Carlo, intervention propagation
2. Create scenario templates YAML (low_sleep_3_days, deadline_crunch, exercise_improvement)
3. Implement `districts/predictive_analytics/strategy_recommender.py` — all recommendation generators
4. Wire simulation + recommendation cycles into autonomous loop
5. Integrate with Pushover for critical recommendations
6. Write predictions to context engine (new domain: "predictions")
7. Write unit tests

**Estimated effort:** 4-5 hours

---

## 6. Implementation Steps

### Phase 1: Schema & Infrastructure

- [ ] **1.1** Create `districts/predictive_analytics/` directory and `__init__.py`
- [ ] **1.2** Create shared data models in `core/models/prediction_models.py` (ForecastResult, OutcomeDistribution, AnomalyEvent, Recommendation, Intervention)
- [ ] **1.3** Register all new config values in `core/config.py`
- [ ] **1.4** Add dependencies to requirements.txt: `prophet`, `statsmodels`, `pandas`, `networkx`
- [ ] **1.5** Create `data/predictive/` directory structure (scenarios/, db location)

### Phase 2: Prediction Store (Agent A)

- [ ] **2.1** Implement `prediction_store.py` with full SQLite schema
- [ ] **2.2** Implement CRUD: insert_forecast, query_forecasts, insert_anomaly, insert_recommendation, etc.
- [ ] **2.3** Implement accuracy tracking: match forecasts to actuals, compute RMSE/MAE/MAPE
- [ ] **2.4** Implement retention/pruning: delete records older than PREDICTION_RETENTION_DAYS
- [ ] **2.5** Unit tests for PredictionStore

### Phase 3: Time-Series Forecasting (Agent A)

- [ ] **3.1** Implement historical data collection from context_engine (last N hours per metric)
- [ ] **3.2** Implement Prophet wrapper: fit, predict with 80%/95% CI, handle holidays/changepoints
- [ ] **3.3** Implement ARIMA wrapper: fit, predict, auto-detect (p,d,q) via AIC
- [ ] **3.4** Implement ensemble: weighted average Prophet + ARIMA
- [ ] **3.5** Implement `forecast_all()` — run all configured metrics
- [ ] **3.6** Wire prediction cycle into autonomous loop (15-min interval)
- [ ] **3.7** Unit tests: forecast accuracy on synthetic data

### Phase 4: Anomaly Prediction (Agent A)

- [ ] **4.1** Implement VALUE_OUT_OF_RANGE detection
- [ ] **4.2** Implement TREND_DIVERGENCE detection (3+ consecutive divergent points)
- [ ] **4.3** Implement RATE_ACCELERATION detection
- [ ] **4.4** Implement COMPOUND_ANOMALY detection (multi-metric correlation)
- [ ] **4.5** Implement severity scoring and Pushover routing
- [ ] **4.6** Unit tests for AnomalyPredictor

### Phase 5: Causal Simulation (Agent B)

- [ ] **5.1** Integrate with existing CausalGraph module (load DAG from research_engine)
- [ ] **5.2** Implement Monte Carlo engine: distribution sampling, graph propagation, outcome collection
- [ ] **5.3** Implement scenario loader from YAML templates
- [ ] **5.4** Create 3 initial scenario templates
- [ ] **5.5** Implement convergence detection
- [ ] **5.6** Wire simulation cycle (60-min interval)
- [ ] **5.7** Unit tests for CausalSimulator

### Phase 6: Strategy Recommender (Agent B)

- [ ] **6.1** Implement time_management recommendation generator (deadline risk, focus forecasting)
- [ ] **6.2** Implement health recommendation generator (fatigue, sleep, exercise)
- [ ] **6.3** Implement productivity recommendation generator
- [ ] **6.4** Implement risk mitigation recommendation generator
- [ ] **6.5** Implement composite (cross-domain) recommendation generator
- [ ] **6.6** Implement priority scoring and dedup/relevance filtering
- [ ] **6.7** Wire Pushover for priority <= 2 recommendations
- [ ] **6.8** Write predictions/recommendations to context engine "predictions" domain
- [ ] **6.9** Unit tests for StrategyRecommender

### Phase 7: Integration & Hardening

- [ ] **7.1** Write integration test: forecast metric → store → accuracy check after actual arrives
- [ ] **7.2** Write integration test: anomaly detected → severity scored → Pushover sent
- [ ] **7.3** Write integration test: scenario loaded → Monte Carlo runs → outcome distributions
- [ ] **7.4** Write integration test: recommendation generated → written to context engine
- [ ] **7.5** Test accuracy tracking: inject forecasts with known error → verify RMSE/MAE/MAPE
- [ ] **7.6** Edge case: insufficient history for Prophet → fall back to ARIMA → fall back to naive (last value)
- [ ] **7.7** Edge case: Prophet model fails to converge → log warning, skip metric, continue
- [ ] **7.8** Edge case: causal graph empty → simulator logs warning, returns empty results
- [ ] **7.9** Edge case: no anomalies → AnomalyPredictor returns empty list, no action
- [ ] **7.10** Performance: forecaster handles 15 metrics in under 60s

---

## 7. Files to Create/Modify

### New Files

| File | Purpose | Agent |
|------|---------|-------|
| `districts/predictive_analytics/__init__.py` | Package init | Shared |
| `districts/predictive_analytics/prediction_store.py` | SQLite persistence + accuracy tracking | A |
| `districts/predictive_analytics/time_series_forecaster.py` | Prophet + ARIMA + ensemble | A |
| `districts/predictive_analytics/anomaly_predictor.py` | Deviation detection | A |
| `districts/predictive_analytics/causal_simulator.py` | Monte Carlo simulation | B |
| `districts/predictive_analytics/strategy_recommender.py` | Actionable recommendations | B |
| `core/models/prediction_models.py` | Shared Pydantic/dataclass schemas | Shared |
| `data/predictive/scenarios/default_scenarios.yaml` | Initial scenario templates | B |
| `tests/districts/predictive_analytics/test_prediction_store.py` | Tests | A |
| `tests/districts/predictive_analytics/test_time_series_forecaster.py` | Tests | A |
| `tests/districts/predictive_analytics/test_anomaly_predictor.py` | Tests | A |
| `tests/districts/predictive_analytics/test_causal_simulator.py` | Tests | B |
| `tests/districts/predictive_analytics/test_strategy_recommender.py` | Tests | B |

### Modified Files

| File | Change | Agent |
|------|--------|-------|
| `core/config.py` | Add all FORECASTER_*, CAUSAL_*, ANOMALY_*, STRATEGY_*, PREDICTION_* settings | Shared |
| `core/loop/autonomous_loop.py` | Add predict_cycle coroutine (forecast + anomaly + simulation + strategy) | A/B |
| `core/loop/context_engine.py` | Add "predictions" domain to world state | B |
| `requirements.txt` | Add prophet, statsmodels, pandas, networkx | Shared |

---

## 8. Success Criteria

| Criterion | Measurement | Threshold |
|-----------|------------|-----------|
| Forecast accuracy (7-day horizon) | MAPE across all metrics | < 20% (80% accurate) |
| Forecast accuracy (24h horizon) | MAPE across all metrics | < 10% |
| Anomaly detection rate | True positive rate on injected anomalies | >= 85% |
| Anomaly detection latency | Time from divergence to alert | < 1 prediction cycle (15 min) |
| Simulation convergence | Monte Carlo std deviation stabilizes | < 1% change after 5000 runs |
| Scenario execution time | Time to run 10K Monte Carlo samples | < 60 seconds |
| Recommendations generated | Actionable recommendations per day | >= 3 |
| Recommendation accuracy | User rates as "helpful" | >= 70% |
| Accuracy tracking | Forecast vs actual comparison runs | Daily |
| Pushover critical alerts | Anomalies with severity >= 6 sent | < 1min from detection |
| Prediction store | All forecasts, anomalies, recs persisted | 100% |
| Context engine integration | "predictions" domain populated | Every cycle |

### Known Limitations (Future Specs)

- **Deep learning models:** Prophet/ARIMA are classical. Future: add LSTM/Transformer for complex patterns.
- **Automated scenario discovery:** Current scenarios are hand-crafted. Future: auto-detect relevant scenarios from data.
- **Reinforcement learning:** Strategy recommender is rule-based. Future: RL for adaptive recommendation policies.
- **Multi-user predictions:** Currently single-user (VECTOR owner). Future: team/dept predictions.
- **Prediction market:** Aggregate multiple models with confidence weighting. Future: ensemble with Bayesian model averaging.

---

## 9. Dependencies

### Upstream Dependencies
- `core/loop/context_engine.py` — primary data source for forecasting (14-domain world state)
- `core/loop/autonomous_loop.py` — prediction cycle runs as coroutine
- `core/config.py` (Pydantic V2) — exists, needs extension
- `districts/health/` — provides health metrics for forecasting
- `districts/security/` (when SPEC-04 done) — provides security alert rate forecasting
- `phone_node/ambient_server.py` — provides heartbeat data
- `core/research_engine/` CausalGraph — simulation graph source

### External Dependencies
- `prophet>=1.1.5` (time-series forecasting)
- `statsmodels>=0.14.0` (ARIMA)
- `pandas>=2.1.0` (data manipulation)
- `networkx>=3.1` (causal graph operations — likely already installed)
- `numpy>=1.24` (numerical — likely already installed)
- `pyyaml>=6.0` (YAML scenario loader — likely already installed)

### Runtime Dependencies
- Write access to `data/predictive/` directory
- Context engine populated with at least 48h of history per metric
- SQLite3 (built into Python stdlib)

### Downstream Dependents
- specs-06 (Health Integration) — may consume health predictions for trend analysis
- specs-07 (Emergency Response) — may trigger on critical anomaly predictions
- specs-08 (AR Dashboard) — may visualize predictions in AR
- specs-12 (Adaptive Learning) — may adjust learning rate based on productivity predictions
