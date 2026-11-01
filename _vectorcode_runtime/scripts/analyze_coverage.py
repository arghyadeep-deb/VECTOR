"""Analyze coverage.json and print missing lines for hot-path modules."""
import json
import os

with open("coverage.json", encoding="utf-8") as coverage_file:
    data = json.load(coverage_file)
targets = ["decision_engine.py", "permission_gateway.py", "loop_state.py",
           "policy.py", "semantic.py", "agent_base.py", "agent_registry.py",
           "governor.py", "wiring.py", "episodic.py"]

total_stmts = 0
total_covered = 0

for path, info in sorted(data["files"].items()):
    fname = os.path.basename(path)
    if fname in targets:
        s = info["summary"]
        pct = 100 * s["covered_lines"] / s["num_statements"] if s["num_statements"] else 0
        miss = info.get("missing_lines", [])[:25]
        total_stmts += s["num_statements"]
        total_covered += s["covered_lines"]
        print(f"{path}")
        print(f"  {s['num_statements']} stmts, {s['covered_lines']} covered, {pct:.1f}%")
        print(f"  missing first 25 lines: {miss}")
        print()

subtotal_pct = 100 * total_covered / total_stmts if total_stmts else 0.0
print(f"SUBTOTAL: {total_stmts} stmts, {total_covered} covered, {subtotal_pct:.1f}%")
