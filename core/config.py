import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

import os
from loguru import logger

CONFIG = {
    "owner_name": "Arghyadeep",
    "system_name": "VECTOR",
    "version": "1.0.0",
    "env": os.getenv("VECTOR_ENV", "development"),
    "debug": os.getenv("VECTOR_DEBUG", "true").lower() == "true",
    "vault_path": Path(os.getenv("VECTOR_VAULT_PATH", "C:/Users/Arghyadeep/V.E.C.T.O.R Brain")),
    "db_path": Path(__file__).parent.parent / "vector_memory.db",
    "ollama_host": os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
    "models": {
        "ambient": "vector-ambient",
        "focus": "vector-focus",
        "multilingual": "vector-multilingual",
        "reasoning": "vector-reasoning",
        "coder": "vector-coder",
        "deep": "vector-deep",
        "chairman": "vector-chairman",
        "embed": "nomic-embed-text",
        "cloud_coder": "glm-5.1:cloud",
        "cloud_orchestrator": "kimi-k2.6:cloud",
    },
    "model_router": {
        "conversation": "focus",
        "multilingual": "multilingual",
        "coding": "coder",
        "council": "reasoning",
        "deep_analysis": "deep",
        "private": "chairman",
        "embedding": "embed",
        "ambient_classify": "ambient",
        "saas_build": "cloud_coder",
        "orchestration": "cloud_orchestrator",
    },
    "api_keys": {
        "anthropic_key": os.getenv("ANTHROPIC_KEY", ""),
        "gemini_key": os.getenv("GEMINI_KEY", ""),
        "github_token": os.getenv("GITHUB_TOKEN", ""),
        "github_username": os.getenv("GITHUB_USERNAME", "ArghyadeepDeb"),
        "pushover_token": os.getenv("PUSHOVER_TOKEN", ""),
        "pushover_user": os.getenv("PUSHOVER_USER", ""),
        "supabase_url": os.getenv("SUPABASE_URL", ""),
        "supabase_key": os.getenv("SUPABASE_KEY", ""),
        "virustotal_key": os.getenv("VIRUSTOTAL_KEY", ""),
        "newsapi_key": os.getenv("NEWSAPI_KEY", ""),
        "stripe_key": os.getenv("STRIPE_KEY", ""),
    },
    "loop": {
        "observe_interval_sec": 0.5,
        "db_sync_hours": 48,
        "reflect_hour": 2,
        "reflect_minute": 0,
    },
    "permission": {
        "green": ["read_calendar", "play_music", "set_timer", "search_web", "take_screenshot", "check_weather", "check_attendance"],
        "yellow": ["send_message_routine", "create_calendar_event", "commit_code", "download_file", "set_reminder"],
        "red": ["send_email", "delete_files", "execute_code", "financial_transaction", "push_github", "deploy_production"],
    },
    "council": {"max_per_week": 10, "hp_gate": 700, "cost_inr": 1.60},
    "cost": {"monthly_budget_inr": 500, "alert_inr": 400},
    "voice": {
        "whisper_model": "base",
        "kokoro_model_dir": "./models/kokoro",
        "kokoro_speed": 0.85,
        "wake_threshold": 0.5,
        "record_duration_sec": 5.0,
        "sample_rate": 16000,
        "wake_phrase": "hey_jarvis",   # placeholder until "Hey VECTOR" custom model trained
    },
    "security": {
        "suspicious_ports": [4444, 6666, 1337, 31337, 9001, 9050],
        "suspicious_process_names": [
            "cryptominer", "keylogger", "miner", "rat", "netcat",
            "mimikatz", "cobaltstrike", "metasploit", "ncrack",
            "xmrig", "monero", "cpuminer",
        ],
        "entropy_threshold": 7.5,
    },
    "control": {
        "adb_path": "adb",
        "phone_device_id": None,
    },
    "sensing": {
        "lgbm_model_path": "./models/malware_lgbm.txt",
        "known_faces_dir": "./data/known_faces",
        "camera_index": 0,
        "screen_ocr_enabled": True,
        "fatigue_check_interval_sec": 30,
    },
    "coding": {
        # github_token also lives in api_keys.github_token — mirrored here for district-local access
        "github_token": os.getenv("GITHUB_TOKEN", ""),
        "repo_path": str(Path(__file__).parent.parent),  # project root
    },
}

def get(key, default=None):
    """Retrieve value from CONFIG dictionary with fallback."""
    return CONFIG.get(key, default)

def print_status():
    """Log system status information."""
    logger.info(f"Owner: {CONFIG['owner_name']}")
    logger.info(f"Environment: {CONFIG['env']}")
    logger.info(f"Ollama Host: {CONFIG['ollama_host']}")
    
    non_empty_api_keys = sum(1 for v in CONFIG["api_keys"].values() if v)
    logger.info(f"Non-empty API keys: {non_empty_api_keys}")

if __name__ == "__main__":
    print_status()
    print("???: config.py OK")

