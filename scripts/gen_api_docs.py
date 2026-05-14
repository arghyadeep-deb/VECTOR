"""Generate API reference documentation from VectorCode source code.

Walks vectorcode/python/vectorcode/ and produces a markdown API reference
with module summaries, public class signatures, and function signatures.
"""
import ast
import sys
from pathlib import Path
from typing import List, Tuple

VC = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode\python\vectorcode")
OUT = Path(r"C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\V.E.C.T.O.R. Codebase\vectorcode\docs\API_REFERENCE.md")

SKIP_DIRS = {"__pycache__", ".pytest_cache", "skills"}
SKIP_FILES = {"__init__.py"}


def get_signature(node) -> str:
    """Extract a function/method signature."""
    args = []
    for arg in node.args.args:
        a = arg.arg
        if arg.annotation:
            try:
                a += f": {ast.unparse(arg.annotation)}"
            except Exception:
                pass
        args.append(a)
    for arg in node.args.kwonlyargs:
        a = arg.arg
        if arg.annotation:
            try:
                a += f": {ast.unparse(arg.annotation)}"
            except Exception:
                pass
        args.append(a)
    sig = ", ".join(args)
    rtype = ""
    if node.returns:
        try:
            rtype = f" -> {ast.unparse(node.returns)}"
        except Exception:
            pass
    return f"{node.name}({sig}){rtype}"


def get_docstring(node) -> str:
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        doc = node.body[0].value.value.strip()
        # First line only for brevity
        return doc.split("\n")[0].strip()[:120]
    return ""


def analyze_file(path: Path) -> Tuple[str, List[str], List[Tuple[str, str, List[str]]]]:
    """Return (module_doc, top_level_functions, classes)."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return "", [], []

    module_doc = ""
    if (tree.body and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)):
        module_doc = tree.body[0].value.value.strip().split("\n")[0][:120]

    funcs = []
    classes = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                sig = get_signature(node)
                doc = get_docstring(node)
                funcs.append(f"`{sig}` — {doc}" if doc else f"`{sig}`")
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                cls_doc = get_docstring(node)
                methods = []
                for m in node.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not m.name.startswith("_") or m.name in ("__init__",):
                            methods.append(get_signature(m))
                classes.append((node.name, cls_doc, methods))

    return module_doc, funcs, classes


def main():
    sections: List[Tuple[str, List[Path]]] = []

    # Discover source files grouped by top-level package
    for entry in sorted(VC.iterdir()):
        if entry.is_dir():
            if entry.name in SKIP_DIRS:
                continue
            files = sorted(entry.rglob("*.py"))
            files = [f for f in files
                     if not any(d in f.parts for d in SKIP_DIRS)
                     and f.name not in SKIP_FILES]
            if files:
                sections.append((entry.name, files))
        elif entry.suffix == ".py" and entry.name not in SKIP_FILES:
            sections.append(("(root)", [entry]))

    # Build markdown
    lines = [
        "# VectorCode API Reference",
        "",
        "Auto-generated from source. Lists every public module, class, and function.",
        "",
        "**Generated:** by `scripts/gen_api_docs.py`",
        "",
        "---",
        "",
        "## Table of Contents",
        "",
    ]
    for section, _ in sections:
        anchor = section.replace("/", "").replace(" ", "-").lower()
        lines.append(f"- [{section}](#{anchor})")
    lines.append("")

    for section, files in sections:
        anchor = section.replace("/", "").replace(" ", "-").lower()
        lines.append("---")
        lines.append("")
        lines.append(f"## {section}")
        lines.append("")
        for f in files:
            rel = f.relative_to(VC)
            mod_doc, funcs, classes = analyze_file(f)
            if not (mod_doc or funcs or classes):
                continue
            lines.append(f"### `{rel.as_posix()}`")
            lines.append("")
            if mod_doc:
                lines.append(f"_{mod_doc}_")
                lines.append("")
            if classes:
                lines.append("**Classes:**")
                lines.append("")
                for cname, cdoc, methods in classes:
                    head = f"- **`{cname}`**"
                    if cdoc:
                        head += f" — {cdoc}"
                    lines.append(head)
                    if methods:
                        for m in methods[:8]:
                            lines.append(f"  - `{m}`")
                        if len(methods) > 8:
                            lines.append(f"  - _(+{len(methods) - 8} more methods)_")
                lines.append("")
            if funcs:
                lines.append("**Functions:**")
                lines.append("")
                for fn in funcs[:15]:
                    lines.append(f"- {fn}")
                if len(funcs) > 15:
                    lines.append(f"- _(+{len(funcs) - 15} more functions)_")
                lines.append("")
        lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {OUT}")
    print(f"Sections: {len(sections)}, Lines: {len(lines)}")


if __name__ == "__main__":
    main()
