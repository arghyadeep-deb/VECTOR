"""VECTOR collections engine — a PocketBase-style dynamic data layer in Python.

Absorbed (reimplemented, not copied) from pocketbase-master (Go BaaS). Provides the
capabilities VECTOR lacked: dynamic collections/schema, generic validated CRUD with a
safe filter language, versioned migrations, pluggable file storage, JWT+RBAC auth, and
per-collection CRUD hooks. Built on VECTOR's existing encrypted SQLite connection.
"""

from core.collections.fields import Field, FieldType, ValidationError, build_field
from core.collections.schema import Collection, CollectionType, RESERVED_NAMES
from core.collections.store import (
    CollectionStore,
    CollectionEngine,
    FilterError,
    parse_filter,
    parse_sort,
)
from core.collections.migrations import MigrationRunner, Migration, migration, get_runner
from core.collections.storage import FileStorage, LocalDriver, S3Driver, StorageError, safe_key
from core.collections.auth import AuthService, JWTManager, RuleEngine, PasswordHasher, AuthError
from core.collections.hooks import CollectionHooks, HookContext, HookCancelled, get_hooks

__all__ = [
    # data layer
    "Field",
    "FieldType",
    "ValidationError",
    "build_field",
    "Collection",
    "CollectionType",
    "RESERVED_NAMES",
    "CollectionStore",
    "CollectionEngine",
    "FilterError",
    "parse_filter",
    "parse_sort",
    # migrations
    "MigrationRunner",
    "Migration",
    "migration",
    "get_runner",
    # storage
    "FileStorage",
    "LocalDriver",
    "S3Driver",
    "StorageError",
    "safe_key",
    # auth
    "AuthService",
    "JWTManager",
    "RuleEngine",
    "PasswordHasher",
    "AuthError",
    # hooks
    "CollectionHooks",
    "HookContext",
    "HookCancelled",
    "get_hooks",
]
