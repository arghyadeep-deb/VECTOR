__version__ = "1.0.0"

from importlib import import_module

from .bootstrap import ensure_paths

ensure_paths()

_LAZY_EXPORTS = {
    name: module
    for module, names in {
        "sdk": ("VectorAgent", "Vector", "VectorSystem", "MemoryHandle", "SystemBuilder"),
        "claims": (
            "ClaimService", "WorkStealingService", "LoadBalancer",
            "mcp_claim_task", "mcp_release_task", "mcp_steal_task",
        ),
        "guidance": ("create_guidance_system", "ThreatDetector", "CoherenceScheduler", "AuthorityGate", "ContinueGate"),
        "neural_training": ("VECTORTrainer", "A2C", "DQN", "CuriosityModule", "DecisionTransformer"),
    }.items()
    for name in names
}

__all__ = tuple(_LAZY_EXPORTS)


def __getattr__(name):
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"{__name__}.{module_name}"), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


if __name__ == "__main__":
    assert callable(ensure_paths)
    assert "VECTORTrainer" in __dir__()

