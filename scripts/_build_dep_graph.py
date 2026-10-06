"""Build Python import dependency graph for core/ and districts/ using AST analysis."""
import ast
from pathlib import Path
from collections import defaultdict


from loguru import logger

SCAN_DIRS = ["core", "districts"]
EXCLUDE_DIRS = {"__pycache__", ".git", "node_modules", "venv"}
BASE = Path.cwd()

MODULE_INDEX: dict[str, Path] = {}


def _build_module_index(py_files: list[Path]) -> None:
    MODULE_INDEX.clear()
    for pyf in py_files:
        mod = _module_path(pyf)
        MODULE_INDEX[mod] = pyf


def _module_path(file_path: Path) -> str:
    rel = file_path.relative_to(BASE)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].replace(".py", "")
    return ".".join(parts)


def _resolve_module(mod_name: str) -> str | None:
    if mod_name in MODULE_INDEX:
        return mod_name
    init_mod = f"{mod_name}.__init__"
    if init_mod in MODULE_INDEX:
        return mod_name
    return None


def find_py_files() -> list[Path]:
    files: list[Path] = []
    for d in SCAN_DIRS:
        target = BASE / d
        if not target.exists():
            continue
        for pyf in target.rglob("*.py"):
            if any(x in EXCLUDE_DIRS for x in pyf.parts):
                continue
            files.append(pyf)
    return sorted(files)


def extract_imports(source: str, module_name: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    deps: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                top_mod = top.split(".")[0]
                if top_mod in ("districts", "core"):
                    deps.add(alias.name)
                else:
                    deps.add(top)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                module_file = MODULE_INDEX.get(module_name)
                module_parts = module_name.split(".")
                package_parts = module_parts if module_file and module_file.name == "__init__.py" else module_parts[:-1]
                levels_up = node.level - 1
                if levels_up > len(package_parts):
                    continue
                base = ".".join(package_parts[:len(package_parts) - levels_up])
                resolved = f"{base}.{node.module}" if node.module and base else (node.module or base)
            else:
                resolved = node.module or ""
            if resolved:
                added_child = False
                for alias in node.names:
                    child = f"{resolved}.{alias.name}"
                    if alias.name != "*" and _resolve_module(child):
                        deps.add(child)
                        added_child = True
                if not added_child:
                    deps.add(resolved)
    return deps


def build_graph(py_files: list[Path]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    _build_module_index(py_files)
    outgoing: dict[str, set[str]] = {}
    incoming: dict[str, set[str]] = defaultdict(set)

    for pyf in py_files:
        mod = _module_path(pyf)
        source = pyf.read_text(encoding="utf-8", errors="replace")
        imps = extract_imports(source, mod)
        outgoing[mod] = set()
        for imp in imps:
            resolved = _resolve_module(imp)
            if resolved and resolved != mod:
                outgoing[mod].add(resolved)
                incoming[resolved].add(mod)

    return outgoing, dict(incoming)


def find_sccs(graph: dict[str, set[str]]) -> list[set[str]]:
    index_counter = [0]
    index_map: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    sccs: list[set[str]] = []

    def strongconnect(v: str):
        index_map[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True

        for w in graph.get(v, set()):
            if w not in index_map:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif on_stack.get(w, False):
                lowlink[v] = min(lowlink[v], index_map[w])

        if lowlink[v] == index_map[v]:
            scc: set[str] = set()
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.add(w)
                if w == v:
                    break
            if len(scc) > 1 or (v in graph.get(v, set())):
                sccs.append(scc)

    for v in list(graph.keys()):
        if v not in index_map:
            strongconnect(v)

    return sccs


def find_orphans(graph: dict[str, set[str]], incoming: dict[str, set[str]]) -> list[str]:
    orphans: list[str] = []
    for mod in graph:
        package = mod.split(".")[0] if "." in mod else mod
        external = [src for src in incoming.get(mod, set()) if not src.startswith(package)]
        if not external:
            orphans.append(mod)
    return orphans


def write_report(graph: dict[str, set[str]], sccs: list[set[str]], orphans: list[str], output_path: Path):
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  VECTOR Import Dependency Graph Report")
    lines.append("=" * 60)
    lines.append(f"Total modules: {len(graph)}")
    lines.append("")

    if sccs:
        lines.append("-" * 60)
        lines.append(f"  Circular Import Chains ({len(sccs)} found)")
        lines.append("-" * 60)
        for i, scc in enumerate(sccs, 1):
            lines.append(f"\n  Cycle #{i}:")
            for mod in sorted(scc):
                deps = graph.get(mod, set()) & scc
                if deps:
                    lines.append(f"    {mod} -> {', '.join(sorted(deps))}")
                else:
                    lines.append(f"    {mod}")
    else:
        lines.append("  No circular imports detected.")

    lines.append("")
    if orphans:
        lines.append("-" * 60)
        lines.append(f"  Orphan Modules ({len(orphans)} found)")
        lines.append("-" * 60)
        for mod in sorted(orphans):
            lines.append(f"    {mod}")
    else:
        lines.append("  No orphan modules detected.")

    lines.append("")
    lines.append("-" * 60)
    lines.append("  Full Dependency Graph")
    lines.append("-" * 60)
    for mod in sorted(graph):
        deps = graph[mod]
        if deps:
            lines.append(f"  {mod} -> {', '.join(sorted(deps))}")
        else:
            lines.append(f"  {mod} -> (no deps)")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Report written to: {}", output_path)


def main():
    py_files = find_py_files()
    logger.info("Found {} .py files in core/ and districts/", len(py_files))

    outgoing, incoming = build_graph(py_files)
    logger.info("Built dependency graph with {} nodes", len(outgoing))

    sccs = find_sccs(outgoing)
    filtered = [s for s in sccs if len(s) > 1]
    if filtered:
        logger.warning("Found {} circular import chain(s)", len(filtered))
    else:
        logger.info("No circular imports detected")

    orphans = find_orphans(outgoing, incoming)
    if orphans:
        logger.info("Found {} orphan module(s)", len(orphans))

    report_path = Path(__file__).parent / "import_graph_report.txt"
    write_report(outgoing, filtered, orphans, report_path)


if __name__ == "__main__":
    main()
