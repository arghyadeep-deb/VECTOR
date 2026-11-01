"""
Alpha Zoo — 452 quantitative factor definitions from Vibe-Trading.
Use AlphaZooLoader to discover and load factors.
"""

from pathlib import Path

from vectorcode.src.bootstrap import ensure_paths
ensure_paths()


ALPHA_ZOO_DIR = Path(__file__).parent

class AlphaZooLoader:
    """Loads and catalogs all alpha factors from the zoo."""

    def list_factors(self) -> list[str]:
        """Return list of all available factor names."""
        factors = []
        for f in ALPHA_ZOO_DIR.rglob("*.py"):
            if f.name != "__init__.py":
                factors.append(f.stem)
        return sorted(factors)

    def load_factor(self, name: str):
        """Dynamically load a factor by name."""
        import importlib.util
        for f in ALPHA_ZOO_DIR.rglob(f"{name}.py"):
            spec = importlib.util.spec_from_file_location(name, f)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        raise FileNotFoundError(f"Factor not found: {name}")

if __name__ == "__main__":
    loader = AlphaZooLoader()
    factors = loader.list_factors()
    print(f"✅ alpha_zoo OK: {len(factors)} factors")
