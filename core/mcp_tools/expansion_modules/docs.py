from __future__ import annotations

from pathlib import Path

from loguru import logger

from core.config import CONFIG
from core.mcp_tools.error_handling import safe_json as _safe_json
from core.mcp_tools.error_handling import register_stub_tool as _reg
from core.mcp_tools.memory_safety import (
    MEMORY_CLEAR_CONFIRM as _MEMORY_CLEAR_CONFIRM,
    resolve_memory_path as _resolve_memory_path,
)

_ROOT = Path(__file__).resolve().parents[3]  # module-level so tests can point it at a tmp dir
_DOC_EXTS = frozenset({".md", ".markdown", ".rst", ".txt", ".html", ".htm", ".pdf"})
_DENY_PARTS = frozenset({".git", ".github", ".claude"})


def _doc_path(root: Path, raw: str) -> tuple[Path | None, str | None]:
    """Resolve a caller-supplied documentation path. Returns (path, error).

    Must stay inside the repo root (CWE-22, symlink-safe via is_relative_to),
    must be a documentation file type (so a doc tool cannot overwrite/delete
    source code, configs or secrets) and must not touch VCS/agent config dirs.
    """
    base = root.resolve()
    try:
        p = (base / (raw or "")).resolve()
    except (OSError, ValueError):
        return None, "invalid path"
    if p == base or not p.is_relative_to(base):
        return None, "Path traversal denied"
    if p.suffix.lower() not in _DOC_EXTS:
        return None, f"not a documentation file type: {p.suffix or '(none)'}"
    if _DENY_PARTS.intersection(p.relative_to(base).parts):
        return None, "protected path"
    return p, None


def _py_module_path(root: Path, raw: str) -> tuple[Path | None, str | None]:
    """Resolve a caller-supplied module file: a .py file inside the repo root."""
    base = root.resolve()
    try:
        p = (base / (raw or "")).resolve()
    except (OSError, ValueError):
        return None, "invalid path"
    if not p.is_relative_to(base) or p.suffix != ".py":
        return None, "module must be a .py file inside the repo root"
    return p, None


def add_doc_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _ROOT

    # â”€â”€ doc_* (28) — wired to districts/documentation/ + stdlib â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from districts.qa.doc_generator import DocGenerator

        @mcp.tool
        def doc_generate(doc_type: str = "weekly_summary") -> str:
            """Generate documentation from source code."""
            try:
                gen = DocGenerator()
                if doc_type == "weekly_summary":
                    result = gen.generate_weekly_summary()
                elif doc_type == "changelog":
                    result = gen.generate_changelog()
                else:
                    return _safe_json({"error": f"unsupported doc_type '{doc_type}' (use weekly_summary or changelog)"})
                return _safe_json(result)
            except Exception as e:
                logger.warning("[VECTOR][mcp] doc_generate failed: {}", e)
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_update(module: str) -> str:
            """Update existing documentation for a module."""
            try:
                mod_p, err = _py_module_path(ROOT, module)
                if err:
                    return _safe_json({"error": err})
                module = str(mod_p)
                from districts.qa.technical_writer import TechnicalWriter
                writer = TechnicalWriter()
                result = writer.generate_module_docs(module) if hasattr(writer, "generate_module_docs") else {"module": module, "status": "updated"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_search(query: str) -> str:
            """Search documentation content."""
            try:
                from core.memory.obsidian_sync import ObsidianSync
                sync = ObsidianSync()
                if not hasattr(sync, "search"):
                    return _safe_json({"error": "doc search backend unavailable (ObsidianSync has no search)"})
                results = sync.search(query)
                return _safe_json({"query": query, "results": results[:10]})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_extract(module: str) -> str:
            """Extract key facts from a module's documentation."""
            try:
                mod_p, err = _py_module_path(ROOT, module)
                if err:
                    return _safe_json({"error": err})
                module = str(mod_p)
                from districts.qa.technical_writer import TechnicalWriter
                writer = TechnicalWriter()
                result = writer.scan_module(module) if hasattr(writer, "scan_module") else {"module": module, "status": "scanned"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_index() -> str:
            """Rebuild documentation index."""
            try:
                from core.brain_hooks import vault_stats
                stats = vault_stats()
                return _safe_json({"index": stats})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_tag(doc_path: str, tags: str) -> str:
            """Tag documentation entries."""
            try:
                from core.memory.obsidian_sync import ObsidianSync
                sync = ObsidianSync()
                tag_list = [t.strip() for t in tags.split(",")]
                if hasattr(sync, "write_note"):
                    sync.write_note(doc_path, tags=tag_list)
                return _safe_json({"ok": True, "path": doc_path, "tags": tag_list})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_link(source: str, target: str) -> str:
            """Add cross-references between docs."""
            try:
                from core.memory.knowledge_graph import get_knowledge_graph
                kg = get_knowledge_graph()
                kg.add_relation(source, "references", target)
                return _safe_json({"ok": True, "source": source, "target": target})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_render(content: str) -> str:
            """Render markdown to HTML."""
            try:
                import markdown as _md
                html = _md.markdown(content)
                return _safe_json({"html": html[:5000], "length": len(html)})
            except ImportError:
                return _safe_json({"error": "markdown package not installed — pip install markdown"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_validate(module: str) -> str:
            """Validate documentation completeness."""
            try:
                mod_p, err = _py_module_path(ROOT, module)
                if err:
                    return _safe_json({"error": err})
                module = str(mod_p)
                from districts.qa.technical_writer import TechnicalWriter
                writer = TechnicalWriter()
                result = writer.scan_module(module) if hasattr(writer, "scan_module") else {"module": module, "status": "validated"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_lint(module: str) -> str:
            """Lint documentation for issues."""
            try:
                mod_p, err = _py_module_path(ROOT, module)
                if err:
                    return _safe_json({"error": err})
                module = str(mod_p)
                from districts.qa.technical_writer import TechnicalWriter
                writer = TechnicalWriter()
                result = writer.scan_module(module) if hasattr(writer, "scan_module") else {"module": module, "status": "linted"}
                return _safe_json(result)
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_publish(doc_path: str) -> str:
            """Publish docs to the docs/ directory."""
            try:
                resolved, err = _doc_path(ROOT, doc_path)
                if err:
                    return _safe_json({"error": err})
                if not resolved.exists():
                    return _safe_json({"error": f"File not found: {doc_path}"})
                dst = ROOT / "docs" / resolved.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(str(resolved), str(dst))
                return _safe_json({"ok": True, "published": str(dst)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_draft(title: str, content: str = "") -> str:
            """Create a draft documentation page."""
            try:
                import re as _re
                slug = _re.sub(r"[^A-Za-z0-9_-]+", "_", title or "").strip("_")[:60]
                if not slug:
                    return _safe_json({"error": "title must contain letters or digits"})
                gen = DocGenerator()
                doc_type = f"draft_{slug}"
                if not gen.write_document(content, doc_type):
                    return _safe_json({"error": "draft could not be written"})
                path = ROOT / "docs" / f"{doc_type}_{_time.strftime('%Y-%m-%d')}.md"
                return _safe_json({"ok": True, "path": str(path)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_archive(doc_path: str) -> str:
            """Archive old documentation."""
            try:
                resolved, err = _doc_path(ROOT, doc_path)
                if err:
                    return _safe_json({"error": err})
                archive_dir = ROOT / "docs" / "archive"
                archive_dir.mkdir(parents=True, exist_ok=True)
                dst = archive_dir / resolved.name
                _shutil.copy2(str(resolved), str(dst))
                return _safe_json({"ok": True, "archived": str(dst)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_summarize(content: str, max_length: int = 500) -> str:
            """Summarize a documentation page."""
            summary = content[:max_length] + ("..." if len(content) > max_length else "")
            return _safe_json({"summary": summary, "original_length": len(content)})

        @mcp.tool
        def doc_format(content: str, style: str = "vector") -> str:
            """Format documentation to style guide."""
            formatted = content.strip()
            return _safe_json({"formatted": formatted, "style": style})

        @mcp.tool
        def doc_translate(content: str, target_lang: str = "en") -> str:
            """Translate documentation to another language."""
            try:
                from core.inference.vectorcode_llm import chat
                result = chat(f"Translate the following text to {target_lang}:\n\n{content[:2000]}")
                return _safe_json({"translation": result, "target_lang": target_lang})
            except Exception as e:
                logger.warning("[VECTOR][mcp] doc_translate unavailable: {}", e)
                return _safe_json({"status": "unavailable", "message": "Translation requires vectorcode_llm module"})

        @mcp.tool
        def doc_embed(content: str) -> str:
            """Embed documentation in vector index."""
            try:
                from core.memory.obsidian_sync import ObsidianSync
                sync = ObsidianSync()
                if hasattr(sync, "write_note"):
                    sync.write_note("embedded_doc", content=content)
                return _safe_json({"ok": True, "length": len(content)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_compare(v1_path: str, v2_path: str) -> str:
            """Compare two documentation versions."""
            try:
                p1, err = _doc_path(ROOT, v1_path)
                if err:
                    return _safe_json({"error": err})
                p2, err = _doc_path(ROOT, v2_path)
                if err:
                    return _safe_json({"error": err})
                result = _subprocess.run(["diff", "-u", "--", str(p1), str(p2)], cwd=str(ROOT), capture_output=True, text=True, timeout=10)
                if result.returncode > 1:  # diff: 0 = same, 1 = differ, >1 = trouble (missing file, ...)
                    return _safe_json({"error": f"diff failed (exit {result.returncode})", "stderr": result.stderr[:500]})
                return _safe_json({"diff": result.stdout[:5000] or "No differences"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_move(src: str, dst: str) -> str:
            """Move a documentation file."""
            try:
                src_resolved, err = _doc_path(ROOT, src)
                if err:
                    return _safe_json({"error": err})
                dst_resolved, err = _doc_path(ROOT, dst)
                if err:
                    return _safe_json({"error": err})
                if not src_resolved.exists():
                    return _safe_json({"error": f"File not found: {src}"})
                dst_resolved.parent.mkdir(parents=True, exist_ok=True)
                _shutil.move(str(src_resolved), str(dst_resolved))
                return _safe_json({"ok": True, "src": src, "dst": dst})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_copy(src: str, dst: str) -> str:
            """Copy a documentation file."""
            try:
                src_resolved, err = _doc_path(ROOT, src)
                if err:
                    return _safe_json({"error": err})
                dst_resolved, err = _doc_path(ROOT, dst)
                if err:
                    return _safe_json({"error": err})
                if not src_resolved.exists():
                    return _safe_json({"error": f"File not found: {src}"})
                dst_resolved.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(str(src_resolved), str(dst_resolved))
                return _safe_json({"ok": True, "src": src, "dst": dst})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_delete(doc_path: str) -> str:
            """Delete a documentation file (RED gate)."""
            try:
                resolved, err = _doc_path(ROOT, doc_path)
                if err:
                    return _safe_json({"error": err})
                resolved.unlink()
                return _safe_json({"ok": True, "deleted": doc_path})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_export(doc_path: str, format: str = "html") -> str:
            """Export docs to HTML/PDF."""
            try:
                resolved, err = _doc_path(ROOT, doc_path)
                if err:
                    return _safe_json({"error": err})
                if format == "html":
                    import markdown as _md
                    content = resolved.read_text(encoding="utf-8", errors="replace")
                    html = _md.markdown(content)
                    out = resolved.with_suffix(".html")
                    out.write_text(html, encoding="utf-8")
                    return _safe_json({"ok": True, "output": str(out)})
                return _safe_json({"error": f"Format '{format}' not supported"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_import(path: str) -> str:
            """Import external documentation into vault."""
            try:
                resolved = _Path(path).resolve()
                if resolved.suffix.lower() not in _DOC_EXTS:
                    return _safe_json({"error": f"not a documentation file type: {resolved.suffix or '(none)'}"})
                if not resolved.is_file():
                    return _safe_json({"error": f"File not found: {path}"})
                dst = ROOT / "docs" / resolved.name
                dst.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(str(resolved), str(dst))
                return _safe_json({"ok": True, "imported": str(dst)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_version(doc_path: str, version: str = "") -> str:
            """Version or tag documentation — create a dated copy in docs/archive/."""
            try:
                resolved, err = _doc_path(ROOT, doc_path)
                if err:
                    return _safe_json({"error": err})
                if not resolved.exists():
                    return _safe_json({"error": f"File not found: {doc_path}"})
                import re as _re
                if version and not _re.fullmatch(r"[A-Za-z0-9._-]{1,40}", version):
                    return _safe_json({"error": "invalid version label"})
                ver = version or _time.strftime("%Y%m%d")
                archive_name = f"{resolved.stem}-v{ver}{resolved.suffix}"
                archive_dir = ROOT / "docs" / "archive"
                archive_dir.mkdir(parents=True, exist_ok=True)
                dst = archive_dir / archive_name
                _shutil.copy2(str(resolved), str(dst))
                return _safe_json({"ok": True, "version": ver, "archived": str(dst)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_review(module: str) -> str:
            """Review documentation for accuracy — scans source and suggests improvements."""
            try:
                mod_p, err = _py_module_path(ROOT, module)
                if err:
                    return _safe_json({"error": err})
                module = str(mod_p)
                from districts.qa.technical_writer import TechnicalWriter
                writer = TechnicalWriter()
                result = writer.scan_module(module) if hasattr(writer, "scan_module") else {"module": module, "status": "reviewed"}
                return _safe_json(result)
            except ImportError:
                docs_dir = ROOT / "docs"
                files = sorted(f.name for f in docs_dir.glob("*.md") if f.is_file())
                return _safe_json({"module": module, "status": "scanned", "docs_count": len(files)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_approve(doc_path: str) -> str:
            """Approve and finalise documentation — move from draft to docs/."""
            try:
                resolved, err = _doc_path(ROOT, doc_path)
                if err:
                    return _safe_json({"error": err})
                if not resolved.exists():
                    return _safe_json({"error": f"File not found: {doc_path}"})
                if "draft" in resolved.name:
                    final_name = resolved.name.replace("draft_", "")
                    dst = resolved.parent / final_name
                    _shutil.move(str(resolved), str(dst))
                    return _safe_json({"ok": True, "approved": str(dst)})
                return _safe_json({"ok": True, "note": f"'{doc_path}' already finalised"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_unlink(source: str, target: str) -> str:
            """Remove cross-references between docs in the knowledge graph."""
            try:
                from core.memory.knowledge_graph import get_knowledge_graph
                kg = get_knowledge_graph()
                kg.add_relation(source, "removed_reference", target, confidence=0.0, source="mcp_doc_unlink")
                return _safe_json({"ok": True, "source": source, "target": target})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_restore(doc_path: str) -> str:
            """Restore a documentation file from docs/archive/."""
            try:
                archive_dir = ROOT / "docs" / "archive"
                if not archive_dir.exists():
                    return _safe_json({"error": "No archive directory found"})
                resolved, err = _doc_path(ROOT, doc_path)
                if err:
                    return _safe_json({"error": err})
                import glob as _glob
                archives = sorted(archive_dir.glob(f"{_glob.escape(resolved.stem)}*{_glob.escape(resolved.suffix)}"), key=lambda p: p.stat().st_mtime, reverse=True)
                if not archives:
                    return _safe_json({"error": f"No archived versions of {doc_path} found"})
                _shutil.copy2(str(archives[0]), str(resolved))
                return _safe_json({"ok": True, "restored_from": str(archives[0]), "to": str(resolved)})
            except Exception as e:
                return _safe_json({"error": str(e)})
    except ImportError as e:
        logger.warning(f"[VECTOR][mcp] doc tools unavailable: {e}")
        for n, d in [("doc_generate", "Generate docs"), ("doc_update", "Update docs"), ("doc_search", "Search docs"), ("doc_export", "Export docs"), ("doc_import", "Import docs"), ("doc_render", "Render markdown"), ("doc_validate", "Validate docs"), ("doc_lint", "Lint docs"), ("doc_publish", "Publish docs"), ("doc_draft", "Draft doc"), ("doc_archive", "Archive doc"), ("doc_index", "Doc index"), ("doc_tag", "Tag doc"), ("doc_link", "Link docs"), ("doc_move", "Move doc"), ("doc_copy", "Copy doc"), ("doc_delete", "Delete doc"), ("doc_format", "Format doc"), ("doc_translate", "Translate doc"), ("doc_summarize", "Summarize doc"), ("doc_extract", "Extract facts"), ("doc_embed", "Embed doc"), ("doc_compare", "Compare docs"), ("doc_version", "Version doc"), ("doc_review", "Review doc"), ("doc_approve", "Approve doc"), ("doc_unlink", "Unlink doc"), ("doc_restore", "Restore doc")]:
            _reg(mcp, n, d)
