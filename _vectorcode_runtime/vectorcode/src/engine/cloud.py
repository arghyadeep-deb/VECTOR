"""Re-export from the real vc_engine implementation."""
try:
    from vectorcode.src.vc_engine.cloud import CloudEngine, PRICING as CLOUD_PRICING
    # CLOUD_MODELS exposed as legacy alias
    try:
        from vectorcode.src.vc_engine.cloud import _OPENAI_MODELS as _OM
        CLOUD_MODELS: list = list(_OM)
    except ImportError:
        CLOUD_MODELS = []
except ImportError as _cloud_import_error:
    _CLOUD_IMPORT_ERROR = _cloud_import_error
    CLOUD_MODELS = []
    CLOUD_PRICING = {}

    class CloudEngine:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Cloud engine dependencies are unavailable") from _CLOUD_IMPORT_ERROR

        def generate(self, msgs, **kw):
            raise RuntimeError("Cloud engine dependencies are unavailable") from _CLOUD_IMPORT_ERROR

__all__ = ["CloudEngine", "CLOUD_MODELS", "CLOUD_PRICING"]
