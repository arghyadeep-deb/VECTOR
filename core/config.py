import os
import sys
from pathlib import Path

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
    vision: str = "qwen2.5vl:7b"       # GUI automation + screen understanding (dedicated vision model)


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
    db_sync_hours: int = Field(24, ge=1, le=720)            # multi-DB mesh reconcile cadence
    command_poll_sec: float = Field(3.0, ge=0.5, le=60.0)   # remote command relay poll (Phase 4)
    reflect_hour: int = Field(2, ge=0, le=23)
    reflect_minute: int = Field(0, ge=0, le=59)


class PermissionConfig(BaseModel):
    green: list[str] = Field(default_factory=lambda: [
        "read_calendar", "play_music", "set_timer", "search_web",
        "take_screenshot", "check_weather", "check_attendance",
        "progress_goal", "kickstart_goal",
        "analyze_progress", "research_topic", "check_deadline", "review_goal",
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
        # Hand Execution Engine — scheduled autonomous Hands with
        # requires_approval=False (hands/registry.py). GREEN = auto-execute,
        # no owner gate (matches each Hand's own requires_approval flag).
        "hand_researcher", "hand_collector", "hand_predictor",
        "hand_trader", "hand_lead", "hand_vault_sync",
    ])
    yellow: list[str] = Field(default_factory=lambda: [
        "send_message_routine", "create_calendar_event", "commit_code",
        "download_file", "set_reminder", "write_note_personal",
        "launch_app", "run_shell_command",
        "pc_screenshot", "pc_type", "pc_click", "pc_launch_app",
        # GUIAutomationAgent (core/vision_control) — VLM-driven desktop/browser control
        "gui_task", "click_screen", "desktop_task", "browser_task", "vision_control",
        "monthly_report", "finance_report", "journal", "weekly_journal",
        "create_project", "add_deadline", "log_exercise",
        # VectorCode write/execute actions
        "code_task", "code_generate", "code_fix", "code_debug", "run_tests",
    ])
    red: list[str] = Field(default_factory=lambda: [
        "send_email", "delete_files", "execute_code",
        "financial_transaction", "push_github", "deploy_production",
        "overwrite_note_personal",
        # Hand Execution Engine — Hands with requires_approval=True
        # (browser: purchases/forms; content: publishing; clip: upload).
        "hand_browser", "hand_content", "hand_clip",
        # Real money / irreversible outward actions — owner approval ALWAYS
        # (audit 2026-06-21: these previously bypassed the gateway entirely).
        # solana_swap_execute: notifies owner with price + reasoning, signs only on approval.
        "solana_swap_execute", "content_publish",
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
    # Voice cloning (voicebox absorption — chatterbox-tts optional install)
    cloning_engine: str = "chatterbox"       # "chatterbox" | "voxcpm"
    cloning_model_dir: str = str(Path(__file__).parent.parent / "models" / "chatterbox")
    cloning_device: str = "cuda"
    cloning_exaggeration: float = Field(0.5, ge=0.0, le=1.0)
    cloning_cfg_weight: float = Field(0.5, ge=0.0, le=1.0)
    default_voice_profile: str = ""          # profile name from voice_profiles collection
    prefer_local_voice: bool = True          # True → local cloning before ElevenLabs cloud
    effects_default: list = Field(default_factory=list)   # default DSP chain for new profiles
    # VoxCPM2 absorption (docs/repo_analysis/VoxCPM.md) — alternate
    # cloning_engine, on-demand load (8GB VRAM), never permanent-resident
    # alongside vector-focus. Apache-2.0, guarded optional install (`pip
    # install voxcpm`). Kept off Hindi by default — vendor's own WER is weak.
    voxcpm_model_dir: str = str(Path(__file__).parent.parent / "models" / "voxcpm")
    voxcpm_inference_timesteps: int = Field(10, ge=1, le=100)
    voxcpm_cfg_value: float = Field(2.0, ge=0.0, le=10.0)
    voice_design_description: str = (
        "A calm, articulate British male voice, mid-30s, measured pace, "
        "warm but precise — like a trusted technical advisor."
    )


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
    screen_enabled: bool = False
    camera_enabled: bool = False
    # Task B.2 (governor-wiring-and-ambient-perception.md): ADB-phone observe
    # source. Defaults off — owner-hardware-dependent (needs a connected
    # Android device + adb on PATH). PhoneController already degrades
    # gracefully (is_connected()=False, get_notifications()=[]) when absent.
    phone_enabled: bool = False
    # Task B.3: wearable (HR/sleep/steps) observe source. Architecture docs
    # name it as a core observe source; zero wiring existed before this.
    # Owner-hardware-dependent (no wearable device/API credentials
    # configured yet) — defaults off. districts/health/wearable_connector.py
    # already degrades gracefully to an empty poll with no sources enabled.
    wearable_enabled: bool = False


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


class SidecarsConfig(BaseModel):
    # Paths to sidecar applications that VECTOR can launch alongside itself.
    # Leave empty ("") to use the default location under the parent of the
    # VECTOR codebase (i.e. <codebase-parent>/GitHub/<AppName>).
    # Set a non-empty path to point at wherever you cloned/installed the app.
    #
    # LibreChat: no npm package exists; must be cloned locally.
    #   Default: <codebase-parent>/GitHub/LibreChat-main
    #   Override: set VECTOR_LIBRECHAT_PATH env var or change this field.
    librechat_path: str = ""
    #
    # ComfyUI: local Stable-Diffusion node UI; must be cloned locally.
    #   Default: <codebase-parent>/GitHub/ComfyUI-master
    #   Override: set VECTOR_COMFYUI_PATH env var.
    comfyui_path: str = ""
    #
    # hyperframes: local Node media-frame server; must be cloned locally.
    #   Default: <codebase-parent>/GitHub/hyperframes-main
    #   Override: set VECTOR_HYPERFRAMES_PATH env var.
    hyperframes_path: str = ""


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

    def _mapping_value(self, key: str, default=None):
        if not hasattr(self, key):
            return default
        value = getattr(self, key)
        if isinstance(value, BaseModel):
            return value.model_dump()
        return value

    def get(self, key: str, default=None):
        return self._mapping_value(key, default)

    def __getitem__(self, key: str):
        if not hasattr(self, key):
            raise KeyError(key)
        return self._mapping_value(key)

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and hasattr(self, key)

    # Core — mapped from env var names
    VECTOR_ENV: str = "development"
    VECTOR_DEBUG: bool = False
    VECTOR_VAULT_PATH: str = str(Path.home() / "V.E.C.T.O.R Brain")
    OLLAMA_HOST: str = "http://127.0.0.1:11434"
    VECTOR_DB_KEY: SecretStr = SecretStr("")

    # API keys — SecretStr prevents values leaking into logs or repr()
    ANTHROPIC_KEY: SecretStr = SecretStr("")
    GEMINI_KEY: SecretStr = SecretStr("")
    GITHUB_TOKEN: SecretStr = SecretStr("")
    GITHUB_USERNAME: str = "arghyadeep-deb"
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
    # Repo integration (docs/repo_analysis/youtube-automation-agent.md):
    # read-only Data API key for trending/competitor lookups — separate from
    # GOOGLE_CREDENTIALS_PATH's OAuth flow (uploads only need OAuth).
    YOUTUBE_DATA_API_KEY: SecretStr = SecretStr("")
    INSTAGRAM_ACCESS_TOKEN: SecretStr = SecretStr("")
    INSTAGRAM_ACCOUNT_ID: str = ""
    ELEVENLABS_KEY: SecretStr = SecretStr("")
    ELEVENLABS_VOICE_ID: str = "pNInz6obpgDQGcFmaJgB"
    OPENROUTER_KEY: SecretStr = SecretStr("")
    MISTRAL_KEY: SecretStr = SecretStr("")
    CONTENT_NICHE: str = "AI"
    VIDEO_UPLOAD_DELAY_MINUTES: int = 30
    MUAPI_API_KEY: SecretStr = SecretStr("")
    WAN2GP_URL: str = ""
    PAGESPEED_API_KEY: SecretStr = SecretStr("")
    HASS_URL: str = ""
    HASS_TOKEN: SecretStr = SecretStr("")

    # LLM provider keys used by absorbed vectorcode/src/ (naming: _API_KEY suffix used there)
    GROQ_API_KEY: SecretStr = SecretStr("")
    XAI_API_KEY: SecretStr = SecretStr("")
    MINIMAX_API_KEY: SecretStr = SecretStr("")
    TAVILY_API_KEY: SecretStr = SecretStr("")
    FIRECRAWL_API_KEY: SecretStr = SecretStr("")
    HONCHO_API_KEY: SecretStr = SecretStr("")
    DEEPGRAM_API_KEY: SecretStr = SecretStr("")
    OLLAMA_API_KEY: SecretStr = SecretStr("")
    AZURE_ANTHROPIC_KEY: SecretStr = SecretStr("")
    AZURE_FOUNDRY_API_KEY: SecretStr = SecretStr("")
    GOOGLE_API_KEY: SecretStr = SecretStr("")
    OPENAI_CODEX_API_KEY: SecretStr = SecretStr("")
    HINDSIGHT_API_KEY: SecretStr = SecretStr("")
    BROWSERBASE_API_KEY: SecretStr = SecretStr("")
    # Runtime vars used by absorbed vectorcode/src/
    VECTOR_HOME: str = str(Path.home() / ".vector")
    VECTOR_TIMEZONE: str = "Asia/Kolkata"
    VECTOR_ALLOW_SHELL_EXEC: bool = False
    VECTOR_WRITE_SAFE_ROOT: str = ""
    VECTOR_ALLOW_PRIVATE_URLS: bool = False
    VECTOR_ALLOW_COMMIT_DRIFT: bool = False

    # Network
    VECTOR_OFP_SECRET: SecretStr = SecretStr("")
    VECTOR_OFP_CERT: str = ""
    VECTOR_OFP_KEY: str = ""
    VECTOR_PEERS: str = ""
    VECTOR_CLOUD_API_URL: str = ""
    VECTOR_BRAIN_URL: str = ""
    VECTOR_BRAIN_API_KEY: SecretStr = SecretStr("")
    VECTOR_OAUTH_REDIRECT_BASE: str = "http://localhost:7788"

    # Collections engine (PocketBase-style data layer) — JWT auth secret
    VECTOR_JWT_SECRET: SecretStr = SecretStr("")

    # Telemetry
    SENTRY_DSN: str = ""
    VECTOR_BUILD_SHA: str = "dev"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""

    # Infrastructure
    VLLM_BASE_URL: str = "http://localhost:8000/v1"
    CLOUDFLARE_ACCOUNT_ID: str = ""
    SSL_CERT_FILE: str = ""
    SSL_CERT_DIR: str = ""
    ACP_LOGGING_ENABLED: bool = False

    # Sidecar app paths (overrides SidecarsConfig defaults)
    VECTOR_LIBRECHAT_PATH: str = ""
    VECTOR_COMFYUI_PATH: str = ""
    VECTOR_HYPERFRAMES_PATH: str = ""

    # Research engine
    LDR_DATA_DIR: str = ""
    LDR_LOG_SETTINGS: str = "none"

    # OAuth
    OAUTH_GITHUB_CLIENT_ID: str = ""
    OAUTH_GITHUB_CLIENT_SECRET: SecretStr = SecretStr("")
    OAUTH_GOOGLE_CLIENT_ID: str = ""
    OAUTH_GOOGLE_CLIENT_SECRET: SecretStr = SecretStr("")

    # Trading
    VECTOR_TRADING_RESULTS_DIR: str = "logs"
    VECTOR_TRADING_CACHE_DIR: str = "cache"
    VECTOR_TRADING_MEMORY_LOG_PATH: str = "memory/trading_memory.md"

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
    sidecars: SidecarsConfig = Field(default_factory=SidecarsConfig)
    ads: AdsConfig = Field(default_factory=AdsConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    emergency: EmergencyConfig = Field(default_factory=EmergencyConfig)
    code_intel: CodeIntelConfig = Field(default_factory=CodeIntelConfig)
    event_bus: EventBusConfig = Field(default_factory=EventBusConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)
    research_lab: ResearchLabConfig = Field(default_factory=ResearchLabConfig)
    home_assistant: HomeAssistantConfig = Field(default_factory=lambda: HomeAssistantConfig(
        # os.getenv intentional — lambda can't access self
        enabled=bool(os.getenv("HASS_TOKEN")),
        host=(os.getenv("HASS_URL") or "homeassistant.local").replace("http://", "").replace("https://", "").split(":")[0],
        token=os.getenv("HASS_TOKEN", ""),
    ))

    def get_env(self, key: str, default: str | None = None) -> str | None:
        return os.getenv(key, default)


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


def _normalize_base_url(value: str, default: str = "http://127.0.0.1:11434") -> str:
    value = (value or default).strip()
    if not value:
        return default
    if "://" not in value:
        value = f"http://{value}"
    return value.rstrip("/")


def _normalize_supabase_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    if "://" in value:
        return value
    if "." not in value and "/" not in value:
        return f"https://{value}.supabase.co"
    return f"https://{value}"


def _normalize_turso_http_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    if value.startswith("libsql://"):
        return "https://" + value[len("libsql://"):]
    return value


CONFIG: dict = {
    "owner_name": "Arghyadeep",
    "system_name": "VECTOR",
    "version": "1.0.0",
    "env": _s.VECTOR_ENV,
    "debug": _s.VECTOR_DEBUG,
    "location": os.environ.get("VECTOR_LOCATION", "home"),
    "ofp_secret": _secret(_s.VECTOR_OFP_SECRET.get_secret_value()),
    "peers": _s.VECTOR_PEERS,
    "ofp_cert": _s.VECTOR_OFP_CERT,
    "ofp_key": _s.VECTOR_OFP_KEY,
    "cloud_api_url": _s.VECTOR_CLOUD_API_URL,
    "cloud": {
        "brain_url": _s.VECTOR_BRAIN_URL,
        "api_key": _secret(_s.VECTOR_BRAIN_API_KEY.get_secret_value()),
    },
    "oauth_redirect_base": _s.VECTOR_OAUTH_REDIRECT_BASE,
    "sentry_dsn": _s.SENTRY_DSN,
    "sentry_env": _s.VECTOR_ENV,
    "otel_endpoint": _s.OTEL_EXPORTER_OTLP_ENDPOINT,
    "vllm_base_url": _s.VLLM_BASE_URL,
    "cloudflare_account_id": _s.CLOUDFLARE_ACCOUNT_ID,
    "ssl_cert_file": _s.SSL_CERT_FILE,
    "ssl_cert_dir": _s.SSL_CERT_DIR,
    "acp_logging_enabled": _s.ACP_LOGGING_ENABLED,
    "build_sha": _s.VECTOR_BUILD_SHA,
    "ldr_data_dir": _s.LDR_DATA_DIR,
    "search_response_limit": int(os.environ.get("VECTOR_SEARCH_LIMIT", "500")),
    "policy_default_score": float(os.environ.get("VECTOR_POLICY_DEFAULT", "0.5")),
    # ── LLM routing policy (simple→cloud keys, heavy-security→local Ollama) ──
    # prefer_local_for_heavy=False → COMPLEX/REASONING go cloud-premium first (speed);
    #   set VECTOR_PREFER_LOCAL_HEAVY=1 to route heavy tasks to local gemma4:26b first.
    # distribute_simple=True → round-robin simple tasks across configured cloud providers.
    "routing": {
        "prefer_local_for_heavy": os.environ.get("VECTOR_PREFER_LOCAL_HEAVY", "0") in ("1", "true", "True"),
        "distribute_simple": os.environ.get("VECTOR_DISTRIBUTE_SIMPLE", "1") in ("1", "true", "True"),
    },
    # ── Avatar presence / trigger mode ────────────────────────────────────────
    # mode: proactive | hybrid | reactive  (see core/loop/presence.py)
    "presence": {
        "mode": os.environ.get("VECTOR_PRESENCE_MODE", "proactive"),
        "dnd_start_hour": int(os.environ.get("VECTOR_DND_START", "23")),
        "dnd_end_hour":   int(os.environ.get("VECTOR_DND_END",   "8")),
        "allowed_proactive_agents": ["nudge_engine", "chief_of_staff", "daily_reviewer"],
        "wake_keywords": ["hey vector", "vector", "ok vector"],
    },
    "vector_home": _s.VECTOR_HOME,
    "vector_timezone": _s.VECTOR_TIMEZONE,
    "allow_shell_exec": _s.VECTOR_ALLOW_SHELL_EXEC,
    "write_safe_root": _s.VECTOR_WRITE_SAFE_ROOT,
    "allow_private_urls": _s.VECTOR_ALLOW_PRIVATE_URLS,
    "allow_commit_drift": _s.VECTOR_ALLOW_COMMIT_DRIFT,
    "decision_weights": {},     # override keys: goal, conf, policy, urgency, timing, cost
    "hp_tiers": {},             # override keys: elite, strong, healthy, weak
    "llm_pricing": {},          # override per-model pricing for budget tracking
    "vault_path": Path(_s.VECTOR_VAULT_PATH),
    "db_path": _BASE_DIR / "vector_memory.db",
    "db_key": _secret(_s.VECTOR_DB_KEY.get_secret_value()),
    "ollama_host": _normalize_base_url(_s.OLLAMA_HOST),
    "allowed_origins": _s.ALLOWED_ORIGINS,
    "oauth": {
        "github_client_id": _s.OAUTH_GITHUB_CLIENT_ID,
        "github_client_secret": _secret(_s.OAUTH_GITHUB_CLIENT_SECRET.get_secret_value()),
        "google_client_id": _s.OAUTH_GOOGLE_CLIENT_ID,
        "google_client_secret": _secret(_s.OAUTH_GOOGLE_CLIENT_SECRET.get_secret_value()),
    },
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
        "supabase_url":           _normalize_supabase_url(_s.SUPABASE_URL),
        "supabase_key":           _secret(_s.SUPABASE_KEY.get_secret_value()),
        "virustotal_key":         _secret(_s.VIRUSTOTAL_KEY.get_secret_value()),
        "newsapi_key":            _secret(_s.NEWSAPI_KEY.get_secret_value()),
        "stripe_key":             _secret(_s.STRIPE_KEY.get_secret_value()),
        "kiit_username":          _s.KIIT_USERNAME,
        "kiit_password":          _secret(_s.KIIT_PASSWORD.get_secret_value()),
        "google_credentials_path": _s.GOOGLE_CREDENTIALS_PATH,
        "youtube_channel_id":     _s.YOUTUBE_CHANNEL_ID,
        "youtube_data_api_key":   _secret(_s.YOUTUBE_DATA_API_KEY.get_secret_value()),
        "instagram_access_token": _secret(_s.INSTAGRAM_ACCESS_TOKEN.get_secret_value()),
        "instagram_account_id":   _s.INSTAGRAM_ACCOUNT_ID,
        "elevenlabs_key":         _secret(_s.ELEVENLABS_KEY.get_secret_value()),
        "elevenlabs_voice_id":    _s.ELEVENLABS_VOICE_ID,
        "openrouter_key":         _secret(_s.OPENROUTER_KEY.get_secret_value()),
        "mistral_key":            _secret(_s.MISTRAL_KEY.get_secret_value()),
        "muapi_api_key":          _secret(_s.MUAPI_API_KEY.get_secret_value()),
        "pagespeed_api_key":      _secret(_s.PAGESPEED_API_KEY.get_secret_value()),
        "hass_url":               _s.HASS_URL,
        "hass_token":             _secret(_s.HASS_TOKEN.get_secret_value()),
        "openai_api_key":         os.environ.get("OPENAI_API_KEY", ""),
        "groq_api_key":           _secret(_s.GROQ_API_KEY.get_secret_value()),
        "xai_api_key":            _secret(_s.XAI_API_KEY.get_secret_value()),
        "minimax_api_key":        _secret(_s.MINIMAX_API_KEY.get_secret_value()),
        "tavily_api_key":         _secret(_s.TAVILY_API_KEY.get_secret_value()),
        "firecrawl_api_key":      _secret(_s.FIRECRAWL_API_KEY.get_secret_value()),
        "honcho_api_key":         _secret(_s.HONCHO_API_KEY.get_secret_value()),
        "deepgram_api_key":       _secret(_s.DEEPGRAM_API_KEY.get_secret_value()),
        "ollama_api_key":         _secret(_s.OLLAMA_API_KEY.get_secret_value()),
        "azure_anthropic_key":    _secret(_s.AZURE_ANTHROPIC_KEY.get_secret_value()),
        "azure_foundry_api_key":  _secret(_s.AZURE_FOUNDRY_API_KEY.get_secret_value()),
        "google_api_key":         _secret(_s.GOOGLE_API_KEY.get_secret_value()),
        "openaicodex_api_key":    _secret(_s.OPENAI_CODEX_API_KEY.get_secret_value()),
        "hindsight_api_key":      _secret(_s.HINDSIGHT_API_KEY.get_secret_value()),
        "browserbase_api_key":    _secret(_s.BROWSERBASE_API_KEY.get_secret_value()),
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
    "turso_url": _normalize_turso_http_url(_s.TURSO_URL or _s.turso.url),
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
    # ── Investment Safety Controls ────────────────────────────────────────────
    # CRITICAL: paper_trading=True is the safe default. Set False ONLY after
    # verifying all gateway/kill-switch checks pass. kill_switch=True halts
    # ALL trade execution across every investment district immediately.
    "investment": {
        "paper_trading":       True,    # True = simulate only, never sends real orders
        "kill_switch":         False,   # True = halt ALL execution immediately
        "max_position_size":   10000,   # Maximum position size in ₹ (base currency)
        "daily_loss_cap":      5000,    # Maximum daily loss in ₹ before auto-halt
        "max_trades_per_day":  10,      # Maximum number of live trades per calendar day
    },
    "trading": {
        # Ollama is VECTOR's primary local-first runtime (RULE 11). The trading
        # graph's OpenAI-compatible client routes "ollama" to
        # http://localhost:11434/v1 with no API key required (see
        # core/trading/llm_clients/openai_client.py + api_key_env.py). Leaving
        # this as "openai" broke every analysis with "Missing credentials"
        # since model names below (vector-reasoning/vector-focus) are Ollama
        # custom models, not real OpenAI models.
        "llm_provider":        os.environ.get("TRADING_LLM_PROVIDER", "ollama"),
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
    "browser": {
        # Named Playwright auth profiles (login-once, reuse-later)
        "auth_profiles_dir": os.environ.get(
            "VECTOR_BROWSER_AUTH_DIR",
            str(Path.home() / ".vector" / "browser_auth"),
        ),
        # DOM pruner — max interactive elements kept per observation (18k→~500 tokens)
        "dom_pruner_max_elements": 20,
        # PII scrubber switches
        "pii_scrub_enabled":      True,
        "pii_scrub_screenshot":   True,
        "pii_scrub_network":      True,
        "pii_scrub_console":      True,
        "pii_scrub_replacement":  "[REDACTED]",
        "pii_scrub_patterns":     "",   # empty = all default patterns (excludes noisy generic_hex_token)
        "pii_scrub_audit_report": True,
    },
    "vision_control": {
        "max_loop":  25,
        "factors":   [1000, 1000],   # coordinate normalization (VLM outputs 0-1000 range)
        "loop_interval_sec": 0.5,
    },
    "comfyui": {
        "path": os.environ.get("COMFYUI_PATH", ""),  # Override ComfyUI install path (default: GitHub/ComfyUI-master)
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
    # ── Collections engine (PocketBase absorption) ───────────────────────────
    "collections": {
        "enabled": os.environ.get("VECTOR_COLLECTIONS_ENABLED", "1") in ("1", "true", "True"),
        "storage": {
            "backend":       os.environ.get("VECTOR_COLLECTIONS_BACKEND", "local"),  # local | s3
            "local_root":    os.environ.get("VECTOR_COLLECTIONS_ROOT",
                                            str(Path(_s.VECTOR_HOME) / "collections_files")),
            "s3_bucket":     os.environ.get("VECTOR_S3_BUCKET", ""),
            "s3_region":     os.environ.get("VECTOR_S3_REGION", ""),
            "s3_endpoint":   os.environ.get("VECTOR_S3_ENDPOINT", ""),
            "s3_access_key": os.environ.get("VECTOR_S3_ACCESS_KEY", ""),
            "s3_secret_key": os.environ.get("VECTOR_S3_SECRET_KEY", ""),
            "s3_public_base": os.environ.get("VECTOR_S3_PUBLIC_BASE", ""),
        },
        "jwt": {
            "secret":          _s.VECTOR_JWT_SECRET.get_secret_value(),
            "access_ttl_sec":  int(os.environ.get("VECTOR_JWT_ACCESS_TTL", "900")),
            "refresh_ttl_sec": int(os.environ.get("VECTOR_JWT_REFRESH_TTL", "1209600")),
        },
    },
    "knowledge": {
        # Output directory for domain-context.json and assembled-graph.json files
        "output_dir": os.environ.get("VECTOR_KNOWLEDGE_OUTPUT_DIR",
                                     str(Path(_s.VECTOR_HOME) / "knowledge_graphs")),
        # Maximum output JSON size in bytes (default 512 KB)
        "max_output_bytes": int(os.environ.get("VECTOR_KNOWLEDGE_MAX_BYTES", str(512 * 1024))),
        # Karpathy wiki root (Obsidian brain vault)
        "wiki_root": os.environ.get("VECTOR_WIKI_ROOT",
                                    str(Path(_s.VECTOR_HOME).parent / "V.E.C.T.O.R. Brain")),
    },
    # ── Sidecar app paths ─────────────────────────────────────────────────────
    # These apps have no pip/npm package; they must be cloned locally.
    # Defaults point to <codebase-parent>/GitHub/<AppName> — the conventional
    # layout used when all repos live next to each other.
    # Override any path via the corresponding env var or .env key so that the
    # cloned repos can live anywhere (or be deleted entirely — VECTOR silently
    # skips sidecars whose directory does not exist).
    #
    #   VECTOR_LIBRECHAT_PATH   — LibreChat clone  (node api/server/index.js)
    #   VECTOR_COMFYUI_PATH     — ComfyUI clone    (python main.py)
    #   VECTOR_HYPERFRAMES_PATH — hyperframes clone (node packages/producer/dist/server.js)
    "sidecars": {
        "librechat_path":   _s.VECTOR_LIBRECHAT_PATH or _s.sidecars.librechat_path,
        "comfyui_path":     _s.VECTOR_COMFYUI_PATH or _s.sidecars.comfyui_path,
        "hyperframes_path": _s.VECTOR_HYPERFRAMES_PATH or _s.sidecars.hyperframes_path,
    },
}

# ── Afterburner: inject CONFIG values into os.environ for absorbed code ──────
# vectorcode/src/ (Hermes/OpenJarvis/Ruflo) uses os.getenv() directly (~1500 calls).
# Instead of editing 330+ files, we pre-populate os.environ with CONFIG values
# at startup. Existing os.getenv() calls automatically pick up CONFIG settings.
# Shell env takes precedence (setdefault, not set).

_CFG = CONFIG  # local alias for lazy closures


def _resolve_cfg(path: str, default: str = "") -> str:
    """Resolve a dotted CONFIG path like 'api_keys.anthropic_key' to a value."""
    val: object = _CFG
    for part in path.split("."):
        if isinstance(val, dict):
            val = val.get(part, default)
        else:
            return default
    if isinstance(val, str):
        return val
    if isinstance(val, bool):
        return "1" if val else "0"
    return default


# Maps: target env var name → CONFIG dotted path
_ENV_ALIASES: dict[str, str] = {
    # Naming mismatches: CONFIG uses shorter keys, vectorcode/src/ uses _API_KEY suffix
    "ANTHROPIC_API_KEY":     "api_keys.anthropic_key",
    "GEMINI_API_KEY":        "api_keys.gemini_key",
    "MISTRAL_API_KEY":       "api_keys.mistral_key",
    "OPENROUTER_API_KEY":    "api_keys.openrouter_key",
    "ELEVENLABS_API_KEY":    "api_keys.elevenlabs_key",
    "OPENAI_API_KEY":        "api_keys.openai_api_key",
    "GROQ_API_KEY":          "api_keys.groq_api_key",
    "XAI_API_KEY":           "api_keys.xai_api_key",
    "MINIMAX_API_KEY":       "api_keys.minimax_api_key",
    "TAVILY_API_KEY":        "api_keys.tavily_api_key",
    "FIRECRAWL_API_KEY":     "api_keys.firecrawl_api_key",
    "HONCHO_API_KEY":        "api_keys.honcho_api_key",
    "DEEPGRAM_API_KEY":      "api_keys.deepgram_api_key",
    "OLLAMA_API_KEY":        "api_keys.ollama_api_key",
    "AZURE_ANTHROPIC_KEY":   "api_keys.azure_anthropic_key",
    "AZURE_FOUNDRY_API_KEY": "api_keys.azure_foundry_api_key",
    "GOOGLE_API_KEY":        "api_keys.google_api_key",
    "OPENAI_CODEX_API_KEY":  "api_keys.openaicodex_api_key",
    "HINDSIGHT_API_KEY":     "api_keys.hindsight_api_key",
    "BROWSERBASE_API_KEY":   "api_keys.browserbase_api_key",
    # Runtime vars with different CONFIG key names
    "VECTOR_HOME":            "vector_home",
    "VECTOR_TIMEZONE":        "vector_timezone",
    "VECTOR_ALLOW_SHELL_EXEC":"allow_shell_exec",
    "VECTOR_WRITE_SAFE_ROOT": "write_safe_root",
    "VECTOR_ALLOW_PRIVATE_URLS": "allow_private_urls",
    "VECTOR_ALLOW_COMMIT_DRIFT": "allow_commit_drift",
    "VECTOR_DB_KEY":          "db_key",
    # Duplicate api_keys entries with top-level keys for broad coverage
    "GITHUB_TOKEN":           "api_keys.github_token",
    "ELEVENLABS_KEY":         "api_keys.elevenlabs_key",
    "HASS_TOKEN":             "api_keys.hass_token",
    "HASS_URL":               "api_keys.hass_url",
    "NEWSAPI_KEY":            "api_keys.newsapi_key",
    "VIRUSTOTAL_KEY":         "api_keys.virustotal_key",
    "STRIPE_KEY":             "api_keys.stripe_key",
    "SUPABASE_KEY":           "api_keys.supabase_key",
    "PUSHOVER_TOKEN":         "api_keys.pushover_token",
    "PUSHOVER_USER":          "api_keys.pushover_user",
    "INSTAGRAM_ACCESS_TOKEN":  "api_keys.instagram_access_token",
    "KIIT_USERNAME":          "api_keys.kiit_username",
    "KIIT_PASSWORD":          "api_keys.kiit_password",
    "MUAPI_API_KEY":          "api_keys.muapi_api_key",
    "PAGESPEED_API_KEY":      "api_keys.pagespeed_api_key",
    "ELEVENLABS_VOICE_ID":    "api_keys.elevenlabs_voice_id",
    "YOUTUBE_CHANNEL_ID":     "api_keys.youtube_channel_id",
    "INSTAGRAM_ACCOUNT_ID":   "api_keys.instagram_account_id",
}


def inject_env() -> None:
    """Populate os.environ with CONFIG values. Uses setdefault so shell env wins."""
    for env_key, cfg_path in _ENV_ALIASES.items():
        val = _resolve_cfg(cfg_path)
        if val:
            os.environ.setdefault(env_key, val)


inject_env()

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
