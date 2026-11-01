"""Enumerate every real dispatchable agent class under districts/*/ and diff
against config/agent_manifest.yaml, so governor-reachability gaps are measured
instead of guessed. Static AST parse only — never imports district code (some
districts have heavy/optional deps that would make import-based scanning
fragile and side-effecting).

A class counts as a "real agent" if either:
  - it subclasses AgentBase (by name; resolving the import isn't necessary
    since the codebase convention is consistent), or
  - it defines a `run` or `async run` method directly in its own body
    (orchestrator-style classes like OpsSwarm/QASwarm don't subclass
    AgentBase but are still governor-dispatchable).

For each such class we also heuristically flag whether `run()` appears to
branch on the task's type (looks for `task[` / `task.get(` / `.get("type"`
/ `["type"]` patterns in the run method source) vs. a stock_analyst-style
implementation that ignores its argument.
"""
import sys
import ast
import yaml
from pathlib import Path
from dataclasses import dataclass, field

ROOT = Path(__file__).resolve().parent.parent
DISTRICTS_DIR = ROOT / "districts"
MANIFEST_PATH = ROOT / "config" / "agent_manifest.yaml"
OUT_PATH = ROOT / "docs" / "manifest_gap.md"


@dataclass
class AgentClass:
    district: str
    module: str          # e.g. districts.coding.git_bot
    class_name: str
    qualified: str        # districts.coding.git_bot.GitBot
    is_agent_base_subclass: bool
    has_run_method: bool
    run_branches_on_type: bool
    init_requires_args: bool
    dispatchable: bool


def _load_manifest_class_paths(manifest_path: Path) -> set[str]:
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    registered = set()
    for district, agents in (data.get("districts") or {}).items():
        for agent in agents or []:
            cls = agent.get("class")
            if cls:
                registered.add(cls)
    return registered


def _run_method_branches_on_type(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    src = ast.dump(node)
    markers = ['"type"', "'type'"]
    return any(m in src for m in markers)


def _init_requires_args(class_node: ast.ClassDef) -> bool:
    for item in class_node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
            args = item.args
            # args.args includes 'self' as first; defaults cover the tail
            positional = args.args[1:]  # drop self
            required = len(positional) - len(args.defaults)
            has_required_kwonly = any(
                kw for kw, default in zip(args.kwonlyargs, args.kw_defaults)
                if default is None
            )
            return required > 0 or has_required_kwonly
    return False  # no explicit __init__ -> inherits, assume zero-arg safe


def _scan_file(py_file: Path, district: str) -> list[AgentClass]:
    try:
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
    except (SyntaxError, UnicodeDecodeError):
        return []

    module_rel = py_file.relative_to(ROOT).with_suffix("")
    module_dotted = ".".join(module_rel.parts)

    results = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        base_names = []
        for b in node.bases:
            if isinstance(b, ast.Name):
                base_names.append(b.id)
            elif isinstance(b, ast.Attribute):
                base_names.append(b.attr)
        is_agent_base = "AgentBase" in base_names

        run_node = None
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "run":
                run_node = item
                break
        has_run = run_node is not None
        branches = _run_method_branches_on_type(run_node) if run_node else False

        if not (is_agent_base or has_run):
            continue

        # AgentBase provides a generic fallback run(), so an AgentBase subclass
        # without its own run() is not necessarily a governor-dispatchable
        # specialist. Some of these are background daemons/helpers called by
        # cron/autonomous-loop code (for example SubconsciousLoop or
        # EmergencyResponseSystem) and should not appear as manifest gaps.
        dispatchable = has_run

        qualified = f"{module_dotted}.{node.name}"
        results.append(AgentClass(
            district=district,
            module=module_dotted,
            class_name=node.name,
            qualified=qualified,
            is_agent_base_subclass=is_agent_base,
            has_run_method=has_run,
            run_branches_on_type=branches,
            init_requires_args=_init_requires_args(node),
            dispatchable=dispatchable,
        ))
    return results


def _swarm_self_loaded_qualified_names(district_dir: Path, district: str) -> set[str]:
    """Detect the orchestrator self-loading pattern used by coding/, finance/,
    ops/, qa/, research/ (districts/<d>/agent.py defines a PYTHON_AGENTS list
    of (module_name, class_name[, role_handle]) tuples and registers each one
    directly into the shared registry from its own __init__). Those sub-agents
    are real and reachable the moment the orchestrator is manifest-registered
    — registering them AGAIN individually in the manifest would just create a
    second, always-losing (lower HP, no declared capability) dispatch path.
    Returns their fully-qualified `districts.<d>.<module>.<Class>` paths so
    the report can exclude them from "unregistered" with an accurate reason.
    """
    agent_py = district_dir / "agent.py"
    if not agent_py.exists():
        return set()
    try:
        tree = ast.parse(agent_py.read_text(encoding="utf-8"), filename=str(agent_py))
    except (SyntaxError, UnicodeDecodeError):
        return set()

    # Two conventions observed:
    #   PYTHON_AGENTS = [(bare_module_stem, ClassName, role_handle), ...]
    #     (coding/finance/qa/research) — qualify as districts.<d>.<stem>.<Class>
    #   agents_to_import = [(ClassName, "districts.ops.full.module.path", role), ...]
    #     (ops) — reversed order AND already a fully-qualified module path
    VAR_CONVENTIONS = {"PYTHON_AGENTS": "stem_first", "agents_to_import": "class_first"}
    qualified: set[str] = set()
    for node in ast.walk(tree):
        # Written either as a plain assignment or — in most districts
        # observed so far — a type-annotated one
        # (`PYTHON_AGENTS: list[tuple[str, str]] = [...]`), which parses to
        # ast.AnnAssign, not ast.Assign.
        var_name = None
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name) and t.id in VAR_CONVENTIONS]
            if not names:
                continue
            var_name, value = names[0], node.value
        elif isinstance(node, ast.AnnAssign):
            if not (isinstance(node.target, ast.Name) and node.target.id in VAR_CONVENTIONS):
                continue
            var_name, value = node.target.id, node.value
        else:
            continue
        convention = VAR_CONVENTIONS[var_name]
        if not isinstance(value, ast.List):
            continue
        for elt in value.elts:
            if not isinstance(elt, ast.Tuple) or len(elt.elts) < 2:
                continue
            a, b = elt.elts[0], elt.elts[1]
            if not (isinstance(a, ast.Constant) and isinstance(b, ast.Constant)):
                continue
            if convention == "stem_first":
                qualified.add(f"districts.{district}.{a.value}.{b.value}")
            else:  # class_first: (ClassName, full_module_path, ...)
                qualified.add(f"{b.value}.{a.value}")
    return qualified


def scan_districts() -> dict[str, list[AgentClass]]:
    by_district: dict[str, list[AgentClass]] = {}
    for district_dir in sorted(DISTRICTS_DIR.iterdir()):
        if not district_dir.is_dir() or district_dir.name.startswith("_") or district_dir.name == "__pycache__":
            continue
        district = district_dir.name
        agents = []
        # Top-level files only (district_dir/*.py, not rglob): districts/coding,
        # districts/intelligence, and districts/investment each vendor a whole
        # absorbed OSS library in a nested subpackage (vector_mlops/,
        # vector_social_sim/, vector_finagent+vector_backtest+vector_hedgebot/).
        # Those internal helper/workflow classes (Daemon, CoreAgent, WorkflowModule,
        # IndicatorFactory, ...) define `run()` for their own library's purposes,
        # not as governor-dispatchable district agents — they're already wired
        # via thin top-level adapter agents (e.g. finagent_agent.py). Recursing
        # into them produced 140 "unregistered" hits, mostly this noise; VECTOR's
        # actual convention is one file per agent directly under districts/<d>/.
        for py_file in sorted(district_dir.glob("*.py")):
            if py_file.name == "__init__.py":
                continue
            # NOTE: do NOT filter by "test" substring in the filename — qa/
            # has real, non-test district agents named test_engineer.py,
            # api_tester.py, test_results_analyzer.py that collide with that
            # naive heuristic (and even with pytest's own test_*.py discovery
            # convention). District agent files never live under a tests/
            # directory, so there's no real ambiguity to filter for here.
            agents.extend(_scan_file(py_file, district))
        by_district[district] = agents
    return by_district


def build_report(by_district: dict[str, list[AgentClass]], registered: set[str]) -> str:
    lines = [
        "# Manifest Gap Report",
        "",
        "Generated by `scripts/manifest_gap.py` — static AST scan of `districts/*/` "
        "diffed against `config/agent_manifest.yaml`. A class counts as a dispatchable "
        "agent only when it defines its own `run`/`async run` method (covers "
        "orchestrator classes like `OpsSwarm`/`QASwarm` that don't subclass "
        "`AgentBase`). AgentBase subclasses without a direct `run()` are reported as "
        "background/helper classes instead of manifest gaps.",
        "",
        "`run() branches?` is a heuristic (looks for `\"type\"`/`'type'` literals inside "
        "the run method's AST) — a hardcoded-output agent (e.g. ignores params) will "
        "show `no` and should NOT be registered as-is without a follow-up fix; it will "
        "fake-succeed once dispatched regardless of task type.",
        "",
        "`__init__ needs args?` = `yes` means `ManifestLoader.instantiate_all()`'s bare "
        "`cls()` call will fail; needs an adapter or default args before registering.",
        "",
    ]

    total_real = 0
    total_registered = 0
    total_unregistered = 0
    total_swarm_reachable = 0

    for district in sorted(by_district.keys()):
        agents = by_district[district]
        if not agents:
            continue
        dispatch_agents = [a for a in agents if a.dispatchable]
        background_helpers = [a for a in agents if not a.dispatchable]

        district_dir = DISTRICTS_DIR / district
        swarm_loaded_quals = _swarm_self_loaded_qualified_names(district_dir, district)
        orchestrator_quals = {a.qualified for a in dispatch_agents if a.module == f"districts.{district}.agent"}
        orchestrator_registered = bool(orchestrator_quals & registered)

        reg = [a for a in dispatch_agents if a.qualified in registered]
        swarm_reachable = [
            a for a in dispatch_agents
            if a.qualified not in registered
            and a.qualified in swarm_loaded_quals
            and orchestrator_registered
        ]
        unreg = [
            a for a in dispatch_agents
            if a.qualified not in registered
            and a not in swarm_reachable
        ]
        total_real += len(dispatch_agents)
        total_registered += len(reg)
        total_unregistered += len(unreg)
        total_swarm_reachable += len(swarm_reachable)

        lines.append(
            f"## {district}  ({len(reg)} registered / {len(swarm_reachable)} swarm-reachable / "
            f"{len(unreg)} unregistered / {len(dispatch_agents)} dispatchable"
            f"{f' / {len(background_helpers)} background-helper' if background_helpers else ''})"
        )
        lines.append("")
        if reg:
            lines.append("**Registered:**")
            for a in reg:
                lines.append(f"- `{a.qualified}`")
            lines.append("")
        if swarm_reachable:
            lines.append(
                f"**Swarm-reachable** (self-loaded by the registered orchestrator "
                f"`districts.{district}.agent` — not a real gap, do not register individually):"
            )
            for a in swarm_reachable:
                lines.append(f"- `{a.qualified}`")
            lines.append("")
        if unreg:
            lines.append("**Unregistered:**")
            lines.append("")
            lines.append("| Class | AgentBase? | has run()? | run() branches? | __init__ needs args? |")
            lines.append("|---|---|---|---|---|")
            for a in unreg:
                lines.append(
                    f"| `{a.qualified}` | {'yes' if a.is_agent_base_subclass else 'no'} | "
                    f"{'yes' if a.has_run_method else 'no'} | "
                    f"{'yes' if a.run_branches_on_type else 'no'} | "
                    f"{'yes' if a.init_requires_args else 'no'} |"
                )
            lines.append("")
        if background_helpers:
            lines.append("**Background/helper AgentBase subclasses** (not manifest gaps; no direct `run()`):")
            for a in background_helpers:
                lines.append(f"- `{a.qualified}`")
            lines.append("")

    lines.insert(
        6,
        f"**Totals: {total_registered} registered / {total_swarm_reachable} swarm-reachable / "
        f"{total_unregistered} unregistered / {total_real} dispatchable agent classes found.**\n",
    )

    return "\n".join(lines)


def main() -> int:
    registered = _load_manifest_class_paths(MANIFEST_PATH)
    by_district = scan_districts()
    report = build_report(by_district, registered)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(report, encoding="utf-8")

    # Re-derive the same totals build_report computed (swarm-reachable
    # sub-agents of a registered orchestrator are not a real gap).
    total_real = 0
    total_unreg = 0
    total_swarm = 0
    for district, agents in by_district.items():
        if not agents:
            continue
        district_dir = DISTRICTS_DIR / district
        swarm_loaded_quals = _swarm_self_loaded_qualified_names(district_dir, district)
        orchestrator_quals = {a.qualified for a in agents if a.module == f"districts.{district}.agent"}
        orchestrator_registered = bool(orchestrator_quals & registered)
        dispatch_agents = [a for a in agents if a.dispatchable]
        total_real += len(dispatch_agents)
        for a in agents:
            if not a.dispatchable:
                continue
            if a.qualified in registered:
                continue
            if a.qualified in swarm_loaded_quals and orchestrator_registered:
                total_swarm += 1
            else:
                total_unreg += 1

    print(f"Scanned {total_real} real agent classes across {len(by_district)} districts.")
    print(f"Swarm-reachable (not a real gap): {total_swarm}")
    print(f"Unregistered: {total_unreg}")
    print(f"Report written to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
