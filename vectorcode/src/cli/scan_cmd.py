"""CLI shim for scan_cmd."""

from loguru import logger
try:
    from vectorcode.src.vector_cli.scan_cmd import *
except ImportError:
    # The real PrivacyScanner (with its run_all() method, used by
    # server/routes.py's /v1/security/scan endpoint) comes from the
    # wildcard import above. A fallback stub here previously redefined
    # PrivacyScanner unconditionally -- even when the import succeeded --
    # with a scan(path) method the real class doesn't have and without
    # run_all(), so every call to that endpoint crashed with
    # AttributeError. Do not reintroduce a stub class below this point.
    logger.opt(exception=True).debug("[VECTOR] suppressed exception")

