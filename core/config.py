import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from typing import Optional
from pydantic import BaseModel, SecretStr, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_DIR = Path(__file__).parent.parent


# ── Sub-models (each validated at startup) ────────────────────────────────────

class ModelsConfig(BaseModel):
    ambient: str = "vector-ambient"
    focus: str = "vector-focus"
    multilingual: str = "vector-multilingual"
    reasoning: str = "vector-reasoning"
    coder: str = "vector-coder"
    deep: str = "vector-deep"
    chairman: str = "vector-chairman"
    embed: str = "nomic-embed-text"
    r1: str = "vector-r1"               # deepseek-r1:14b — chain-of-thought council member
    dev: str = "vector-dev"             # devstral:24b — code review + refactor specialist
    fast: str = "vector-fast"           # mistral-small3.1 — low-latency general fallback
    cloud_coder: str = "vector-dev"     # was phi4:latest — now devstral-based VECTOR model
    cloud_orchestrator: str = "vector-r1"  # was deepseek-r1:14b raw — now VECTOR custom


class ModelRouterConfig(BaseModel):
    conversation: str = "focus"
    multilingual: str = "multilingual"
    coding: str = "coder"
    code_review: str = "dev"
    council: str = "reasoning"
    chain_of_thought: str = "r1"
    fast_fallback: str = "fast"
    deep_analysis: str = "deep"
    private: str = "chairman"
    embedding: str = "embed"
    ambient_classify: str = "ambient"
    saas_build: str = "dev"
    orchestration: str = "r1"


class LoopConfig(BaseModel):
    observe_interval_sec: float = Field(0.5, ge=0.1, le=60.0)
    db_sync_hours: int = Field(48, ge=1, le=720)
    reflect_hour: int = Field(2, ge=0, le=23)
    reflect_minute: int = Field(0, ge=0, le=59)


class PermissionConfig(BaseModel):
    green: list[str] = Field(default_factory=lambda: [
        "read_calendar", "play_music", "set_timer", "search_web",
        "take_screenshot", "check_weather", "check_attendance",
        "progress_goal", "kickstart_goal",
        # concrete action types from think→act pipeline
        "git_status", "check_git", "recent_commits", "git_log",
        "daily_digest", "search_arxiv", "get_hn", "hackernews",
        "check_fatigue", "consolidate", "daily_review", "reflect",
        "deadline_check", "progress",
        # VectorCode read-only actions
        "code_review_vc", "code_status", "read_code", "analyze_code",
        # VECTOR UI events — purely local dashboard side effects, no real-world impact
        "respond", "open_panel",
        "widget_open", "widget_close", "widget_show_location",
        "music_play", "music_pause", "music_next", "music_prev",
    ])
    yellow: list[str] = Field(default_factory=lambda: [
        "send_message_routine", "create_calendar_event", "commit_code",
        "download_file", "set_reminder", "write_note_personal",
        "monthly_report", "finance_report", "journal", "weekly_journal",
        "create_project", "add_deadline", "log_exercise",
        # VectorCode write/execute actions
        "code_task", "code_generate", "code_fix", "code_debug", "run_tests",
    ])
    red: list[str] = Field(default_factory=lambda: [
        "send_email", "delete_files", "execute_code",
        "financial_transaction", "push_github", "deploy_production",
        "overwrite_note_personal",
    ])


class CouncilConfig(BaseModel):
    max_per_week: int = Field(10, ge=1, le=100)
    hp_gate: int = Field(700, ge=0, le=1000)
    cost_inr: float = Field(1.60, ge=0)


class CostConfig(BaseModel):
    monthly_budget_inr: int = Field(500, ge=0)
    alert_inr: int = Field(400, ge=0)

    @model_validator(mode="after")
    def alert_below_budget(self):
        if self.alert_inr > self.monthly_budget_inr:
            raise ValueError(
                f"alert_inr ({self.alert_inr}) must be ≤ monthly_budget_inr ({self.monthly_budget_inr})"
            )
        return self


class PersonalityConfig(BaseModel):
    enabled: bool = True
    character_card_path: str = ""
    character_version: str = "v1.0"
    sentiment_method: str = "keyword"  # keyword | embedding | llm
    consistency_threshold: float = Field(0.70, ge=0.0, le=1.0)
    consistency_weights: dict[str, float] = Field(default_factory=lambda: {
        "trait": 0.40, "rules": 0.35, "quirks": 0.15, "speech": 0.10,
    })
    learning_enabled: bool = True
    personality_version: str = "1.0"


class CircuitBreakerConfig(BaseModel):
    failure_threshold: int = Field(5, ge=1, le=100)
    recovery_timeout_sec: float = Field(30.0, ge=1.0, le=300.0)
    half_open_max_retries: int = Field(3, ge=1, le=10)
    success_threshold: int = Field(2, ge=1, le=10)


class BulkheadConfig(BaseModel):
    max_concurrent: int = Field(4, ge=1, le=32)
    max_queue: int = Field(10, ge=1, le=100)
    queue_timeout_sec: float = Field(30.0, ge=1.0, le=300.0)


class FailoverConfig(BaseModel):
    secondary_url: str = "http://127.0.0.1:8001"
    heartbeat_interval_sec: float = Field(5.0, ge=1.0, le=60.0)
    max_missed_heartbeats: int = Field(3, ge=1, le=10)


class GracefulDegradationConfig(BaseModel):
    cooldown_sec: float = Field(60.0, ge=10.0, le=600.0)
    enabled: bool = True


class ChaosConfig(BaseModel):
    enabled: bool = False
    schedule_interval_h: int = Field(24, ge=1, le=168)


class ResilienceConfig(BaseModel):
    enabled: bool = True
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)
    bulkhead: BulkheadConfig = Field(default_factory=BulkheadConfig)
    failover: FailoverConfig = Field(default_factory=FailoverConfig)
    degradation: GracefulDegradationConfig = Field(default_factory=GracefulDegradationConfig)
    chaos: ChaosConfig = Field(default_factory=ChaosConfig)


class VoiceConfig(BaseModel):
    whisper_model: str = "large-v3"
    stt_engine: str = "whisper"
    device: str = "cuda"
    compute_type: str = "float16"
    kokoro_model_dir: str = str(Path(__file__).parent.parent / "models" / "kokoro")
    kokoro_speed: float = Field(0.85, ge=0.1, le=3.0)
    wake_threshold: float = Field(0.5, ge=0.0, le=1.0)
    record_duration_sec: float = Field(5.0, ge=1.0, le=120.0)
    sample_rate: int = Field(16000, ge=8000, le=96000)
    wake_phrase: str = "hey_vector"
    vad_threshold: float = Field(0.02, ge=0.001, le=1.0)
    vad_frame_ms: int = Field(30, ge=10, le=100)
    silence_timeout_sec: float = Field(2.0, ge=0.1, le=30.0)
    conversation_timeout_sec: int = Field(30, ge=5, le=300)
    max_concurrent_sessions: int = Field(3, ge=1, le=10)
    streaming_enabled: bool = True


class SecurityCfg(BaseModel):
    suspicious_ports: list[int] = Field(default_factory=lambda: [
        4444, 6666, 1337, 31337, 9001, 9050,
    ])
    suspicious_process_names: list[str] = Field(default_factory=lambda: [
        "cryptominer", "keylogger", "miner", "rat", "netcat",
        "mimikatz", "cobaltstrike", "metasploit", "ncrack",
        "xmrig", "monero", "cpuminer",
    ])
    entropy_threshold: float = Field(7.5, ge=0.0, le=8.0)


class SecurityConfig(BaseModel):
    siem_enabled: bool = False
    network_monitor_interval_sec: int = 30
    log_aggregator_enabled: bool = True
    detection_rules_enabled: bool = True
    alert_manager_enabled: bool = True
    incident_response_enabled: bool = True
    pushover_enabled: bool = True
    pushover_user_key: str = ""
    pushover_api_token: str = ""
    blocked_domains: list[str] = ["shell_command", "command_line", "python_script"]


class ControlConfig(BaseModel):
    adb_path: str = "adb"
    phone_device_id: Optional[str] = None


class SensingConfig(BaseModel):
    lgbm_model_path: str = "./models/malware_lgbm.txt"
    known_faces_dir: str = "./data/known_faces"
    camera_index: int = Field(0, ge=0)
    screen_ocr_enabled: bool = True
    fatigue_check_interval_sec: int = Field(30, ge=5, le=3600)


class CodingConfig(BaseModel):
    repo_path: str = str(_BASE_DIR)


class VectorCodeConfig(BaseModel):
    enabled: bool = True
    python_path: str = str(_BASE_DIR / "vectorcode" / "python" / "vectorcode")
    mcp_port: int = Field(9001, ge=1024, le=65535)
    base_url: str = "http://127.0.0.1:9001"
    timeout_sec: float = Field(300.0, ge=10.0, le=3600.0)


class VectorCodeCommsConfig(BaseModel):
    local_url: str = "http://127.0.0.1:8080"
    port: int = Field(8080, ge=1024, le=65535)
    timeout_sec: float = Field(10.0, ge=1.0, le=60.0)
    repo_path: str = str(Path(__file__).parent.parent / "vectorcode")


class TursoConfig(BaseModel):
    url: str = ""
    token: str = ""


class KarpathyConfig(BaseModel):
    runs_dir: str = "./data/training_runs"
    data_dir: str = "./data/datasets"
    daily_minutes: int = Field(30, ge=5, le=120)


class AirLLMConfig(BaseModel):
    models_dir: str = "./models/airllm"
    cache_dir: str = "./data/airllm_cache"
    max_gpu_memory_gb: float = Field(11.0, ge=1.0, le=24.0)


class ResearchLabConfig(BaseModel):
    enabled: bool = False
    sandbox_backend: str = "subprocess"
    max_concurrent_experiments: int = 2
    schedule_interval_hours: int = 6
    docker_image: str = "vector-experiment-runner:latest"
    sandbox_enabled: bool = False


class EventBusConfig(BaseModel):
    enabled: bool = True
    max_queue_size: int = 1000
    worker_pool_size: int = 4


class EmergencyConfig(BaseModel):
    enabled: bool = False
    detector_interval_sec: int = 5
    pushover_enabled: bool = True
    quiet_hours_start: int = 23
    quiet_hours_end: int = 7
    rate_limit_pushover_monthly: int = 10000


class HealthConfig(BaseModel):
    enabled: bool = False
    wearable_poll_interval_minutes: int = 15
    health_analysis_interval_minutes: int = 60
    emergency_detection_interval_seconds: int = 60
    pushover_enabled: bool = True
    retention_days: int = 90


class CodeIntelConfig(BaseModel):
    project_id: str = "vector-codebase-main"
    qdrant_url: str = "http://127.0.0.1:6333"
    embedding_provider: str = "ollama"
    ollama_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "nomic-embed-text"
    chunk_size: int = Field(100, ge=10, le=500)
    chunk_overlap: int = Field(10, ge=0, le=50)
    max_file_size_mb: float = Field(5.0, ge=0.1, le=50.0)
    dist_path: str = "vectorcode/code_intel/dist/index.js"


class TrainingConfig(BaseModel):
    adapters_dir: str = "models/adapters"
    models_dir: str = "models"
    unsloth_enabled: bool = False
    eval_results_dir: str = "data/evaluations"
    self_improvement_enabled: bool = True
    self_improvement_interval_hours: int = 168
    distillation_enabled: bool = True
    training_enabled: bool = False


class PredictiveAnalyticsConfig(BaseModel):
    enabled: bool = False
    forecast_interval_minutes: int = 15
    simulation_interval_minutes: int = 60
    retention_days: int = 90
    pushover_enabled: bool = True
    max_metrics: int = 14


class HomeAssistantConfig(BaseModel):
    enabled: bool = False
    host: str = "homeassistant.local"
    port: int = 8123
    token: str = ""
    use_ssl: bool = False
    rate_limit_per_sec: int = 10


class AdsConfig(BaseModel):
    scripts_path: str = "districts/marketing/ads/scripts"
    references_path: str = "districts/marketing/ads/references"
    templates_path: str = "districts/marketing/ads/templates"
    image_provider_order: list[str] = Field(default_factory=lambda: ["gemini", "openai", "stability", "replicate"])
    pdf_output_dir: str = "output/ads_reports"
    screenshot_dir: str = "output/ads_screenshots"
    max_concurrent_audits: int = Field(6, ge=1, le=10)


# ── Main settings (reads from .env) ───────────────────────────────────────────

class VectorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BASE_DIR / ".env",
        extra="ignore",
        case_sensitive=False,
    )

    # Core — mapped from env var names
    VECTOR_ENV: str = "development"
    VECTOR_DEBUG: bool = False
    VECTOR_VAULT_PATH: str = "C:/Users/Arghyadeep/V.E.C.T.O.R Brain"
    OLLAMA_HOST: str = "http://127.0.0.1:11434"

    # API keys — SecretStr prevents values leaking into logs or repr()
    ANTHROPIC_KEY: SecretStr = SecretStr("")
    GEMINI_KEY: SecretStr = SecretStr("")
    GITHUB_TOKEN: SecretStr = SecretStr("")
    GITHUB_USERNAME: str = "ArghyadeepDeb"
    PUSHOVER_TOKEN: SecretStr = SecretStr("")
    PUSHOVER_USER: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_KEY: SecretStr = SecretStr("")
    VIRUSTOTAL_KEY: SecretStr = SecretStr("")
    NEWSAPI_KEY: SecretStr = SecretStr("")
    STRIPE_KEY: SecretStr = SecretStr("")
    KIIT_USERNAME: str = ""
    KIIT_PASSWORD: SecretStr = SecretStr("")
    GOOGLE_CREDENTIALS_PATH: str = ""
    YOUTUBE_CHANNEL_ID: str = ""
    INSTAGRAM_ACCESS_TOKEN: SecretStr = SecretStr("")
    INSTAGRAM_ACCOUNT_ID: str = ""
    ELEVENLABS_KEY: SecretStr = SecretStr("")
    ELEVENLABS_VOICE_ID: str = "pNInz6obpgDQGcFmaJgB"
    CONTENT_NICHE: str = "AI"
    VIDEO_UPLOAD_DELAY_MINUTES: int = 30
    MUAPI_API_KEY: SecretStr = SecretStr("")
    WAN2GP_URL: str = ""
    PAGESPEED_API_KEY: SecretStr = SecretStr("")
    HASS_URL: str = ""
    HASS_TOKEN: SecretStr = SecretStr("")

    # Network
    VECTOR_OFP_SECRET: SecretStr = SecretStr("")
    VECTOR_PEERS: str = ""
    VECTOR_CLOUD_API_URL: str = ""
    VECTOR_OAUTH_REDIRECT_BASE: str = "http://localhost:7788"

    # Telemetry
    SENTRY_DSN: str = ""
    VECTOR_BUILD_SHA: str = "dev"

    # Research engine
    LDR_DATA_DIR: str = ""

    # CORS — overridable via env var as a JSON array
    ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ])

    # Turso — overridable via env vars
    TURSO_URL: str = ""
    TURSO_TOKEN: SecretStr = SecretStr("")

    # Structured sub-configs — validated by their own models
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    model_router: ModelRouterConfig = Field(default_factory=ModelRouterConfig)
    loop: LoopConfig = Field(default_factory=LoopConfig)
    permission: PermissionConfig = Field(default_factory=PermissionConfig)
    council: CouncilConfig = Field(default_factory=CouncilConfig)
    cost: CostConfig = Field(default_factory=CostConfig)
    personality: PersonalityConfig = Field(default_factory=PersonalityConfig)
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    security: SecurityCfg = Field(default_factory=SecurityCfg)
    siem: SecurityConfig = Field(default_factory=SecurityConfig)
    control: ControlConfig = Field(default_factory=ControlConfig)
    sensing: SensingConfig = Field(default_factory=SensingConfig)
    coding: CodingConfig = Field(default_factory=CodingConfig)
    comms: VectorCodeCommsConfig = Field(default_factory=VectorCodeCommsConfig)
    turso: TursoConfig = Field(default_factory=TursoConfig)
    karpathy: KarpathyConfig = Field(default_factory=KarpathyConfig)
    airllm: AirLLMConfig = Field(default_factory=AirLLMConfig)
    vectorcode: VectorCodeConfig = Field(default_factory=VectorCodeConfig)
    predictive_analytics: PredictiveAnalyticsConfig = Field(default_factory=PredictiveAnalyticsConfig)
    ads: AdsConfig = Field(default_factory=AdsConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    emergency: EmergencyConfig = Field(default_factory=EmergencyConfig)
    code_intel: CodeIntelConfig = Field(default_factory=CodeIntelConfig)
    event_bus: EventBusConfig = Field(default_factory=EventBusConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)
    research_lab: ResearchLabConfig = Field(default_factory=ResearchLabConfig)
    home_assistant: HomeAssistantConfig = Field(default_factory=lambda: HomeAssistantConfig(
        enabled=bool(os.getenv("HASS_TOKEN")),
        host=(os.getenv("HASS_URL") or "homeassistant.local").replace("http://", "").replace("https://", "").split(":")[0],
        token=os.getenv("HASS_TOKEN", ""),
    ))


# ── Instantiate: validation failure is fatal at startup ───────────────────────

try:
    _s = VectorSettings()
    logger.info("[VECTOR][config] Pydantic BaseSettings validated OK")
except Exception as _cfg_err:
    logger.critical(f"[VECTOR][config] Config validation FAILED: {_cfg_err}")
    raise SystemExit(1) from _cfg_err


# ── CONFIG dict — same structure as before, 100% backward compatible ──────────

class _Redacted(str):
    """String subclass whose repr redacts the value — prevents accidental secret leaks in logs."""
    def __repr__(self) -> str:
        return f"***({len(self)}chars)***"


def _secret(value: str) -> "_Redacted":
    return _Redacted(value)


CONFIG: dict = {
    "owner_name": "Arghyadeep",
    "system_name": "VECTOR",
    "version": "1.0.0",
    "env": _s.VECTOR_ENV,
    "debug": _s.VECTOR_DEBUG,
    "location": os.environ.get("VECTOR_LOCATION", "home"),
    "ofp_secret": _secret(_s.VECTOR_OFP_SECRET.get_secret_value()),
    "peers": _s.VECTOR_PEERS,
    "cloud_api_url": _s.VECTOR_CLOUD_API_URL,
    "oauth_redirect_base": _s.VECTOR_OAUTH_REDIRECT_BASE,
    "sentry_dsn": _s.SENTRY_DSN,
    "sentry_env": _s.VECTOR_ENV,
    "build_sha": _s.VECTOR_BUILD_SHA,
    "ldr_data_dir": _s.LDR_DATA_DIR,
    "search_response_limit": int(os.environ.get("VECTOR_SEARCH_LIMIT", "500")),
    "policy_default_score": float(os.environ.get("VECTOR_POLICY_DEFAULT", "0.5")),
    "decision_weights": {},     # override keys: goal, conf, policy, urgency, timing, cost
    "hp_tiers": {},             # override keys: elite, strong, healthy, weak
    "llm_pricing": {},          # override per-model pricing for budget tracking
    "vault_path": Path(_s.VECTOR_VAULT_PATH),
    "db_path": _BASE_DIR / "vector_memory.db",
    "ollama_host": _s.OLLAMA_HOST,
    "allowed_origins": _s.ALLOWED_ORIGINS,
    # Sub-configs as plain dicts — all existing CONFIG["x"]["y"] access works
    "models": _s.models.model_dump(),
    "model_router": _s.model_router.model_dump(),
    "api_keys": {
        "anthropic_key":          _secret(_s.ANTHROPIC_KEY.get_secret_value()),
        "gemini_key":             _secret(_s.GEMINI_KEY.get_secret_value()),
        "github_token":           _secret(_s.GITHUB_TOKEN.get_secret_value()),
        "github_username":        _s.GITHUB_USERNAME,
        "pushover_token":         _secret(_s.PUSHOVER_TOKEN.get_secret_value()),
        "pushover_user":          _s.PUSHOVER_USER,
        "supabase_url":           _s.SUPABASE_URL,
        "supabase_key":           _secret(_s.SUPABASE_KEY.get_secret_value()),
        "virustotal_key":         _secret(_s.VIRUSTOTAL_KEY.get_secret_value()),
        "newsapi_key":            _secret(_s.NEWSAPI_KEY.get_secret_value()),
        "stripe_key":             _secret(_s.STRIPE_KEY.get_secret_value()),
        "kiit_username":          _s.KIIT_USERNAME,
        "kiit_password":          _secret(_s.KIIT_PASSWORD.get_secret_value()),
        "google_credentials_path": _s.GOOGLE_CREDENTIALS_PATH,
        "youtube_channel_id":     _s.YOUTUBE_CHANNEL_ID,
        "instagram_access_token": _secret(_s.INSTAGRAM_ACCESS_TOKEN.get_secret_value()),
        "instagram_account_id":   _s.INSTAGRAM_ACCOUNT_ID,
        "elevenlabs_key":         _secret(_s.ELEVENLABS_KEY.get_secret_value()),
        "elevenlabs_voice_id":    _s.ELEVENLABS_VOICE_ID,
        "muapi_api_key":          _secret(_s.MUAPI_API_KEY.get_secret_value()),
        "pagespeed_api_key":      _secret(_s.PAGESPEED_API_KEY.get_secret_value()),
    },
    "media": {
        "wan2gp_url": _s.WAN2GP_URL,
        "use_lipsync_avatar": False,
        "portrait_image": "",   # set to a portrait photo path to enable lipsync avatar
    },
    "content_niche": _s.CONTENT_NICHE,
    "video_upload_delay_minutes": _s.VIDEO_UPLOAD_DELAY_MINUTES,
    # Top-level aliases so CONFIG.get("pushover_token") works (permission_gateway uses this)
    "pushover_token": _s.PUSHOVER_TOKEN.get_secret_value(),
    "pushover_user": _s.PUSHOVER_USER,
    "elevenlabs_key": _s.ELEVENLABS_KEY.get_secret_value(),
    "loop": _s.loop.model_dump(),
    "permission": _s.permission.model_dump(),
    "council": _s.council.model_dump(),
    "cost": _s.cost.model_dump(),
    "personality": _s.personality.model_dump(),
    "resilience": _s.resilience.model_dump(),
    "voice": _s.voice.model_dump(),
    "security": _s.security.model_dump(),
    "siem": _s.siem.model_dump(),
    "control": _s.control.model_dump(),
    "sensing": _s.sensing.model_dump(),
    "coding": {
        "github_token": _s.GITHUB_TOKEN.get_secret_value(),
        "repo_path": _s.coding.repo_path,
    },
    "comms": {
        "local_url": _s.comms.local_url,
        "port": _s.comms.port,
        "timeout_sec": _s.comms.timeout_sec,
        "repo_path": _s.comms.repo_path,
    },
    "turso_url": _s.TURSO_URL or _s.turso.url,
    "turso_token": _s.TURSO_TOKEN.get_secret_value() or _s.turso.token,
    "karpathy": {
        "runs_dir": _s.karpathy.runs_dir,
        "data_dir": _s.karpathy.data_dir,
        "daily_minutes": _s.karpathy.daily_minutes,
    },
    "airllm": {
        "models_dir": _s.airllm.models_dir,
        "cache_dir": _s.airllm.cache_dir,
        "max_gpu_memory_gb": _s.airllm.max_gpu_memory_gb,
    },
    "vectorcode": {
        "enabled": _s.vectorcode.enabled,
        "python_path": _s.vectorcode.python_path,
        "mcp_port": _s.vectorcode.mcp_port,
        "base_url": _s.vectorcode.base_url,
        "timeout_sec": _s.vectorcode.timeout_sec,
    },
    "obsidian": {
        "vault_path": _s.VECTOR_VAULT_PATH,
        "lightrag_working_dir": "./data/lightrag_vault",
        "watch_debounce_sec": 30,
        "ingest_on_startup": True,
        "protected_paths": ["CLAUDE.md", "GOALS.md", "VECTOR", "graphify-out", ".obsidian"],
        "vector_write_folders": ["Daily", "Reflections", "Council", "Agent HP", "Research", "Interviews", "Journals", "Reviews", "Health", "Finance", "Projects"],
        "personal_write_folders": ["00 Notes", "01 Journals", "02 Projects", "03 Reviews", "04 Skills", "wiki"],
    },
    "vector_finagent": {
        "terminal_binary": str(Path.home() / ".vector" / "vector_finagent" / "FinceptTerminal.exe"),
        "alpha_vantage_key": os.environ.get("ALPHA_VANTAGE_KEY", ""),
        "fred_api_key":      os.environ.get("FRED_API_KEY", ""),
        "polygon_key":       os.environ.get("POLYGON_API_KEY", ""),
        "edgar_api_key":     os.environ.get("EDGAR_API_KEY", ""),
        "data_cache_dir":    str(Path.home() / ".vector" / "vector_finagent" / "cache"),
    },
    "trading": {
        "llm_provider":        "openai",
        "deep_think_llm":      os.environ.get("DEEP_THINK_LLM", "vector-reasoning"),
        "quick_think_llm":     os.environ.get("QUICK_THINK_LLM", "vector-focus"),
        "max_debate_rounds":   1,
        "max_risk_rounds":     1,
        "checkpoint_enabled":  False,
        "output_language":     "English",
        "data_vendors": {
            "core_stock_apis":       "yfinance",
            "technical_indicators":  "yfinance",
            "fundamental_data":      "yfinance",
            "news_data":             "yfinance",
        },
        "results_dir":         str(Path.home() / ".vector" / "trading" / "logs"),
        "cache_dir":           str(Path.home() / ".vector" / "trading" / "cache"),
        "memory_log_path":     str(Path.home() / ".vector" / "trading" / "memory" / "trading_memory.md"),
    },
    "vector_hedgebot": {
        "openai_api_key":       os.environ.get("OPENAI_API_KEY", ""),
        "exa_api_key":          os.environ.get("EXA_API_KEY", ""),
        "jupiter_api_key":      os.environ.get("JUPITER_API_KEY", ""),
        "solana_private_key":   os.environ.get("SOLANA_PRIVATE_KEY", ""),
        "massive_api_key":      os.environ.get("MASSIVE_API_KEY", ""),
        "director_model":       os.environ.get("AUTOHEDGE_DIRECTOR_MODEL", "vector-reasoning"),
        "fast_model":           os.environ.get("AUTOHEDGE_FAST_MODEL", "vector-focus"),
        "output_dir":           str(Path.home() / ".vector" / "vector_hedgebot" / "outputs"),
        "logs_dir":             str(Path.home() / ".vector" / "vector_hedgebot" / "logs"),
        "live_trading":         False,      # set True + SOLANA_PRIVATE_KEY to enable execution
    },
    "vector_backtest": {
        "langchain_provider":  os.environ.get("LANGCHAIN_PROVIDER", "openai"),
        "langchain_model":     os.environ.get("LANGCHAIN_MODEL", "gpt-4.1"),
        "tushare_token":       os.environ.get("TUSHARE_TOKEN", ""),
        "ccxt_exchange":       os.environ.get("CCXT_EXCHANGE", "binance"),
        "token_threshold":     int(os.environ.get("TOKEN_THRESHOLD", "40000")),
        "workspace_dir":       str(Path.home() / ".vector" / "vector_backtest" / "workspace"),
        "memory_dir":          str(Path.home() / ".vector" / "vector_backtest" / "memory"),
        "runs_dir":            str(Path.home() / ".vector" / "vector_backtest" / "runs"),
        "skills_user_dir":     str(Path.home() / ".vector" / "vector_backtest" / "skills"),
        "enable_shell_tools":  False,
    },
    "vector_mlops": {
        "hf_token":          os.environ.get("HF_TOKEN", ""),
        "github_token":      os.environ.get("GITHUB_TOKEN", ""),
        "slack_bot_token":   os.environ.get("SLACK_BOT_TOKEN", ""),
        "slack_channel_id":  os.environ.get("SLACK_CHANNEL_ID", ""),
        "model_name":        os.environ.get("ML_INTERN_MODEL", "anthropic/claude-opus-4-6"),
        "yolo_mode":         False,
        "reasoning_effort":  "high",
        "save_sessions":     True,
        "tool_runtime":      "local",
        "sandbox_enabled":   False,
        "sessions_dir":      str(Path.home() / ".vector" / "vector_mlops" / "sessions"),
    },
    "vector_social_sim": {
        "llm_api_key":          os.environ.get("LLM_API_KEY", os.environ.get("OPENAI_API_KEY", "")),
        "llm_base_url":         os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
        "llm_model_name":       os.environ.get("LLM_MODEL_NAME", "gpt-4.1"),
        "llm_boost_api_key":    os.environ.get("LLM_BOOST_API_KEY", ""),
        "llm_boost_base_url":   os.environ.get("LLM_BOOST_BASE_URL", ""),
        "llm_boost_model_name": os.environ.get("LLM_BOOST_MODEL_NAME", ""),
        "zep_api_key":          os.environ.get("ZEP_API_KEY", ""),
        "uploads_dir":          str(Path.home() / ".vector" / "vector_social_sim" / "uploads"),
        "reports_dir":          str(Path.home() / ".vector" / "vector_social_sim" / "reports"),
        "simulations_dir":      str(Path.home() / ".vector" / "vector_social_sim" / "simulations"),
    },
    "smart_routing": {
        "enabled":        True,
        "default_profile": "auto",    # free | eco | auto | premium
        "proxy_port":     8402,
        "cache_ttl_sec":  30,
        "compress_min_chars": 2000,   # min message size to trigger compression
        "confidence_threshold": 0.70, # below this → LLM classifier fallback
    },
    "code_conductor": {
        "max_files":       20,        # max files for orchestrator to read per task
        "similarity_threshold": 0.8,  # git eval hunk match threshold
    },
    "stealth_browser": {
        "port":       9377,
        "api_key":    os.environ.get("STEALTH_BROWSER_API_KEY", ""),
        "admin_key":  os.environ.get("STEALTH_BROWSER_ADMIN_KEY", ""),
        "timeout_sec": 30,
    },
    "vision_control": {
        "max_loop":  25,
        "factors":   [1000, 1000],   # coordinate normalization (VLM outputs 0-1000 range)
        "loop_interval_sec": 0.5,
    },
    "comfyui": {
        "url": os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188"),
        "output_dir": os.environ.get("COMFYUI_OUTPUT_DIR", str(Path.home() / ".vector" / "comfyui" / "output")),
        "timeout": 120.0,
        "poll_interval": 1.5,
    },
    "task_queue": {
        "max_concurrent": 8,
    },
    "training": _s.training.model_dump(),
    "event_bus": _s.event_bus.model_dump(),
    "research_lab": _s.research_lab.model_dump(),
    "health": {
        "enabled": _s.health.enabled,
        "wearable_poll_interval_minutes": _s.health.wearable_poll_interval_minutes,
        "health_analysis_interval_minutes": _s.health.health_analysis_interval_minutes,
        "emergency_detection_interval_seconds": _s.health.emergency_detection_interval_seconds,
        "pushover_enabled": _s.health.pushover_enabled,
        "retention_days": _s.health.retention_days,
    },
    "emergency": {
        "enabled": _s.emergency.enabled,
        "detector_interval_sec": _s.emergency.detector_interval_sec,
        "pushover_enabled": _s.emergency.pushover_enabled,
        "quiet_hours_start": _s.emergency.quiet_hours_start,
        "quiet_hours_end": _s.emergency.quiet_hours_end,
        "rate_limit_pushover_monthly": _s.emergency.rate_limit_pushover_monthly,
    },
    "code_intel": {
        "project_id":        _s.code_intel.project_id,
        "qdrant_url":        _s.code_intel.qdrant_url,
        "embedding_provider":_s.code_intel.embedding_provider,
        "ollama_url":        _s.code_intel.ollama_url,
        "embedding_model":   _s.code_intel.embedding_model,
        "chunk_size":        _s.code_intel.chunk_size,
        "chunk_overlap":     _s.code_intel.chunk_overlap,
        "max_file_size_mb":  _s.code_intel.max_file_size_mb,
        "dist_path":         _s.code_intel.dist_path,
    },
    "predictive_analytics": {
        "enabled":                    _s.predictive_analytics.enabled,
        "forecast_interval_minutes":  _s.predictive_analytics.forecast_interval_minutes,
        "simulation_interval_minutes":_s.predictive_analytics.simulation_interval_minutes,
        "retention_days":             _s.predictive_analytics.retention_days,
        "pushover_enabled":           _s.predictive_analytics.pushover_enabled,
        "max_metrics":                _s.predictive_analytics.max_metrics,
    },
    "ads": {
        "scripts_path":          _s.ads.scripts_path,
        "references_path":       _s.ads.references_path,
        "templates_path":        _s.ads.templates_path,
        "image_provider_order":  _s.ads.image_provider_order,
        "pdf_output_dir":        _s.ads.pdf_output_dir,
        "screenshot_dir":        _s.ads.screenshot_dir,
        "max_concurrent_audits": _s.ads.max_concurrent_audits,
        "gemini_key":            os.environ.get("GEMINI_API_KEY", ""),
        "openai_key":            os.environ.get("OPENAI_API_KEY", ""),
        "stability_key":         os.environ.get("STABILITY_API_KEY", ""),
        "replicate_key":         os.environ.get("REPLICATE_API_TOKEN", ""),
        "pagespeed_key":         _s.PAGESPEED_API_KEY.get_secret_value(),
    },
    "home_assistant": _s.home_assistant.model_dump(),
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def get(key: str, default=None):
    return CONFIG.get(key, default)


def print_status() -> None:
    logger.info(f"Owner: {CONFIG['owner_name']}")
    logger.info(f"Environment: {CONFIG['env']}")
    logger.info(f"Ollama Host: {CONFIG['ollama_host']}")
    non_empty = sum(1 for v in CONFIG["api_keys"].values() if v)
    logger.info(f"Non-empty API keys: {non_empty}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print_status()
    # Validate all sub-model types are correct
    assert isinstance(CONFIG["loop"]["observe_interval_sec"], float)
    assert isinstance(CONFIG["permission"]["green"], list)
    assert isinstance(CONFIG["voice"]["sample_rate"], int)
    assert isinstance(CONFIG["models"]["focus"], str)
    assert "pushover_token" in CONFIG
    assert "allowed_origins" in CONFIG
    assert "obsidian" in CONFIG
    assert "write_note_personal" in CONFIG["permission"]["yellow"]
    assert "overwrite_note_personal" in CONFIG["permission"]["red"]
    print("✅ config.py OK")
