"""Scan all .py files for dead code detection using AST + inverted index."""
import ast
import json
import re
from pathlib import Path
from collections import defaultdict


from loguru import logger

EXCLUDE_DIRS = {"vectorcode", "node_modules", ".git", "__pycache__", ".pytest_cache", "venv", ".claude"}
WORD_RE = re.compile(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b")


def _should_skip(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True
    if path.stem.startswith("test_") or path.stem.endswith("_test"):
        return True
    return False


def extract_definitions(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                names.add(node.target.id)
    return names


def find_all_py_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for py_file in root.rglob("*.py"):
        if _should_skip(py_file):
            continue
        files.append(py_file)
    return sorted(files)


def build_inverted_index(py_files: list[Path], content_map: dict[Path, str]) -> dict[str, set[Path]]:
    idx: dict[str, set[Path]] = defaultdict(set)
    for pyf in py_files:
        for word in WORD_RE.findall(content_map[pyf]):
            idx[word].add(pyf)
    return idx


def report(
    py_files: list[Path],
    defs_per_file: dict[Path, set[str]],
    content_map: dict[Path, str],
    inv_idx: dict[str, set[Path]],
    output_path: Path,
) -> dict:
    potentially_dead: list[dict] = []
    only_init_refs: list[dict] = []
    duplicates: dict[str, list[Path]] = defaultdict(list)
    large_files: list[dict] = []

    for pyf in py_files:
        line_count = content_map[pyf].count("\n") + 1
        if line_count > 1000:
            large_files.append({
                "file": str(pyf.relative_to(Path.cwd())),
                "lines": line_count,
            })
        for name in defs_per_file[pyf]:
            duplicates[name].append(pyf)

    duplicate_report = {n: [str(p.relative_to(Path.cwd())) for p in locs] for n, locs in duplicates.items() if len(locs) > 1}

    init_files = {pyf for pyf in py_files if pyf.name == "__init__.py"}
    non_init_files = [pyf for pyf in py_files if pyf.name != "__init__.py"]

    for pyf in non_init_files:
        rel = str(pyf.relative_to(Path.cwd()))
        own_defs = defs_per_file[pyf]
        if not own_defs:
            continue
        external_files: set[Path] = set()
        init_using_files: set[Path] = set()
        for name in own_defs:
            using = inv_idx.get(name, set())
            external_files.update(using - {pyf})
            init_using_files.update(using & init_files - {pyf})

        if not external_files:
            potentially_dead.append({"file": rel, "definitions": sorted(own_defs)})
        elif init_using_files and external_files == init_using_files:
            only_init_refs.append({
                "file": rel,
                "definitions": sorted(own_defs),
                "init_files": sorted(str(p.relative_to(Path.cwd())) for p in init_using_files),
            })

    result = {
        "summary": {
            "total_files_scanned": len(py_files),
            "potentially_dead_files": len(potentially_dead),
            "files_only_in_init_references": len(only_init_refs),
            "duplicate_definitions": len(duplicate_report),
            "large_files_over_1000_lines": len(large_files),
        },
        "potentially_dead": potentially_dead,
        "only_init_references": only_init_refs,
        "duplicate_definitions": [{"name": n, "files": f} for n, f in duplicate_report.items()],
        "large_files": large_files,
    }

    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def print_human_summary(data: dict):
    s = data["summary"]
    logger.info("=== Dead Code Scanner Report ===")
    logger.info("Total .py files scanned: {}", s["total_files_scanned"])
    logger.info("Potentially dead files: {}", s["potentially_dead_files"])
    logger.info("Files only referenced in __init__.py: {}", s["files_only_in_init_references"])
    logger.info("Duplicate definitions found: {}", s["duplicate_definitions"])
    logger.info("Files over 1000 lines: {}", s["large_files_over_1000_lines"])

    if data["potentially_dead"]:
        logger.info("--- Potentially Dead Files ---")
        for entry in data["potentially_dead"]:
            logger.info("  {} (defs: {})", entry["file"], ", ".join(entry["definitions"]))

    if data["only_init_references"]:
        logger.info("--- Files Only Referenced via __init__.py ---")
        for entry in data["only_init_references"]:
            logger.info("  {} (refs via {})", entry["file"], ", ".join(entry["init_files"]))

    if data["duplicate_definitions"]:
        logger.info("--- Duplicate Definitions ---")
        for entry in data["duplicate_definitions"]:
            logger.info("  {} -> {}", entry["name"], ", ".join(entry["files"]))

    if data["large_files"]:
        logger.info("--- Large Files (>1000 lines) ---")
        for entry in data["large_files"]:
            logger.info("  {} ({} lines)", entry["file"], entry["lines"])
    logger.info("=== End Report ===")


def main():
    root = Path.cwd()
    logger.info("Scanning .py files from: {}", root)
    py_files = find_all_py_files(root)
    logger.info("Found {} .py files (excluding vectorcode, node_modules, .git)", len(py_files))

    defs_per_file: dict[Path, set[str]] = {}
    content_map: dict[Path, str] = {}
    for pyf in py_files:
        source = pyf.read_text(encoding="utf-8", errors="replace")
        content_map[pyf] = source
        defs_per_file[pyf] = extract_definitions(source)

    logger.info("Building inverted word index...")
    inv_idx = build_inverted_index(py_files, content_map)
    logger.info("Inverted index built with {} unique words across {} files", len(inv_idx), len(py_files))

    report_path = Path(__file__).parent / "dead_code_report.json"
    data = report(py_files, defs_per_file, content_map, inv_idx, report_path)
    print_human_summary(data)
    logger.info("Report written to: {}", report_path)


if __name__ == "__main__":
    main()
