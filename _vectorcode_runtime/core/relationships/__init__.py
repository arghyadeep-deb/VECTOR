"""Shared relationship-data persistence helpers."""

from core.relationships.schema import get_connection, init_schema

__all__ = ["get_connection", "init_schema"]


if __name__ == "__main__":
    from core.runtime_paths import data_path

    init_schema(data_path("contacts.db"))
