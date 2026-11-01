"""Model metadata — registry of model capabilities and pricing."""

from typing import Optional

MODELS: dict[str, dict] = {
    "anthropic/claude-sonnet-4-6":   {"context": 200000, "pricing": {"in": 0.003, "out": 0.015}, "provider": "anthropic"},
    "anthropic/claude-opus-4-5":     {"context": 200000, "pricing": {"in": 0.015, "out": 0.075}, "provider": "anthropic"},
    "anthropic/claude-haiku-4-5":    {"context": 200000, "pricing": {"in": 0.00025, "out": 0.00125}, "provider": "anthropic"},
    "openai/gpt-4o":                 {"context": 128000, "pricing": {"in": 0.005, "out": 0.015}, "provider": "openai"},
    "openai/gpt-4o-mini":            {"context": 128000, "pricing": {"in": 0.00015, "out": 0.0006}, "provider": "openai"},
    "google/gemini-2.5-pro":        {"context": 1000000, "pricing": {"in": 0.00125, "out": 0.005}, "provider": "google"},
    "google/gemini-2.5-flash":      {"context": 1000000, "pricing": {"in": 0.00025, "out": 0.001}, "provider": "google"},
    "groq/llama-3.3-70b-versatile": {"context": 128000, "pricing": {"in": 0.00059, "out": 0.00079}, "provider": "groq"},
    "mistral/mistral-large-latest": {"context": 128000, "pricing": {"in": 0.004, "out": 0.012}, "provider": "mistral"},
    "deepseek/deepseek-chat":       {"context": 64000, "pricing": {"in": 0.00027, "out": 0.0011}, "provider": "deepseek"},
    "ollama/llama3.2":              {"context": 128000, "pricing": {"in": 0.0, "out": 0.0}, "provider": "ollama"},
}


def get_model_info(model_id: str) -> Optional[dict]:
    return MODELS.get(model_id)


def get_context_length(model_id: str) -> int:
    info = MODELS.get(model_id, {})
    return info.get("context", 128000)


def get_pricing(model_id: str) -> dict:
    info = MODELS.get(model_id, {})
    return info.get("pricing", {"in": 0.0, "out": 0.0})


def estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    pricing = get_pricing(model_id)
    return (input_tokens * pricing["in"] + output_tokens * pricing["out"]) / 1000
