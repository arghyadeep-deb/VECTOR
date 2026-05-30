"""Re-export from the real vc_engine implementation."""
try:
    from vectorcode.src.vc_engine.cloud import CloudEngine, PRICING as CLOUD_PRICING
    # CLOUD_MODELS exposed as legacy alias
    try:
        from vectorcode.src.vc_engine.cloud import _OPENAI_MODELS as _OM
        CLOUD_MODELS: list = list(_OM)
    except Exception:
        CLOUD_MODELS = []
except Exception:
    CLOUD_MODELS = []
    CLOUD_PRICING = {}

    class CloudEngine:  # type: ignore[no-redef]
        def generate(self, msgs, **kw):
            return {}

__all__ = ["CloudEngine", "CLOUD_MODELS", "CLOUD_PRICING"]
