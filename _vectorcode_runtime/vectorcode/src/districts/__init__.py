"""Shim package — the real VECTOR districts live at the top-level `districts/` package.

This module exists so that `import vectorcode.src.districts` does not raise
ModuleNotFoundError. Code that needs actual district classes should import
directly from `districts.<district_name>`.
"""
