"""Security utilities for VECTOR Research Engine."""

from .data_sanitizer import (
    DataSanitizer,
    filter_research_metadata,
    redact_data,
    sanitize_data,
    strip_settings_snapshot,
)
from .file_integrity import FileIntegrityManager, FAISSIndexVerifier
from .notification_validator import (
    NotificationURLValidator,
    NotificationURLValidationError,
)
from .safe_requests import safe_get, safe_post, SafeSession
from .security_headers import SecurityHeaders
from .ssrf_validator import validate_url, get_safe_url, is_ip_blocked
from .url_validator import URLValidator
from .password_validator import PasswordValidator
from .log_sanitizer import sanitize_for_log, strip_control_chars
from .filename_sanitizer import sanitize_filename, UnsafeFilenameError
from .module_whitelist import (
    get_safe_module_class,
    ModuleNotAllowedError,
    ALLOWED_MODULES,
)

# security_settings (and account_lockout, which depends on it) transitively
# import core.research_engine.settings -> ...web.models.settings, a package
# that does not exist in this checkout (pre-existing absorption gap, not
# something this guard fixes) — conditional import, same convention as
# PathValidator/FileUploadValidator below, so the rest of this lightweight,
# load-bearing security package (ssrf_validator, safe_requests, etc.) isn't
# taken down by an unrelated missing module.
try:
    from .security_settings import get_security_default

    _has_security_settings = True
except ImportError:
    get_security_default = None  # type: ignore
    _has_security_settings = False

try:
    from .account_lockout import AccountLockoutManager, get_account_lockout_manager

    _has_account_lockout = True
except ImportError:
    AccountLockoutManager = None  # type: ignore
    get_account_lockout_manager = None  # type: ignore
    _has_account_lockout = False

# PathValidator requires werkzeug (Flask dependency), import conditionally
try:
    from .path_validator import PathValidator

    _has_path_validator = True
except ImportError:
    PathValidator = None  # type: ignore
    _has_path_validator = False

# FileUploadValidator requires pdfplumber, import conditionally
try:
    from .file_upload_validator import FileUploadValidator

    _has_file_upload_validator = True
except ImportError:
    FileUploadValidator = None  # type: ignore
    _has_file_upload_validator = False

__all__ = [
    "PathValidator",
    "DataSanitizer",
    "sanitize_data",
    "redact_data",
    "filter_research_metadata",
    "strip_settings_snapshot",
    "get_security_default",
    "FileIntegrityManager",
    "FAISSIndexVerifier",
    "FileUploadValidator",
    "NotificationURLValidator",
    "NotificationURLValidationError",
    "SecurityHeaders",
    "URLValidator",
    "safe_get",
    "safe_post",
    "SafeSession",
    "validate_url",
    "get_safe_url",
    "is_ip_blocked",
    "get_safe_module_class",
    "ModuleNotAllowedError",
    "ALLOWED_MODULES",
    "AccountLockoutManager",
    "get_account_lockout_manager",
    "PasswordValidator",
    "sanitize_for_log",
    "strip_control_chars",
    "sanitize_filename",
    "UnsafeFilenameError",
]
