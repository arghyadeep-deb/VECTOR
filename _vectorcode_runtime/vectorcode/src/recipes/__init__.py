# VECTOR module — ported from VectorCode
# Personalized for VECTOR runtime.
# Owner: Arghyadeep Deb
# Ingested: 2026-05-15T02:57:36+00:00

"""Recipe system — composable primitive configurations."""

from vectorcode.src.recipes.composer import (
    recipe_to_eval_suite,
    recipe_to_operator,
)
from vectorcode.src.recipes.loader import (
    Recipe,
    discover_recipes,
    load_recipe,
    resolve_recipe,
)

__all__ = [
    "Recipe",
    "discover_recipes",
    "load_recipe",
    "recipe_to_eval_suite",
    "recipe_to_operator",
    "resolve_recipe",
]
