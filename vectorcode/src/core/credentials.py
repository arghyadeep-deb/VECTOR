"""Core credentials shim."""
from typing import Any, Dict
TOOL_CREDENTIALS: Dict[str, Any] = {}

def get_credential(name: str) -> Any:
    return TOOL_CREDENTIALS.get(name)

def set_credential(name: str, value: Any) -> None:
    TOOL_CREDENTIALS[name] = value
def get_credential_status(name: str) -> str:
    return "unknown"

