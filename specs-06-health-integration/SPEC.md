# SPEC-06: Health Integration & Wearable Vitals Platform

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This spec requires 2 parallel agents after shared schema phase.

**Goal:** Transform VECTOR's camera-based fatigue monitor and manual sleep/exercise trackers into a comprehensive health platform with wearable API integration (Apple Health, Google Fit, Oura, Garmin, Whoop), real-time vitals dashboard, trend analysis, health advisor, and emergency detection.

**Architecture:** Build 5-layer health stack on top of existing `districts/health/` agents and `core/sensing/health_monitor.py`. WearableConnector polls APIs every 15 minutes. VitalsDashboard provides real-time React panel. TrendAnalyzer detects weekly/monthly anomalies. HealthAdvisor generates rule-based + LLM recommendations. EmergencyDetector monitors for critical vitals and escalates.

**Tech Stack:** pyhealth (Apple Health), Google Fit API, Oura API (if available), Garmin/Whoop web scraping or API stubs, FastAPI (dashboard), React (frontend), SQLite (metrics store), loguru (logging), asyncio (polling)

**Score:** Current 28/100 — Target 85/100

---

## 1. Problem Statement

### 1.1 Current Limitations

| Dimension | Score | Issue |
|-----------|-------|-------|
| Wearable Integration | 5/100 | BiometricsAggregator has connector stubs for Apple Health, Oura, Strava. They are absorbed VectorCode connectors that may not work without manual setup. No Google Fit, no Garmin, no Whoop. No reliable real-time data stream. |
| Real-Time Vitals | 15/100 | FatigueMonitor uses camera EAR (Eye Aspect Ratio) via MediaPipe. No heart rate, no HRV, no SpO2, no stress level, no skin temperature. Camera-only sensing is limited. |
| Trend Analysis | 20/100 | FatigueMonitor tracks session duration and EAR drops. No weekly/monthly trend analysis, no baseline comparison, no anomaly detection. |
| Health Recommendations | 25/100 | No automated health advice. VECTOR detects fatigue and recommends breaks but has no holistic view combining sleep, exercise, vitals, and activity. |
| Emergency Detection | 10/100 | No detection capability. If owner has a medical event (sustained high HR, fall detected via phone accelerometer, no movement for 12h), VECTOR cannot detect or escalate. |

### 1.2 Root Causes

1. **No wearable API integration:** BiometricsAggregator has stubs but no working real-time connector. The Apple Health connector relies on VectorCode which may not be running. No continuous poll loop.

2. **Camera-only sensing:** The only real-time health sensor is the camera (MediaPipe face detection → EAR calculation). This gives eye closure and head pose but zero physiological data.

3. **No historical analysis:** Data is collected per cycle but never analyzed over time. No baselines, no trends, no weekly comparisons. FatigueMonitor checks if current EAR < threshold but doesn't check if baselines have shifted.

4. **No emergency protocol:** VECTOR has no mechanism to detect medical emergencies. Phone node runs an ambient server with accelerometer data but it's not connected to any health emergency detection.

### 1.3 Measured Impact

- Real-time HR/HRV/SpO2: zero (no sensor)
- Wearable data sources: 0 working connectors out of 4 stubs
- Trend analysis: none — no baseline, no weekly comparison
- Health recommendations: only "take a break" from FatigueMonitor
- Emergency detection: zero capability
- Daily health summary: none
- Sleep/activity correlation: none

---

## 2. Current Architecture

### 2.1 districts/health/ Agents

| Agent | File | Capability | Gap |
|-------|------|-----------|-----|
| FatigueMonitor | `fatigue_monitor.py` | Camera EAR analysis via mediapipe, session duration tracking | No baseline, no trend, camera only |
| SleepTracker | `sleep_tracker.py` | Logs sleep hours (manual entry or inferred) | No sleep stage data, no quality metrics |
| ExerciseLogger | `exercise_logger.py` | Logs exercise sessions (manual entry) | No automatic activity detection |
| BiometricsAggregator | `biometrics_aggregator.py` | Stub for Apple Health, Oura, Strava via VectorCode | Connectors may not work, no real-time poll loop |

### 2.2 core/sensing/ Health Monitor

| Module | File | Capability |
|--------|------|-----------|
| HealthMonitor | `health_monitor.py` | Aggregates fatigue_score, energy_level, system_load, wearable stub |
| Camera (FaceDetector + FatigueMonitor) | `camera.py` | MediaPipe face detection, EAR calculation |

### 2.3 Existing Infrastructure

- **Episodic memory:** Stores health observations with timestamps
- **Context engine:** 14-domain world state including health domain
- **Pushover:** Alerting channel (already configured)
- **Phone node:** `phone_node/ambient_server.py` with accelerometer access (phone hardware)
- **ADB bridge:** `phone_node/adb_bridge.py` for Android phone communication
- **Config:** Pydantic V2 via core/config.py
- **Event bus:** Planned in specs-02 — this spec uses direct integration

---

## 3. Target Architecture

```
                         ┌─────────────────────────┐
                         │    VitalsDashboard      │
                         │  (Real-time React panel) │
                         └───────────┬─────────────┘
                                     │ Query
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
     ┌───────────────┐   ┌──────────────────┐   ┌──────────────────┐
     │ Wearable      │   │  TrendAnalyzer   │   │  Emergency       │
     │ Connector     │   │  (weekly/monthly │   │  Detector        │
     │ (polls 15min) │   │   + anomaly)     │   │  (critical vitals)│
     └───────┬───────┘   └────────┬─────────┘   └────────┬─────────┘
             │                    │                       │
             ▼                    ▼                       ▼
     ┌──────────────────────────────────────────────────────────┐
     │                    HealthAdvisor                          │
     │  (rule-based + LLM analysis → recommendations)            │
     └──────────────────────────┬───────────────────────────────┘
                                │
                                ▼
     ┌──────────────────────────────────────────────────────────┐
     │                    Metrics Store (SQLite)                 │
     │  wearables, trends, anomalies, recommendations, alerts   │
     └──────────────────────────────────────────────────────────┘
```

### 3.1 Data Flow

1. **WearableConnector** polls Apple Health (pyhealth), Google Fit API, and optionally Oura/Garmin/Whoop every 15 minutes. Writes metrics to SQLite store + episodic memory.
2. **TrendAnalyzer** runs every 60 minutes: computes rolling baselines (7-day, 30-day), detects deviations > 15% from baseline, identifies trends.
3. **HealthAdvisor** runs every 60 minutes: evaluates all metrics + trends + anomalies against rule-based + LLM health guidelines, produces prioritized recommendations.
4. **EmergencyDetector** runs every cycle (15 min): checks vitals against critical thresholds, detects sustained anomalies (e.g., HR > 120 for 30 min), checks for lack of movement via phone accelerometer, escalates via Pushover.
5. **VitalsDashboard** provides real-time + historical view via FastAPI + React, updated every 15 minutes.

---

## 4. Component Breakdown

### 4.1 WearableConnector

**Purpose:** Poll multiple wearable APIs to collect real-time health metrics.

**File:** `districts/health/wearable_connector.py`

**Support data sources:**
```python
class WearableSource(Enum):
    APPLE_HEALTH = "apple_health"       # via pyhealth
    GOOGLE_FIT = "google_fit"           # via Google Fit REST API
    OURA = "oura"                       # via Oura API v2
    GARMIN = "garmin"                   # via Garmin Connect (stub initially)
    WHOOP = "whoop"                     # via Whoop API (stub initially)
    PHONE_SENSORS = "phone_sensors"     # via ADB bridge accelerometer
```

**Metrics collected:**
```python
@dataclass
class WearableMetrics:
    timestamp: datetime
    source: WearableSource

    # Cardiac
    heart_rate: float | None         # bpm
    hrv: float | None                # ms (RMSSD)
    resting_heart_rate: float | None # bpm

    # Sleep
    sleep_hours: float | None
    sleep_quality: float | None      # 0-100 score
    sleep_stages: dict | None        # {"deep": 2.5, "light": 3.0, "rem": 1.5}
    sleep_onset: datetime | None
    wake_time: datetime | None

    # Activity
    steps: int | None
    active_calories: float | None
    exercise_minutes: float | None
    exercise_type: str | None
    activity_level: str | None       # "sedentary", "low", "moderate", "high"

    # Physiological
    spo2: float | None               # blood oxygen %
    stress_level: float | None       # 0-100
    skin_temperature: float | None   # celsius
    respiratory_rate: float | None   # breaths/min

    # Phone sensors
    accelerometer: dict | None       # {"x": 0.1, "y": 0.2, "z": 9.8}
    step_count_phone: int | None
    movement_detected: bool | None
    last_movement: datetime | None
```

**Connector implementations:**
```python
class AppleHealthConnector:
    async def authenticate(self) -> bool
    async def fetch_metrics(self) -> WearableMetrics
    async def fetch_historical(self, hours: int) -> list[WearableMetrics]
    # Uses pyhealth library to read HealthKit data

class GoogleFitConnector:
    async def authenticate(self) -> bool  # OAuth2 flow
    async def fetch_metrics(self) -> WearableMetrics
    async def fetch_historical(self, hours: int) -> list[WearableMetrics]
    # Uses Google Fitness REST API

class OuraConnector:
    async def authenticate(self) -> bool  # Personal Access Token
    async def fetch_metrics(self) -> WearableMetrics
    # Oura API v2 — heart rate, HRV, sleep, activity, readiness

class GarminConnector:
    async def authenticate(self) -> bool  # stub
    async def fetch_metrics(self) -> WearableMetrics  # returns None
    # Placeholder for future Garmin Connect integration

class WhoopConnector:
    async def authenticate(self) -> bool  # stub
    async def fetch_metrics(self) -> WearableMetrics  # returns None
    # Placeholder for future Whoop API integration

class PhoneSensorConnector:
    async def authenticate(self) -> bool  # ADB check
    async def fetch_metrics(self) -> WearableMetrics
    # Reads accelerometer + step counter via ADB bridge
    # Detects movement vs. stillness
```

**WearableConnector orchestrator:**
```python
class WearableConnector:
    def __init__(self):
        self.connectors: dict[WearableSource, BaseConnector] = {}
        self.active_sources: set[WearableSource] = set()

    async def initialize(self):
        # Load config, init all configured connectors, test auth
        # Gracefully handle unavailable sources

    async def poll_all(self) -> dict[WearableSource, WearableMetrics | None]:
        # Poll all active connectors in parallel
        # Returns dict with results (None if source unavailable)

    async def poll_source(self, source: WearableSource) -> WearableMetrics | None

    async def _store_metrics(self, metrics: dict[WearableSource, WearableMetrics]):
        # Write to SQLite store + episodic memory
```

**Configuration:**
```python
WEARABLE_ENABLED_SOURCES: list[str] = []  # user must configure
WEARABLE_POLL_INTERVAL_SECONDS: int = 900  # 15 min
WEARABLE_APPLE_HEALTH_ENABLED: bool = False
WEARABLE_GOOGLE_FIT_ENABLED: bool = False
WEARABLE_GOOGLE_FIT_CLIENT_ID: str = ""
WEARABLE_GOOGLE_FIT_CLIENT_SECRET: str = ""
WEARABLE_OURA_TOKEN: str = ""
WEARABLE_GARMIN_ENABLED: bool = False
WEARABLE_WHOOP_ENABLED: bool = False
WEARABLE_PHONE_SENSORS_ENABLED: bool = True  # ADB bridge is always available
WEARABLE_HISTORY_BACKFILL_HOURS: int = 168  # backfill 7 days on first run
```

### 4.2 VitalsDashboard

**Purpose:** Real-time visualization of health metrics from all wearable sources plus camera-based fatigue.

**Technology:** FastAPI backend + React frontend, REST + WebSocket.

**File:** `dashboard/health_dashboard/`

**Backend (dashboard/health_dashboard/api.py):**
- `GET /api/vitals/current` — latest aggregate metrics from all sources
- `GET /api/vitals/history?metric=heart_rate&hours=24` — time-series data
- `GET /api/vitals/summary` — today's summary (sleep, activity, HR avg, etc.)
- `GET /api/trends` — weekly/monthly trends with % change
- `GET /api/anomalies?days=7` — recent health anomalies
- `GET /api/recommendations` — active health recommendations
- `GET /api/emergency/status` — emergency detection system health
- `WS /api/ws/vitals` — WebSocket pushing live vitals on poll
- `GET /api/wearables/status` — which connectors are active/healthy

**Frontend (dashboard/health_dashboard/):**
- **Live vitals card:** Heart rate (with sparkline), HRV, SpO2, stress level — updated every 15 min
- **Sleep card:** Last night's sleep hours + quality + stages (deep/light/REM bar chart)
- **Activity card:** Steps, active calories, exercise minutes with daily goal progress
- **Trends panel:** 7-day and 30-day trend lines for key metrics with % change indicators
- **Anomalies feed:** Recent deviations from baseline (e.g., "HRV dropped 22% from baseline")
- **Recommendations:** Prioritized health advice cards from HealthAdvisor
- **Emergency status:** Green/yellow/red indicator for emergency detection system
- **Wearable sources:** Status indicators per source (connected/disconnected/error)

**Backend implementation:**
```python
class HealthDashboardAPI:
    def __init__(self, store: MetricsStore, analyzer: TrendAnalyzer,
                 advisor: HealthAdvisor, emergency: EmergencyDetector):
        self.store = store
        self.analyzer = analyzer
        self.advisor = advisor
        self.emergency = emergency
        self.app = FastAPI()
        self._register_routes()

    def _register_routes(self):
        self.app.get("/api/vitals/current")(self.get_current_vitals)
        self.app.get("/api/vitals/history")(self.get_vitals_history)
        self.app.get("/api/vitals/summary")(self.get_daily_summary)
        self.app.get("/api/trends")(self.get_trends)
        self.app.get("/api/anomalies")(self.get_anomalies)
        self.app.get("/api/recommendations")(self.get_recommendations)
        self.app.get("/api/emergency/status")(self.get_emergency_status)
        self.app.websocket("/api/ws/vitals")(self.ws_vitals)
```

**How to serve:**
- FastAPI app runs on port 8855 (configurable)
- Serves React static build from `dashboard/health_dashboard/build/`
- VECTOR autonomous loop starts dashboard as background task if enabled

**Configuration:**
```python
HEALTH_DASHBOARD_ENABLED: bool = False  # opt-in
HEALTH_DASHBOARD_PORT: int = 8855
HEALTH_DASHBOARD_HOST: str = "127.0.0.1"
HEALTH_DASHBOARD_REFRESH_MS: int = 5000
```

### 4.3 TrendAnalyzer

**Purpose:** Compute rolling baselines, detect trends, and identify anomalies in health metrics over time.

**File:** `districts/health/trend_analyzer.py`

**Capabilities:**
- **Baseline computation:** Rolling 7-day and 30-day baselines for all numeric metrics (mean, std, percentiles)
- **Anomaly detection:** Any metric deviating > configurable threshold (default 15%) from baseline triggers anomaly event
- **Trend classification:** For each metric, classify trend as: improving, declining, stable, volatile
- **Weekly comparison:** Compare current week to previous week with % change
- **Correlation detection:** Identify correlated metric pairs (e.g., HRV decline + sleep quality decline)
- **Circadian pattern detection:** Identify time-of-day patterns (e.g., HR highest at 2pm, lowest at 4am)

**Trend schema:**
```python
@dataclass
class MetricTrend:
    metric_key: str                      # "heart_rate", "hrv", etc.
    current_value: float
    baseline_7d_mean: float
    baseline_7d_std: float
    baseline_30d_mean: float
    baseline_30d_std: float
    delta_7d_pct: float                 # % change from 7d baseline
    delta_30d_pct: float                # % change from 30d baseline
    trend: str                           # "improving", "declining", "stable", "volatile"
    stability: float                     # 0-1 (coefficient of variation inverse)
    anomalies: list[MetricAnomaly]

@dataclass
class MetricAnomaly:
    metric_key: str
    detected_at: datetime
    value: float
    baseline: float
    deviation_pct: float                 # how far from baseline
    direction: str                       # "above", "below"
    severity: int                        # 1-10
    resolved: bool                       # auto-resolved when returns to normal
    resolved_at: datetime | None

@dataclass
class WeeklyComparison:
    week_start: datetime
    week_end: datetime
    metrics: dict[str, MetricChange]     # metric → {previous, current, change_pct}
    summary: str                         # "Positive: sleep +8%, HRV +12%. Negative: steps -15%"
```

**Class structure:**
```python
class TrendAnalyzer:
    async def compute_all_trends(self) -> dict[str, MetricTrend]
    async def compute_trend(self, metric_key: str, hours: int = 720) -> MetricTrend
    async def detect_anomalies(self) -> list[MetricAnomaly]
    async def compute_weekly_comparison(self) -> WeeklyComparison
    async def _load_history(self, metric_key: str, hours: int) -> list[dict]
    def _analyze_trend(self, values: list[float]) -> str
    def _detect_correlations(self) -> list[tuple[str, str, float]]
    def _detect_circadian_pattern(self, metric: str) -> dict[int, float]

    # Called by the analysis cycle
    async def full_analysis(self) -> dict:
        # Returns combined: trends, anomalies, weekly, correlations, circadian
```

**Configuration:**
```python
TREND_ANALYZER_CYCLE_MINUTES: int = 60
TREND_ANALYZER_ANOMALY_THRESHOLD_PCT: float = 15.0  # deviation % to flag
TREND_ANALYZER_ANOMALY_MIN_SEVERITY: int = 5
TREND_ANALYZER_BASELINE_DAYS: list[int] = [7, 30]
TREND_ANALYZER_WEEKLY_COMPARISON_DAY: str = "Monday"  # day of week for weekly summary
```

### 4.4 HealthAdvisor

**Purpose:** Generate health recommendations by combining real-time metrics, trends, anomalies, and LLM analysis.

**File:** `districts/health/health_advisor.py`

**Recommendation categories:**
```python
class HealthRecommendationType(Enum):
    SLEEP_HYGIENE = "sleep_hygiene"             # sleep schedule, environment
    ACTIVITY_EXERCISE = "activity_exercise"      # movement, exercise type/duration
    STRESS_MANAGEMENT = "stress_management"      # breaks, meditation, HRV biofeedback
    HYDRATION_NUTRITION = "hydration_nutrition"  # water intake, meal timing
    ERGONOMICS = "ergonomics"                   # posture, screen breaks, workstation setup
    MEDICAL_ATTENTION = "medical_attention"     # concerning metrics → see doctor
    LIFESTYLE_BALANCE = "lifestyle_balance"      # work-life balance, screen time
    ROUTINE_OPTIMIZATION = "routine_optimization" # optimal work/rest scheduling
```

**Rule-based generators:**
```python
class RuleBasedGenerator:
    @staticmethod
    async def sleep_recommendations(trends, anomalies) -> list[HealthRecommendation]:
        # If sleep_quality declined > 15% for 3+ days → "Sleep quality trending down"
        # If sleep_hours consistently < 6 → "Consider earlier bedtime, aim for 7-8h"
        # If sleep_onset after midnight → "Screen time before bed may delay sleep onset"
        # If HRV low + sleep poor → "Poor recovery — prioritize rest tonight"

    @staticmethod
    async def activity_recommendations(trends, anomalies) -> list[HealthRecommendation]:
        # If steps < 5000 for 3+ days → "Activity level low, aim for 30min walk"
        # If exercise_minutes > 0 → positive reinforcement
        # If exercise irregular → "Consistency matters more than intensity"

    @staticmethod
    async def stress_recommendations(trends, anomalies) -> list[HealthRecommendation]:
        # If HRV baseline dropped > 20% → "Signs of accumulated stress"
        # If resting_heart_rate elevated + sleep poor → "Recovery needed"
        # If stress_level > 70 for sustained period → "Consider 5min breathing break"

    @staticmethod
    async def routine_recommendations(trends, anomalies) -> list[HealthRecommendation]:
        # If fatigue peaks at 2-4pm → "Schedule low-focus tasks for afternoon dip"
        # If focus peaks morning → "Protect morning hours for deep work"
        # Based on circadian pattern analysis from TrendAnalyzer
```

**LLM-based generator (optional, requires LLM access):**
```python
class LLMHealthAdvisor:
    async def analyze(self, metrics: dict, trends: dict,
                      anomalies: list, history: str) -> list[HealthRecommendation]:
        prompt = f"""
        You are VECTOR's health advisor. Analyze the following health data and
        provide 2-3 specific, actionable health recommendations.

        Current metrics:
        {json.dumps(metrics, indent=2)}

        Trends (7-day change):
        {json.dumps({k: {"delta_pct": v.delta_7d_pct, "trend": v.trend} for k, v in trends.items()}, indent=2)}

        Recent anomalies:
        {json.dumps([a.__dict__ for a in anomalies[-5:]], indent=2)}

        Historical context (last 3 days):
        {history}

        For each recommendation, provide:
        1. Category (sleep/activity/stress/medical/routine)
        2. Priority (1-5, 1=critical)
        3. Specific actionable advice
        4. Evidence from the data
        5. Expected benefit if followed

        Format as JSON array.
        """

        response = await llm_client.complete(prompt)
        return self._parse_recommendations(response)
```

**HealthAdvisor orchestrator:**
```python
class HealthAdvisor:
    def __init__(self, use_llm: bool = False):
        self.rule_gen = RuleBasedGenerator()
        self.llm_gen = LLMHealthAdvisor() if use_llm else None

    async def generate_recommendations(self) -> list[HealthRecommendation]:
        trends = await trend_analyzer.compute_all_trends()
        anomalies = await trend_analyzer.detect_anomalies()
        history = await self._summarize_history(hours=72)

        recs = []
        recs.extend(await self.rule_gen.sleep_recommendations(trends, anomalies))
        recs.extend(await self.rule_gen.activity_recommendations(trends, anomalies))
        recs.extend(await self.rule_gen.stress_recommendations(trends, anomalies))
        recs.extend(await self.rule_gen.routine_recommendations(trends, anomalies))

        if self.llm_gen:
            llm_recs = await self.llm_gen.analyze(trends, anomalies, history)
            recs.extend(llm_recs)

        return self._prioritize_and_dedup(recs)
```

**Configuration:**
```python
HEALTH_ADVISOR_ENABLED: bool = True
HEALTH_ADVISOR_CYCLE_MINUTES: int = 60
HEALTH_ADVISOR_USE_LLM: bool = False  # opt-in, requires LLM access
HEALTH_ADVISOR_MAX_RECOMMENDATIONS: int = 3
HEALTH_ADVISOR_PUSHOVER_PRIORITY_THRESHOLD: int = 2
HEALTH_ADVISOR_STORE_RECOMMENDATIONS: bool = True
```

### 4.5 EmergencyDetector

**Purpose:** Continuously monitor vitals and phone sensors for signs of medical emergencies.

**File:** `districts/health/emergency_detector.py`

**Detection rules:**
```python
EMERGENCY_RULES = {
    "sustained_high_hr": {
        "description": "Heart rate sustained above threshold for extended period",
        "metric": "heart_rate",
        "condition": "> 120",  # bpm
        "duration_minutes": 30,
        "severity": 8,
    },
    "sustained_low_hr": {
        "description": "Extremely low heart rate",
        "metric": "heart_rate",
        "condition": "< 40",  # bpm
        "duration_minutes": 10,
        "severity": 9,
    },
    "high_stress_sustained": {
        "description": "Stress level critically high for extended period",
        "metric": "stress_level",
        "condition": "> 85",
        "duration_minutes": 60,
        "severity": 7,
    },
    "low_spo2": {
        "description": "Blood oxygen saturation below critical threshold",
        "metric": "spo2",
        "condition": "< 90",  # percent
        "duration_minutes": 5,
        "severity": 10,
    },
    "no_movement_long": {
        "description": "No movement detected for extended period (phone sensors)",
        "metric": "movement_detected",
        "condition": "== False",
        "duration_minutes": 720,  # 12 hours
        "severity": 9,
    },
    "sleep_apnea_pattern": {
        "description": "Oxygen desaturation pattern during sleep",
        "metric": "spo2",
        "condition": "drop > 4%",  # during sleep hours
        "duration_minutes": 30,
        "severity": 7,
    },
    "hrv_crash": {
        "description": "HRV dropped more than 30% from baseline",
        "metric": "hrv",
        "condition": "delta < -30%",
        "duration_minutes": 0,  # immediate
        "severity": 6,
    },
}
```

**Emergency escalation protocol:**
```python
class EmergencyDetector:
    async def check_all(self) -> list[EmergencyEvent]:
        # Run all rule checks
        # For duration-based rules: check if condition has been met consecutively

    async def handle_emergency(self, event: EmergencyEvent):
        # Severity 10: Pushover critical alert + phone node SMS (if available)
        # Severity 8-9: Pushover high-priority alert + dashboard flash
        # Severity 6-7: Pushover normal alert + log
        # Severity < 6: Log only, no notification
        # Escalation: if no acknowledgment in 10 min, escalate to emergency contact
        #             (if configured — requires specs-07 emergency response integration)
```

**Emergency event schema:**
```python
@dataclass
class EmergencyEvent:
    id: str
    rule_id: str
    detected_at: datetime
    metric_key: str
    current_value: float | bool
    threshold: str
    severity: int
    acknowledged: bool
    acknowledged_at: datetime | None
    escalated: bool
    escalation_contact: str | None
    resolved: bool
    resolved_at: datetime | None
```

**Configuration:**
```python
EMERGENCY_DETECTOR_ENABLED: bool = True
EMERGENCY_DETECTOR_CYCLE_SECONDS: int = 60  # check every minute
EMERGENCY_DETECTOR_PUSHOVER_PRIORITY: int = 2  # emergency priority for Pushover
EMERGENCY_DETECTOR_ESCALATION_MINUTES: int = 10
EMERGENCY_DETECTOR_ESCALATION_CONTACT: str = ""  # Pushover user key of emergency contact
EMERGENCY_DETECTOR_EMERGENCY_CONTACT_ENABLED: bool = False
```

### 4.6 MetricsStore

**Purpose:** SQLite-backed persistent store for all health metrics, trends, anomalies, recommendations, and emergency events.

**File:** `districts/health/metrics_store.py`

**SQLite schema:**
```sql
-- Raw wearable metrics
CREATE TABLE wearable_metrics (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,            -- "apple_health", "google_fit", etc.
    heart_rate REAL,
    hrv REAL,
    resting_heart_rate REAL,
    sleep_hours REAL,
    sleep_quality REAL,
    sleep_stages TEXT,               -- JSON
    steps INTEGER,
    active_calories REAL,
    exercise_minutes REAL,
    spo2 REAL,
    stress_level REAL,
    skin_temperature REAL,
    respiratory_rate REAL,
    accelerometer TEXT,              -- JSON
    movement_detected INTEGER,       -- boolean
    metadata TEXT                    -- JSON
);
CREATE INDEX idx_wearable_timestamp ON wearable_metrics(timestamp);
CREATE INDEX idx_wearable_source ON wearable_metrics(source, timestamp);

-- Trends
CREATE TABLE metric_trends (
    id TEXT PRIMARY KEY,
    metric_key TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    current_value REAL,
    baseline_7d_mean REAL,
    baseline_7d_std REAL,
    baseline_30d_mean REAL,
    baseline_30d_std REAL,
    delta_7d_pct REAL,
    delta_30d_pct REAL,
    trend TEXT,
    stability REAL
);
CREATE INDEX idx_trends_metric ON metric_trends(metric_key, computed_at);

-- Anomalies
CREATE TABLE health_anomalies (
    id TEXT PRIMARY KEY,
    metric_key TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    value REAL,
    baseline REAL,
    deviation_pct REAL,
    direction TEXT,
    severity INTEGER,
    resolved INTEGER DEFAULT 0,
    resolved_at TEXT
);
CREATE INDEX idx_anomalies_metric ON health_anomalies(metric_key);

-- Recommendations
CREATE TABLE health_recommendations (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    priority INTEGER,
    generated_at TEXT NOT NULL,
    actionable INTEGER DEFAULT 1,
    acted_upon INTEGER DEFAULT 0,
    acted_at TEXT,
    user_feedback TEXT
);

-- Emergency events
CREATE TABLE emergency_events (
    id TEXT PRIMARY KEY,
    rule_id TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    metric_key TEXT,
    current_value REAL,
    threshold TEXT,
    severity INTEGER,
    acknowledged INTEGER DEFAULT 0,
    acknowledged_at TEXT,
    escalated INTEGER DEFAULT 0,
    resolved INTEGER DEFAULT 0,
    resolved_at TEXT,
    pushover_sent INTEGER DEFAULT 0
);

-- Daily summaries
CREATE TABLE daily_health_summaries (
    date TEXT PRIMARY KEY,
    avg_heart_rate REAL,
    avg_hrv REAL,
    total_sleep_hours REAL,
    sleep_quality REAL,
    total_steps INTEGER,
    total_exercise_minutes REAL,
    avg_stress_level REAL,
    avg_spo2 REAL,
    max_temperature REAL,
    fatigue_avg REAL,
    energy_avg REAL,
    summary_text TEXT,               -- LLM-generated daily summary
    generated_at TEXT
);
```

**Configuration:**
```python
HEALTH_DB_PATH: str = "data/health/health_metrics.db"
HEALTH_DB_RETENTION_DAYS: int = 90
HEALTH_DAILY_SUMMARY_HOUR: int = 22  # generate summary at 10pm
```

---

## 5. Agent Dispatch Plan

### Agent A: WearableConnector + VitalsDashboard

**Focus:** Build wearable API integration and real-time vitals display.

**Tasks:**
1. Install dependencies: `pyhealth` (Apple Health), Google Fit API client
2. Implement `districts/health/metrics_store.py` — full SQLite schema
3. Implement `districts/health/wearable_connector.py` — all connector classes
4. Implement Apple Health connector via pyhealth (working integration)
5. Implement Google Fit connector via REST API (working integration)
6. Implement Oura connector via API v2 (working integration)
7. Implement phone sensor connector via ADB bridge
8. Implement stubs for Garmin + Whoop (documented, graceful failure)
9. Implement FastAPI backend for VitalsDashboard
10. Implement React frontend with live vitals, sleep, activity cards
11. Wire wearable poll cycle into autonomous loop
12. Register config
13. Write unit tests for metrics store and connectors

**Estimated effort:** 5-6 hours

### Agent B: TrendAnalyzer + HealthAdvisor + EmergencyDetector

**Focus:** Build analysis, recommendations, and emergency detection.

**Tasks:**
1. Implement `districts/health/trend_analyzer.py` — baselines, anomalies, trends, correlations, circadian
2. Implement `districts/health/health_advisor.py` — rule-based generators + optional LLM
3. Implement `districts/health/emergency_detector.py` — all detection rules + escalation
4. Wire analysis cycle into autonomous loop (60-min interval)
5. Wire emergency detection cycle (60-second interval)
6. Wire daily health summary generation (10pm)
7. Implement Pushover integration for critical anomalies and emergencies
8. Register config
9. Write unit tests for all three components

**Estimated effort:** 4-5 hours

---

## 6. Implementation Steps

### Phase 1: Schema & Infrastructure

- [ ] **1.1** Create shared health data models in `core/models/health_models.py` (WearableMetrics, MetricTrend, MetricAnomaly, HealthRecommendation, EmergencyEvent, DailySummary)
- [ ] **1.2** Register all new config values in `core/config.py`
- [ ] **1.3** Add dependencies to requirements.txt: `pyhealth`, `google-auth-oauthlib`, `google-auth-httplib2`, `google-api-python-client`
- [ ] **1.4** Create `data/health/` directory structure

### Phase 2: Metrics Store (Agent A)

- [ ] **2.1** Implement `metrics_store.py` with full SQLite schema
- [ ] **2.2** Implement CRUD: insert_wearable, query_history, insert_trend, insert_anomaly, insert_recommendation, insert_emergency, insert_daily_summary
- [ ] **2.3** Implement retention/pruning: delete records older than HEALTH_DB_RETENTION_DAYS
- [ ] **2.4** Implement daily summary generation (aggregate query + summary text)
- [ ] **2.5** Unit tests

### Phase 3: Wearable Connectors (Agent A)

- [ ] **3.1** Implement BaseConnector abstract class with auth, fetch, health_check
- [ ] **3.2** Implement AppleHealthConnector (pyhealth integration)
- [ ] **3.3** Implement GoogleFitConnector (OAuth2 + REST API)
- [ ] **3.4** Implement OuraConnector (Personal Access Token + v2 API)
- [ ] **3.5** Implement PhoneSensorConnector (ADB bridge accelerometer data)
- [ ] **3.6** Implement GarminConnector (stub — logs and returns None)
- [ ] **3.7** Implement WhoopConnector (stub — logs and returns None)
- [ ] **3.8** Implement WearableConnector orchestrator with parallel polling
- [ ] **3.9** Wire poll cycle into autonomous loop (15-min interval)
- [ ] **3.10** Write to episodic memory on each poll
- [ ] **3.11** Unit tests for each connector

### Phase 4: Trend & Anomaly Analysis (Agent B)

- [ ] **4.1** Implement baseline computation (7-day and 30-day rolling)
- [ ] **4.2** Implement anomaly detection (deviation > threshold)
- [ ] **4.3** Implement trend classification (improving/declining/stable/volatile)
- [ ] **4.4** Implement weekly comparison
- [ ] **4.5** Implement correlation detection
- [ ] **4.6** Implement circadian pattern detection
- [ ] **4.7** Wire analysis cycle into autonomous loop (60-min interval)
- [ ] **4.8** Unit tests

### Phase 5: Health Advisor (Agent B)

- [ ] **5.1** Implement sleep recommendation generator
- [ ] **5.2** Implement activity recommendation generator
- [ ] **5.3** Implement stress recommendation generator
- [ ] **5.4** Implement routine optimization recommendation generator
- [ ] **5.5** Implement LLM-based advisor (optional, gated by config)
- [ ] **5.6** Implement priority scoring and dedup
- [ ] **5.7** Wire recommendation cycle (60-min interval)
- [ ] **5.8** Wire Pushover for critical recommendations (priority <= 2)

### Phase 6: Emergency Detection (Agent B)

- [ ] **6.1** Implement all emergency detection rules (sustained high/low HR, high stress, low SpO2, no movement, HRV crash, sleep apnea pattern)
- [ ] **6.2** Implement duration-based condition tracking (must be sustained for N minutes)
- [ ] **6.3** Implement escalation protocol (Pushover → wait → escalate to emergency contact)
- [ ] **6.4** Wire emergency detection cycle (60-second interval)
- [ ] **6.5** Tests: simulate emergency event → verify Pushover sent

### Phase 7: Vitals Dashboard (Agent A)

- [ ] **7.1** Implement FastAPI backend with REST endpoints
- [ ] **7.2** Implement WebSocket endpoint for live vitals push
- [ ] **7.3** Implement React frontend: live vitals card
- [ ] **7.4** Implement React: sleep card with stage bar chart
- [ ] **7.5** Implement React: activity card with daily goals
- [ ] **7.6** Implement React: trends panel with weekly/monthly lines
- [ ] **7.7** Implement React: anomalies feed and recommendations
- [ ] **7.8** Implement React: emergency status indicator
- [ ] **7.9** Wire dashboard startup into autonomous loop (config-gated)

### Phase 8: Integration & Hardening

- [ ] **8.1** Integration test: WearableConnector polls → metrics stored → dashboard displays
- [ ] **8.2** Integration test: inject metric with 20% deviation → anomaly detected → trend registered
- [ ] **8.3** Integration test: sustained high HR for 30 min → EmergencyEvent → Pushover
- [ ] **8.4** Integration test: health recommendation generated → stored → queried
- [ ] **8.5** Edge case: all wearable sources unavailable → logs warning, runs in camera-only mode
- [ ] **8.6** Edge case: WearableConnector auth token expired → reauth flow → fall back to cached data
- [ ] **8.7** Edge case: ADB bridge disconnected → PhoneSensorConnector returns None gracefully
- [ ] **8.8** Edge case: no data for 7-day baseline → use 3-day or 24h fallback
- [ ] **8.9** Edge case: LLM advisor not available (no API key) → rule-based only, no crash
- [ ] **8.10** Performance: 15-min poll for 4 sources completes under 30s total

---

## 7. Files to Create/Modify

### New Files

| File | Purpose | Agent |
|------|---------|-------|
| `districts/health/wearable_connector.py` | Multi-source wearable API polling | A |
| `districts/health/trend_analyzer.py` | Baseline, trend, anomaly, correlation analysis | B |
| `districts/health/health_advisor.py` | Rule-based + LLM health recommendations | B |
| `districts/health/emergency_detector.py` | Critical vitals monitoring + escalation | B |
| `districts/health/metrics_store.py` | SQLite persistence for all health data | A |
| `core/models/health_models.py` | Shared Pydantic/dataclass schemas | Shared |
| `dashboard/health_dashboard/api.py` | FastAPI backend | A |
| `dashboard/health_dashboard/app.py` | React frontend | A |
| `tests/districts/health/test_wearable_connector.py` | Tests | A |
| `tests/districts/health/test_metrics_store.py` | Tests | A |
| `tests/districts/health/test_trend_analyzer.py` | Tests | B |
| `tests/districts/health/test_health_advisor.py` | Tests | B |
| `tests/districts/health/test_emergency_detector.py` | Tests | B |

### Modified Files

| File | Change | Agent |
|------|--------|-------|
| `core/config.py` | Add all WEARABLE_*, HEALTH_DASHBOARD_*, TREND_*, HEALTH_ADVISOR_*, EMERGENCY_DETECTOR_*, HEALTH_DB_* settings | Shared |
| `core/loop/autonomous_loop.py` | Add wearable_poll_cycle, health_analysis_cycle, emergency_detection_cycle coroutines | A/B |
| `core/loop/context_engine.py` | Add detailed health metrics to health domain | A |
| `core/sensing/health_monitor.py` | Integrate wearable data into HealthMonitor snapshot | A |
| `phone_node/adb_bridge.py` | Ensure accelerometer data access for phone sensor connector | A |
| `requirements.txt` | Add pyhealth, google-auth-oauthlib, google-auth-httplib2, google-api-python-client | A/B |

---

## 8. Success Criteria

| Criterion | Measurement | Threshold |
|-----------|------------|-----------|
| Wearable data collection | Poll interval | Every 15 minutes |
| Active wearable connectors | Number of working sources | >= 3 (apple, google, phone) + stub(s) |
| Heart rate on dashboard | Real-time display | Updates within 1 min of poll |
| Sleep data displayed | Last night's sleep | Hours + quality + stages shown |
| Trend baseline accuracy | 7-day/30-day rolling mean | Computed correctly for all metrics |
| Anomaly detection (>15% deviation) | True positive rate | >= 90% |
| Health recommendations generated | Per day | >= 2 recommendations |
| Recommendation validity | User-rated helpful | >= 70% |
| Emergency detection (sustained high HR) | Detection time | < 60 seconds |
| Emergency Pushover | Critical alert sent | Within 10 seconds of detection |
| Daily health summary | Generated daily at 10pm | Text + numeric summary |
| Dashboard WebSocket | Live push latency | < 2 seconds |
| Metrics store | All data persisted | 100% |
| No-movement detection (>12h) | Emergency event triggered | Correctly after 12h inactivity |

### Known Limitations (Future Specs)

- **Real-time ECG/EEG:** Requires dedicated hardware. Not yet supported.
- **Blood pressure:** Not available via consumer wearable APIs. Manual entry option in future.
- **Blood glucose:** Requires CGM device. Future: Dexcom API integration.
- **Medical-grade alerts:** This system is for awareness, not diagnosis. Emergency detection is supplementary, not a replacement for medical devices.
- **specs-07 integration:** Emergency escalation currently uses Pushover. Future: SMS, phone call, or emergency contact notification via specs-07 Emergency Response.
- **specs-08 integration:** Vitals dashboard may be rendered in AR via specs-08 AR Dashboard.

---

## 9. Dependencies

### Upstream Dependencies
- `core/loop/autonomous_loop.py` — health cycles run as coroutines
- `core/loop/context_engine.py` — health domain exists, needs enrichment
- `core/config.py` (Pydantic V2) — exists, needs extension
- `core/sensing/health_monitor.py` — existing camera-based monitoring, will be enriched
- `phone_node/adb_bridge.py` — phone sensor data access
- `phone_node/ambient_server.py` — phone heartbeat data
- `districts/health/fatigue_monitor.py` — existing camera EAR metrics
- `districts/health/sleep_tracker.py` — existing sleep logging
- `districts/health/exercise_logger.py` — existing exercise logging

### External Dependencies
- `pyhealth>=1.0.0` (Apple HealthKit data via Python)
- `google-auth-oauthlib>=1.0.0` (Google Fit OAuth)
- `google-auth-httplib2>=0.1.0` (Google Fit transport)
- `google-api-python-client>=2.80.0` (Google Fit API client)
- `requests>=2.31.0` (API calls — likely already installed)
- `react>=18` (dashboard frontend, via npm)
- Node.js 18+ (for React build)

### Runtime Dependencies
- Apple Health data: macOS with Health app data, or iPhone with Health export
- Google Fit: Google account + OAuth credentials (requires Google Cloud project setup)
- Oura: Oura API personal access token
- ADB bridge: Android phone connected via USB with ADB enabled
- Write access to `data/health/` directory
- Port 8855 available (or configured alternate)
- Pushover API credentials (already configured in .env)

### Downstream Dependents
- specs-05 (Predictive Analytics) — consumes health metrics for health forecasting (TimeSeriesForecaster)
- specs-07 (Emergency Response) — emergency detection escalation routed through specs-07 playbooks
- specs-08 (AR Dashboard) — may visualize health vitals in AR HUD view
- specs-12 (Adaptive Learning) — may adapt based on fatigue/productivity health predictions
