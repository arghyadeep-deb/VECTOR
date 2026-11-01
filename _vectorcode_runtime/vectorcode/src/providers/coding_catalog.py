"""Coding-only provider definitions that must never join the autonomous provider pools.

FreeLLMAPI is a local gateway that forwards to cloud providers: a loopback URL does not make the
payload local, its upstream cost is not guaranteed free, and it is reachable only by explicit
``freellmapi/<model>`` selection with the user's own credential.
"""

import ipaddress
from urllib.parse import urlsplit

from core.inference.llm_providers import LLMProvider, get_provider

FREELLMAPI = "freellmapi"
FREELLMAPI_KEY_ENV = "FREELLMAPI_API_KEY"
ROUTER_MODELS = ["auto:fast", "auto", "auto:smart", "auto:balanced", "auto:reliable"]
# auto:fast leads (and is the default_model below) because live FreeLLMAPI
# analytics on 2026-10-30 showed the plain "auto" router averaging 6.1s
# latency / 18.7s P95 / 12.5s time-to-first-token across its provider pool --
# too slow for interactive coding use. auto:fast trades some of that pool's
# "smartest" picks for ones that respond quickly; still fully overridable via
# an explicit `/model freellmapi/<router-or-exact-id>` selection.
DISCOVERY_TIMEOUT_SEC = 5.0
_MAX_DISCOVERY_BYTES = 2_000_000
_MAX_DISCOVERED_MODELS = 500


def normalize_freellmapi_url(raw: str) -> str:
    """Return a validated endpoint ending in /v1 exactly once; errors never echo the input."""
    value = str(raw or "").strip()
    invalid = ValueError(
        "FreeLLMAPI endpoint is invalid: use http(s)://host[:port] without credentials, query or fragment; "
        "plain http is allowed only for loopback."
    )
    try:
        parts = urlsplit(value)
        port = parts.port
        host = parts.hostname
    except ValueError:
        raise invalid from None
    if parts.scheme not in {"http", "https"} or not host or parts.query or parts.fragment:
        raise invalid
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise invalid
    if port is not None and not 1 <= port <= 65535:
        raise invalid
    if parts.scheme == "http":
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == "localhost"
        if not loopback:
            raise invalid
    path = parts.path.rstrip("/")
    if not path.endswith("/v1"):
        path += "/v1"
    return f"{parts.scheme}://{parts.netloc}{path}"


def _freellmapi_url() -> str:
    from core.config import CONFIG

    return normalize_freellmapi_url(CONFIG["vectorcode"]["freellmapi_base_url"])


def get_coding_provider(slug: str) -> LLMProvider | None:
    """Existing providers unchanged; FreeLLMAPI built from configuration on each call."""
    if slug != FREELLMAPI:
        return get_provider(slug)
    return LLMProvider(
        slug=FREELLMAPI,
        name="FreeLLMAPI (local gateway to cloud)",
        base_url=_freellmapi_url(),
        api_key_env=FREELLMAPI_KEY_ENV,
        driver="openai_compat",
        default_model=ROUTER_MODELS[0],
        models=list(ROUTER_MODELS),
        free=False,
        notes="Explicit selection only; forwards to third-party clouds, availability and cost not guaranteed.",
    )


def freellmapi_models(api_key: str | None) -> list[str]:
    """Router choices, plus connected endpoints when a key lets us ask the gateway (one bounded call)."""
    models = list(ROUTER_MODELS)
    if not api_key:
        return models
    import httpx

    from core.inference.provider_client import ProviderClient

    failed = RuntimeError("FreeLLMAPI model discovery failed; check the gateway is running and the key is valid.")
    try:
        url = _freellmapi_url() + "/models"
        ProviderClient()._ssrf_check(url)
        with httpx.Client(timeout=DISCOVERY_TIMEOUT_SEC) as client:
            response = client.get(url, params={"available": "true"}, headers={"Authorization": f"Bearer {api_key}"})
        if response.status_code != 200 or len(response.content) > _MAX_DISCOVERY_BYTES:
            raise failed
        data = response.json().get("data")
        if not isinstance(data, list):
            raise failed
    except Exception:
        raise failed from None
    for item in data:
        model_id = item.get("id") if isinstance(item, dict) else None
        if isinstance(model_id, str) and model_id.strip() and model_id not in models:
            models.append(model_id)
        if len(models) >= _MAX_DISCOVERED_MODELS:
            break
    return models
