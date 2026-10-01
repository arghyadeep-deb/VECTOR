"""VECTOR Sandbox — subprocess execution with a timeout, output cap, and a
scrubbed environment. NOT real OS-level isolation on win32 -- see
VectorSandbox's class docstring (core/sandbox/vector_sandbox.py) for the
live execute_code wiring this affects. core/sandbox/runner.py's
ContainerRunner is the real (Docker network=none + read-only mounts)
sandbox in this package, when a container runtime is available."""
from core.sandbox.vector_sandbox import VectorSandbox, SandboxResult, SandboxConfig, get_sandbox
__all__ = ["VectorSandbox", "SandboxResult", "SandboxConfig", "get_sandbox"]
