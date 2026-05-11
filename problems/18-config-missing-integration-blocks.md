# Problem 18 — CONFIG Missing Integration Blocks

**Severity: MEDIUM**
**Status: FIXED 2026-05-12 — Added HermesConfig, TursoConfig, KarpathyConfig, AirLLMConfig Pydantic sub-models to core/config.py. Exposed in CONFIG dict as hermes, turso_url, turso_token, karpathy, airllm keys. TURSO_URL/TURSO_TOKEN env vars supported.**
**Discovered: 2026-05-11 by 6-agent codebase audit**

## Symptom

Six integration modules call `CONFIG.get("X", {})` and silently get `{}`
because the corresponding config block doesn't exist. All six integrations
degrade to hardcoded fallbacks with no way to configure them via environment
variables.

## Missing Blocks

| Integration | Code location | Fallback (hardcoded) |
|-------------|--------------|----------------------|
| `hermes` | `hermes_adapter.py:33`, `integrations/hermes/hermes_adapter.py:23` | `http://127.0.0.1:8080` |
| `turso_url` | `multi_db_manager.py:253` | `None` → Turso disabled |
| `turso_token` | `multi_db_manager.py:256` | `None` → Turso disabled |
| `airllm` | `integrations/airllm/airllm_runner.py` | model path hardcoded |
| `openmythos` | `integrations/openmythos/train.py` | base model hardcoded |
| `opencli` | `integrations/opencli/tool_registry.py` | tool dir hardcoded |
| `fly` | Cloud deploy scripts | no env override |
| `cloudflare` | `api/wrangler.toml` (separate) | no python config |
| `karpathy` | `karpathy_lab/progress_tracker.py` | `./data/training_runs` |

## Fix Required

Add to `core/config.py` in the Settings model:

```python
class HermesConfig(BaseModel):
    url: str = Field(default="http://127.0.0.1:8080", env="HERMES_URL")
    acp_port: int = Field(default=8765, env="HERMES_ACP_PORT")

class TursoConfig(BaseModel):
    url: str = Field(default="", env="TURSO_URL")
    token: str = Field(default="", env="TURSO_TOKEN")

class KarpathyConfig(BaseModel):
    runs_dir: str = Field(default="./data/training_runs", env="KARPATHY_RUNS_DIR")
    datasets_dir: str = Field(default="./data/datasets", env="KARPATHY_DATASETS_DIR")

class AirLLMConfig(BaseModel):
    models_dir: str = Field(default="./models/airllm", env="AIRLLM_MODELS_DIR")
    max_gpu_memory: str = Field(default="10GB", env="AIRLLM_MAX_GPU_MEMORY")

class VectorSettings(BaseSettings):
    ...
    hermes: HermesConfig = HermesConfig()
    turso: TursoConfig = TursoConfig()
    karpathy: KarpathyConfig = KarpathyConfig()
    airllm: AirLLMConfig = AirLLMConfig()
```

And expose them in the `CONFIG` dict:

```python
CONFIG = {
    ...
    "hermes": {"url": settings.hermes.url, "acp_port": settings.hermes.acp_port},
    "turso_url": settings.turso.url,
    "turso_token": settings.turso.token,
    "karpathy": {"runs_dir": settings.karpathy.runs_dir, "datasets_dir": settings.karpathy.datasets_dir},
    "airllm": {"models_dir": settings.airllm.models_dir},
}
```

## Why Turso Specifically Matters

`multi_db_manager.py` calls `self._get_config("turso_url")` which calls
`CONFIG.get("turso_url")` → returns `None` → Turso sync permanently skipped
at runtime with no error. The 4-DB sync requirement is silently reduced to
3-DB (Supabase + SQLite + D1 only) because the config key is absent.
