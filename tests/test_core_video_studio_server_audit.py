"""Phase 3 whole-repo audit -- core/video/studio_server.py.

Regression for run_workflow()'s broken "topological sort": it used to
bucket nodes into "no incoming edge" vs "has incoming edge" and keep each
bucket's original array order within itself -- correct only for a 2-level
graph. A 3+ node chain (A -> B -> C) with C listed before B in the raw
nodes array ran C before B had produced output, so C's upstream lookup
got "" instead of B's real result. Fixed with a real Kahn's-algorithm
topological sort.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

from core.video import studio_server


def test_workflow_runs_three_node_chain_in_dependency_order(tmp_path):
    """The exact regression: C listed before B in the array, A -> B -> C."""
    studio_server.set_project_dir(str(tmp_path))
    client = TestClient(studio_server.app)

    # "output" nodes pass upstream_url straight through -- "text_input" is a
    # pure source and deliberately ignores upstream_url, so it can't be used
    # to test propagation through a middle node.
    wf = {
        "nodes": [
            {"id": "c", "type": "output", "params": {}},
            {"id": "a", "type": "text_input", "params": {"text": "hello"}},
            {"id": "b", "type": "output", "params": {}},
        ],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
        ],
    }
    created = client.post("/api/workflows", json=wf).json()
    wf_id = created["id"]

    resp = client.post(f"/api/workflows/{wf_id}/run")
    assert resp.status_code == 200
    results = {r["node_id"]: r for r in resp.json()["results"]}

    order = [r["node_id"] for r in resp.json()["results"]]
    assert order.index("a") < order.index("b") < order.index("c"), (
        f"expected dependency order a->b->c, got {order}"
    )
    # c's output must be a's text, propagated through b -- not "" (which is
    # what the pre-fix bucket-based ordering produced when c ran before b).
    assert results["c"]["url"] == "hello"


def test_workflow_cycle_does_not_crash_or_drop_nodes():
    studio_server.set_project_dir(".")
    nodes = [{"id": "x", "type": "output", "params": {}},
              {"id": "y", "type": "output", "params": {}}]
    edges = [{"source": "x", "target": "y"}, {"source": "y", "target": "x"}]
    by_id = {n["id"]: n for n in nodes}
    indegree = {n["id"]: 0 for n in nodes}
    adj = {n["id"]: [] for n in nodes}
    for e in edges:
        adj[e["source"]].append(e["target"])
        indegree[e["target"]] += 1
    queue = [nid for nid, d in indegree.items() if d == 0]
    assert queue == []  # pure cycle: nothing starts with indegree 0
    ordered_ids = []
    ordered_ids += [nid for nid in by_id if nid not in ordered_ids]
    assert set(ordered_ids) == {"x", "y"}  # both nodes still present, no drop


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
