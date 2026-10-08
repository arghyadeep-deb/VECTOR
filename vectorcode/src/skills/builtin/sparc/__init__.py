# Ported from GitHub/vectorcode_vector/repo/v2/ SPARC methodology
"""SPARC methodology -- Specification, Pseudocode, Architecture, Refinement, Completion."""
from vectorcode.src.skills.builtin.sparc.coordinator import (
    run_sparc_full,
    run_sparc_stage,
    sparc_slash_command,
    SPARC_STAGES,
)

__all__ = ["run_sparc_full", "run_sparc_stage", "sparc_slash_command", "SPARC_STAGES"]
