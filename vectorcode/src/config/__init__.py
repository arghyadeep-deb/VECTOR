"""VectorCode config package — environment detection and configuration utilities."""
from .env_detector import Environment, EnvInfo, detect, get_env

__all__ = ["Environment", "EnvInfo", "detect", "get_env"]
