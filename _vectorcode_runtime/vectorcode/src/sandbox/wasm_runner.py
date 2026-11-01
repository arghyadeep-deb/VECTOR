"""Compatibility-only delegate to ``core.sandbox``; no independent guarantees."""

from core.sandbox.wasm_runner import WasmResult, WasmRunner, create_sandbox_runner

__all__ = ["WasmResult", "WasmRunner", "create_sandbox_runner"]
