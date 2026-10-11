"""Lightweight agent-manifest inventory without importing agent runtimes."""

from __future__ import annotations

from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _manifest_path(path: str | Path | None = None) -> Path:
    return Path(path) if path else REPO_ROOT / "config" / "agent_manifest.yaml"


def summarize_agents(agents: list[dict], district_names: tuple[str, ...] = ()) -> dict:
    """Summarize manifest entries using only scalar metadata."""
    names = [str(agent.get("name", "")).strip() for agent in agents]
    district_counts = Counter(str(agent.get("district", "")).strip() for agent in agents)
    districts = tuple(sorted(district_names or district_counts.keys()))
    duplicate_names = sorted(
        name for name, count in Counter(names).items() if name and count > 1
    )
    return {
        "agent_count": len(agents),
        "district_count": len(districts),
        "districts": list(districts),
        "empty_districts": [district for district in districts if not district_counts[district]],
        "duplicate_agent_names": duplicate_names,
        "district_agent_counts": {
            district: district_counts[district] for district in districts
        },
    }


def load_manifest_inventory(path: str | Path | None = None) -> dict:
    """Load only YAML metadata needed for readiness reporting."""
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("PyYAML is required: pip install pyyaml") from exc

    manifest_path = _manifest_path(path)
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("districts"), dict):
        raise ValueError(f"Malformed agent manifest: {manifest_path}")

    agents: list[dict] = []
    for district_name, district_agents in raw["districts"].items():
        if not isinstance(district_agents, list):
            raise ValueError(f"District {district_name!r} must be a list")
        for entry in district_agents:
            if not isinstance(entry, dict):
                raise ValueError(f"District {district_name!r} contains a non-mapping entry")
            agent = dict(entry)
            agent.setdefault("district", district_name)
            agents.append(agent)

    return summarize_agents(agents, district_names=tuple(sorted(raw["districts"].keys())))


if __name__ == "__main__":
    print(load_manifest_inventory())
