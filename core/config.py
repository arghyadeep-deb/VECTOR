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


class VoiceConfig(BaseModel):
    whisper_model: str = "large-v3"
    kokoro_model_dir: str = str(Path(__file__).parent.parent / "models" / "kokoro")
    kokoro_speed: float = Field(0.85, ge=0.1, le=3.0)
    wake_threshold: float = Field(0.5, ge=0.0, le=1.0)
    record_duration_sec: float = Field(5.0, ge=1.0, le=120.0)
    sample_rate: int = Field(16000, ge=8000, le=96000)
    wake_phrase: str = "hey_vector"


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


# ── Main settings (reads from .env) ───────────────────────────────────────────

class VectorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BASE_DIR / ".env",
        extra="ignore",
        case_sensitive=False,
    )

    # Core — mapped from env var names
    VECTOR_ENV: str = "development"
    VECTOR_DEBUG: bool = True
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
    CONTENT_NICHE: str = "AI"
    VIDEO_UPLOAD_DELAY_MINUTES: int = 30
    MUAPI_API_KEY: SecretStr = SecretStr("")
    WAN2GP_URL: str = ""
    PAGESPEED_API_KEY: SecretStr = SecretStr("")

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
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    security: SecurityCfg = Field(default_factory=SecurityCfg)
    control: ControlConfig = Field(default_factory=ControlConfig)
    sensing: SensingConfig = Field(default_factory=SensingConfig)
    coding: CodingConfig = Field(default_factory=CodingConfig)
    comms: VectorCodeCommsConfig = Field(default_factory=VectorCodeCommsConfig)
    turso: TursoConfig = Field(default_factory=TursoConfig)
    karpathy: KarpathyConfig = Field(default_factory=KarpathyConfig)
    airllm: AirLLMConfig = Field(default_factory=AirLLMConfig)
    vectorcode: VectorCodeConfig = Field(default_factory=VectorCodeConfig)


# ── Instantiate: validation failure is fatal at startup ───────────────────────

try:
    _s = VectorSettings()
    logger.info("[VECTOR][config] Pydantic BaseSettings validated OK")
except Exception as _cfg_err:
    logger.critical(f"[VECTOR][config] Config validation FAILED: {_cfg_err}")
    raise SystemExit(1) from _cfg_err


# ── CONFIG dict — same structure as before, 100% backward compatible ──────────

CONFIG: dict = {
    "owner_name": "Arghyadeep",
    "system_name": "VECTOR",
    "version": "1.0.0",
    "env": _s.VECTOR_ENV,
    "debug": _s.VECTOR_DEBUG,
    "vault_path": Path(_s.VECTOR_VAULT_PATH),
    "db_path": _BASE_DIR / "vector_memory.db",
    "ollama_host": _s.OLLAMA_HOST,
    "allowed_origins": _s.ALLOWED_ORIGINS,
    # Sub-configs as plain dicts — all existing CONFIG["x"]["y"] access works
    "models": _s.models.model_dump(),
    "model_router": _s.model_router.model_dump(),
    "api_keys": {
        "anthropic_key": _s.ANTHROPIC_KEY.get_secret_value(),
        "gemini_key": _s.GEMINI_KEY.get_secret_value(),
        "github_token": _s.GITHUB_TOKEN.get_secret_value(),
        "github_username": _s.GITHUB_USERNAME,
        "pushover_token": _s.PUSHOVER_TOKEN.get_secret_value(),
        "pushover_user": _s.PUSHOVER_USER,
        "supabase_url": _s.SUPABASE_URL,
        "supabase_key": _s.SUPABASE_KEY.get_secret_value(),
        "virustotal_key": _s.VIRUSTOTAL_KEY.get_secret_value(),
        "newsapi_key": _s.NEWSAPI_KEY.get_secret_value(),
        "stripe_key": _s.STRIPE_KEY.get_secret_value(),
        "kiit_username": _s.KIIT_USERNAME,
        "kiit_password": _s.KIIT_PASSWORD.get_secret_value(),
        "google_credentials_path": _s.GOOGLE_CREDENTIALS_PATH,
        "youtube_channel_id": _s.YOUTUBE_CHANNEL_ID,
        "instagram_access_token": _s.INSTAGRAM_ACCESS_TOKEN.get_secret_value(),
        "instagram_account_id": _s.INSTAGRAM_ACCOUNT_ID,
        "elevenlabs_key": _s.ELEVENLABS_KEY.get_secret_value(),
        "muapi_api_key": _s.MUAPI_API_KEY.get_secret_value(),
        "pagespeed_api_key": _s.PAGESPEED_API_KEY.get_secret_value(),
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
    "loop": _s.loop.model_dump(),
    "permission": _s.permission.model_dump(),
    "council": _s.council.model_dump(),
    "cost": _s.cost.model_dump(),
    "voice": _s.voice.model_dump(),
    "security": _s.security.model_dump(),
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
    "fincept": {
        "terminal_binary": str(Path.home() / ".vector" / "fincept" / "FinceptTerminal.exe"),
        "alpha_vantage_key": os.environ.get("ALPHA_VANTAGE_KEY", ""),
        "fred_api_key":      os.environ.get("FRED_API_KEY", ""),
        "polygon_key":       os.environ.get("POLYGON_API_KEY", ""),
        "edgar_api_key":     os.environ.get("EDGAR_API_KEY", ""),
        "data_cache_dir":    str(Path.home() / ".vector" / "fincept" / "cache"),
    },
    "trading": {
        "llm_provider":        "openai",
        "deep_think_llm":      "gpt-5.4",
        "quick_think_llm":     "gpt-5.4-mini",
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
    "autohedge": {
        "openai_api_key":       os.environ.get("OPENAI_API_KEY", ""),
        "exa_api_key":          os.environ.get("EXA_API_KEY", ""),
        "jupiter_api_key":      os.environ.get("JUPITER_API_KEY", ""),
        "solana_private_key":   os.environ.get("SOLANA_PRIVATE_KEY", ""),
        "massive_api_key":      os.environ.get("MASSIVE_API_KEY", ""),
        "director_model":       "gpt-4.1",
        "fast_model":           "gpt-4o-mini",
        "output_dir":           str(Path.home() / ".vector" / "autohedge" / "outputs"),
        "logs_dir":             str(Path.home() / ".vector" / "autohedge" / "logs"),
        "live_trading":         False,      # set True + SOLANA_PRIVATE_KEY to enable execution
    },
    "vibe_trading": {
        "langchain_provider":  os.environ.get("LANGCHAIN_PROVIDER", "openai"),
        "langchain_model":     os.environ.get("LANGCHAIN_MODEL", "gpt-4.1"),
        "tushare_token":       os.environ.get("TUSHARE_TOKEN", ""),
        "ccxt_exchange":       os.environ.get("CCXT_EXCHANGE", "binance"),
        "token_threshold":     int(os.environ.get("TOKEN_THRESHOLD", "40000")),
        "workspace_dir":       str(Path.home() / ".vector" / "vibe_trading" / "workspace"),
        "memory_dir":          str(Path.home() / ".vector" / "vibe_trading" / "memory"),
        "runs_dir":            str(Path.home() / ".vector" / "vibe_trading" / "runs"),
        "skills_user_dir":     str(Path.home() / ".vector" / "vibe_trading" / "skills"),
        "enable_shell_tools":  False,
    },
    "ml_intern": {
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
        "sessions_dir":      str(Path.home() / ".vector" / "ml_intern" / "sessions"),
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
        "output_dir": os.environ.get("COMFYUI_OUTPUT_DIR", "C:/Users/Arghyadeep/Desktop/V.E.C.T.O.R/ComfyUI/output"),
        "timeout": 120.0,
        "poll_interval": 1.5,
    },
    "task_queue": {
        "max_concurrent": 8,
    },
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
