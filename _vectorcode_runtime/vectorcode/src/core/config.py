"""Core config shim — re-exports from vc_core.config."""
from vectorcode.src.vc_core.config import (
    VectorConfig, HardwareInfo, CONFIG,
    load_config, detect_hardware, recommend_engine, recommend_model,
    generate_default_toml, generate_minimal_toml, apply_security_profile,
    validate_config_key, estimated_download_gb,
    DEFAULT_CONFIG_DIR, DEFAULT_CONFIG_PATH,
)
