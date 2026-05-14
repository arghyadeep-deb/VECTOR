# Ported from GitHub/ruvnet_ruflo/repo/v2/ SPARC methodology
"""SPARC methodology — Specification, Pseudocode, Architecture, Refinement, Completion."""
from vectorcode.skills.builtin.sparc.coordinator import (
    run_sparc_full,
    run_sparc_stage,
    sparc_slash_command,
    SPARC_STAGES,
)

__all__ = ["run_sparc_full", "run_sparc_stage", "sparc_slash_command", "SPARC_STAGES"]
