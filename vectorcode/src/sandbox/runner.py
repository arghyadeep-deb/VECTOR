"""Compatibility-only delegate to ``core.sandbox``; no independent guarantees."""

from core.sandbox.runner import ContainerRunner, logger

__all__ = ["ContainerRunner", "logger"]
