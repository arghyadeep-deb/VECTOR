"""Compatibility shim; ``vectorcode.src.vc_security`` is canonical."""

from vectorcode.src.vc_security.file_utils import secure_create, secure_mkdir

__all__ = ["secure_create", "secure_mkdir"]
