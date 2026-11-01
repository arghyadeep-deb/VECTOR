"""Shared constants used across the codebase."""


__all__ = [
    "DEFAULT_LLAMACPP_URL",
    "DEFAULT_LMSTUDIO_URL",
    "DEFAULT_MAX_FILTERED_RESULTS",
    "DEFAULT_OLLAMA_URL",
]

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_LMSTUDIO_URL = "http://localhost:1234/v1"
DEFAULT_LLAMACPP_URL = "http://localhost:8080/v1"

# Cap on how many results the LLM relevance filter keeps per search-engine
# call. Must match the ``search.max_filtered_results`` entry in
# ``defaults/default_settings.json``. Used as the fallback whenever an
# engine is constructed without an explicit value (mainly programmatic
# mode) or when the LLM filter itself is unavailable and we slice the
# unfiltered previews.
DEFAULT_MAX_FILTERED_RESULTS = 20
