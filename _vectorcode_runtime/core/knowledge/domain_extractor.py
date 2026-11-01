"""
VECTOR Domain Extractor — multi-language entry point + file signature scanner.

Scans a project directory and produces a structured context dict describing
entry points (HTTP routes, CLI commands, events, cron, GraphQL, gRPC),
file signatures (exports/imports), and project metadata (package.json, etc.).

Designed to produce a ≤512KB JSON context suitable for feeding an LLM agent
that needs to understand a codebase's domain structure quickly.

Usage:
    extractor = DomainExtractor()
    context = extractor.scan("/path/to/project")
    # or write output:
    context = extractor.scan("/path/to/project", output_path=Path("domain-context.json"))
"""
from __future__ import annotations

__all__ = ["DomainExtractor", "DomainContext"]

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger
from core.config import CONFIG

# ── Constants ──────────────────────────────────────────────────────────────

_MAX_FILE_TREE_DEPTH = 6
_MAX_FILES_PER_DIR = 50
_MAX_FILES_TOTAL = 5000
_MAX_SAMPLED_FILES = 40
_MAX_LINES_PER_FILE = 80
_MAX_ENTRY_POINTS = 200
_MAX_OUTPUT_BYTES = 512 * 1024

_SOURCE_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".py", ".pyi",
    ".go",
    ".rs",
    ".java", ".kt", ".scala",
    ".rb",
    ".cs",
    ".php",
    ".swift",
    ".c", ".cpp", ".h", ".hpp",
    ".ex", ".exs",
    ".hs",
    ".lua",
    ".r", ".R",
}

_SKIP_DIRS = {
    "node_modules", ".git", ".svn", ".hg", "__pycache__", ".tox",
    "venv", ".venv", "env", ".env", "dist", "build", "out", ".next",
    ".nuxt", "target", "vendor", ".idea", ".vscode", "coverage",
    ".understand-anything", ".pytest_cache", ".mypy_cache",
    "Pods", "DerivedData", ".gradle", "bin", "obj",
}

_METADATA_FILES = [
    "package.json", "Cargo.toml", "go.mod", "pyproject.toml",
    "setup.py", "setup.cfg", "pom.xml", "build.gradle",
    "Gemfile", "composer.json", "mix.exs", "Makefile",
    "docker-compose.yml", "docker-compose.yaml",
    "README.md", "README.rst", "README.txt", "README",
]

_ENTRY_POINT_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("http", "Express/Koa route", re.compile(
        r"""(?:app|router|server)\s*\.\s*(?:get|post|put|patch|delete|all|use)\s*\(\s*['"](/[^'"]*?)['"]""",
        re.IGNORECASE,
    )),
    ("http", "Decorator route (Flask/FastAPI/NestJS)", re.compile(
        r"""@(?:app\.)?(?:route|get|post|put|patch|delete|api_view|RequestMapping|GetMapping|PostMapping)\s*\(\s*['"](/[^'"]*?)['"]""",
        re.IGNORECASE,
    )),
    ("http", "Next.js/Remix route handler", re.compile(
        r"""export\s+(?:async\s+)?function\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b""",
    )),
    ("cli", "CLI command", re.compile(
        r"""\.command\s*\(\s*['"]([\w\-:]+)['"]""",
    )),
    ("cli", "argparse subparser", re.compile(
        r"""add_parser\s*\(\s*['"]([\w\-]+)['"]""",
    )),
    ("event", "Event listener", re.compile(
        r"""\.on\s*\(\s*['"]([\w\-:.]+)['"]""",
    )),
    ("event", "Event subscriber decorator", re.compile(
        r"""@(?:EventHandler|Subscribe|Listener|on_event)\s*\(\s*['"]([\w\-:.]+)['"]""",
    )),
    ("cron", "Cron schedule", re.compile(
        r"""@?(?:Cron|Schedule|Scheduled|crontab)\s*\(\s*['"]([^'"]+)['"]""",
        re.IGNORECASE,
    )),
    ("http", "GraphQL resolver", re.compile(
        r"""@(?:Query|Mutation|Subscription|Resolver)\s*\(""",
    )),
    ("http", "gRPC service", re.compile(
        r"""^service\s+(\w+)\s*\{""", re.MULTILINE,
    )),
    ("manual", "Exported handler", re.compile(
        r"""export\s+(?:async\s+)?function\s+(handle\w+|process\w+|on\w+)\b""",
    )),
]

_PRIORITY_KEYWORDS = [
    "controller", "service", "handler", "router", "route", "api",
    "model", "entity", "repository", "usecase", "use_case",
    "command", "query", "event", "subscriber", "listener",
    "middleware", "guard", "interceptor", "resolver",
    "workflow", "flow", "process", "pipeline", "job", "task",
]

_TEST_PATTERN = re.compile(r"(?:\.test\.|\.spec\.|__tests__|_test\.py|test_\w+\.py)")


@dataclass
class DomainContext:
    project_root: str
    file_count: int
    file_tree: list[str]
    entry_points: list[dict[str, Any]]
    file_signatures: list[dict[str, Any]]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "projectRoot": self.project_root,
            "fileCount": self.file_count,
            "fileTree": self.file_tree,
            "entryPoints": self.entry_points,
            "fileSignatures": self.file_signatures,
            "metadata": self.metadata,
        }


class DomainExtractor:
    """
    Scans a codebase and extracts domain context — entry points, file signatures,
    and project metadata — for LLM-powered domain analysis.
    """

    def scan(self, project_root: str | Path, output_path: Path | None = None) -> DomainContext:
        """
        Scan project_root and return a DomainContext.

        Args:
            project_root:  Root directory of the project to scan.
            output_path:   If given, write JSON output to this path.
        """
        root = Path(project_root).resolve()
        if not root.is_dir():
            raise ValueError(f"Not a directory: {root}")

        logger.info("[VECTOR][knowledge] Scanning domain context: {}", root)

        gitignore_patterns = self._parse_gitignore(root)
        file_tree = self._scan_file_tree(root, gitignore_patterns)
        logger.debug("[VECTOR][knowledge] Found {} source files", len(file_tree))

        entry_points = self._detect_entry_points(root, file_tree)
        logger.debug("[VECTOR][knowledge] Detected {} entry points", len(entry_points))

        signatures = self._extract_file_signatures(root, file_tree)
        metadata = self._extract_metadata(root)

        ctx = DomainContext(
            project_root=str(root),
            file_count=len(file_tree),
            file_tree=file_tree,
            entry_points=entry_points,
            file_signatures=signatures,
            metadata=metadata,
        )

        d = self._truncate_to_fit(ctx.to_dict())
        ctx.file_tree = d["fileTree"]
        ctx.entry_points = d["entryPoints"]
        ctx.file_signatures = d["fileSignatures"]

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(d, indent=2), encoding="utf-8")
            size_kb = len(json.dumps(d).encode()) / 1024
            logger.info("[VECTOR][knowledge] domain-context.json written ({:.0f} KB)", size_kb)

        return ctx

    # ── Gitignore ──────────────────────────────────────────────────────────

    def _parse_gitignore(self, root: Path) -> list[re.Pattern]:
        gitignore = root / ".gitignore"
        patterns: list[re.Pattern] = []
        if not gitignore.exists():
            return patterns
        for line in gitignore.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            regex = (line
                     .replace(".", r"\.")
                     .replace("**/", "(.*/)?")
                     .replace("*", "[^/]*")
                     .replace("?", "[^/]"))
            if line.endswith("/"):
                regex = regex.rstrip("/") + "(/|$)"
            try:
                patterns.append(re.compile(regex))
            except re.error:
                pass
        return patterns

    def _is_ignored(self, rel_path: str, patterns: list[re.Pattern]) -> bool:
        return any(p.search(rel_path) for p in patterns)

    # ── File tree scanner ──────────────────────────────────────────────────

    def _scan_file_tree(self, root: Path, gitignore_patterns: list[re.Pattern]) -> list[str]:
        result: list[str] = []

        def _walk(dir_path: Path, depth: int) -> None:
            if depth > _MAX_FILE_TREE_DEPTH or len(result) >= _MAX_FILES_TOTAL:
                return
            try:
                entries = sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
            except PermissionError:
                return

            file_count = 0
            for entry in entries:
                if len(result) >= _MAX_FILES_TOTAL:
                    break
                if entry.is_symlink():
                    continue
                rel = str(entry.relative_to(root))
                if entry.is_dir():
                    if entry.name in _SKIP_DIRS:
                        continue
                    if self._is_ignored(rel + "/", gitignore_patterns):
                        continue
                    _walk(entry, depth + 1)
                elif entry.is_file():
                    if file_count >= _MAX_FILES_PER_DIR:
                        break
                    if entry.suffix not in _SOURCE_EXTENSIONS:
                        continue
                    if self._is_ignored(rel, gitignore_patterns):
                        continue
                    result.append(rel.replace("\\", "/"))
                    file_count += 1

        _walk(root, 0)
        return result

    # ── Entry point detection ──────────────────────────────────────────────

    def _detect_entry_points(self, root: Path, file_paths: list[str]) -> list[dict[str, Any]]:
        entry_points: list[dict[str, Any]] = []
        for rel_path in file_paths:
            if len(entry_points) >= _MAX_ENTRY_POINTS:
                break
            if _TEST_PATTERN.search(rel_path):
                continue
            full_path = root / rel_path
            try:
                content = full_path.read_text(errors="replace")
            except (OSError, UnicodeDecodeError):
                continue

            lines = content.splitlines()
            for entry_type, description, pattern in _ENTRY_POINT_PATTERNS:
                for match in pattern.finditer(content):
                    line_no = content[:match.start()].count("\n") + 1
                    start = max(0, line_no - 1)
                    end = min(len(lines), start + 5)
                    snippet = "\n".join(lines[start:end])
                    entry_points.append({
                        "file": rel_path,
                        "line": line_no,
                        "type": entry_type,
                        "description": description,
                        "match": match.group(0)[:120],
                        "snippet": snippet[:300],
                    })
                    if len(entry_points) >= _MAX_ENTRY_POINTS:
                        break
                if len(entry_points) >= _MAX_ENTRY_POINTS:
                    break
        return entry_points

    # ── File signatures ────────────────────────────────────────────────────

    def _extract_file_signatures(self, root: Path, file_paths: list[str]) -> list[dict[str, Any]]:
        def priority_score(path: str) -> int:
            lower = path.lower()
            return sum(1 for kw in _PRIORITY_KEYWORDS if kw in lower)

        sorted_paths = sorted(file_paths, key=priority_score, reverse=True)
        signatures: list[dict[str, Any]] = []

        for rel_path in sorted_paths[:_MAX_SAMPLED_FILES]:
            full_path = root / rel_path
            try:
                content = full_path.read_text(errors="replace")
            except (OSError, UnicodeDecodeError):
                continue

            lines = content.splitlines()[:_MAX_LINES_PER_FILE]
            truncated = "\n".join(lines)

            exports = re.findall(
                r"export\s+(?:default\s+)?(?:async\s+)?(?:function|class|const|let|var|interface|type|enum)\s+(\w+)",
                truncated,
            )
            if not exports:
                exports = re.findall(r"^(?:def|class)\s+(\w+)", truncated, re.MULTILINE)

            imports = re.findall(
                r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|from\s+([\w.]+)\s+import)""",
                truncated,
            )
            import_list = [m[0] or m[1] for m in imports][:20]

            signatures.append({
                "file": rel_path,
                "exports": exports[:20],
                "imports": import_list,
                "lines": len(content.splitlines()),
                "preview": truncated[:500],
            })

        return signatures

    # ── Metadata extraction ────────────────────────────────────────────────

    def _extract_metadata(self, root: Path) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for filename in _METADATA_FILES:
            filepath = root / filename
            if not filepath.exists():
                continue
            try:
                content = filepath.read_text(errors="replace")
            except (OSError, UnicodeDecodeError):
                continue

            if filename == "package.json":
                try:
                    pkg = json.loads(content)
                    metadata["package.json"] = {
                        "name": pkg.get("name"),
                        "description": pkg.get("description"),
                        "scripts": list((pkg.get("scripts") or {}).keys()),
                        "dependencies": list((pkg.get("dependencies") or {}).keys()),
                        "devDependencies": list((pkg.get("devDependencies") or {}).keys()),
                    }
                except json.JSONDecodeError:
                    metadata["package.json"] = content[:500]
            elif filename.endswith((".md", ".rst", ".txt")) or filename == "README":
                metadata[filename] = content[:2000]
            else:
                metadata[filename] = content[:1000]

        return metadata

    # ── Output clamping ────────────────────────────────────────────────────

    def _truncate_to_fit(self, context: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(context).encode()) <= _MAX_OUTPUT_BYTES:
            return context
        context["fileTree"] = context["fileTree"][:200]
        if len(json.dumps(context).encode()) <= _MAX_OUTPUT_BYTES:
            return context
        for sig in context.get("fileSignatures", []):
            sig["preview"] = sig["preview"][:200]
        if len(json.dumps(context).encode()) <= _MAX_OUTPUT_BYTES:
            return context
        for ep in context.get("entryPoints", []):
            ep["snippet"] = ep["snippet"][:100]
        if len(json.dumps(context).encode()) <= _MAX_OUTPUT_BYTES:
            return context
        context["fileSignatures"] = context["fileSignatures"][:20]
        context["entryPoints"] = context["entryPoints"][:100]
        return context


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # Create a simple fake project
        (root / "app.py").write_text('@app.route("/api/users")\ndef get_users():\n    pass\n')
        (root / "cli.py").write_text('parser.add_subparsers()\nparser.add_parser("run")\n')
        (root / "requirements.txt").write_text("fastapi\n")
        (root / "README.md").write_text("# Test Project\n")

        extractor = DomainExtractor()
        ctx = extractor.scan(root)
        assert ctx.file_count >= 2
        assert any(ep["type"] == "http" for ep in ctx.entry_points), "Should detect Flask route"
        assert any(ep["type"] == "cli" for ep in ctx.entry_points), "Should detect CLI subparser"
        assert len(ctx.file_signatures) >= 1
        assert "README.md" in ctx.metadata

        d2 = ctx.to_dict()
        assert d2["fileCount"] == ctx.file_count
        assert d2["projectRoot"] == str(root.resolve())

    print("OK domain_extractor.py — entry points, signatures, metadata, truncation verified")
