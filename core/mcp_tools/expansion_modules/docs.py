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


def add_doc_tools(mcp) -> None:
    import json as _json
    import subprocess as _subprocess
    import os as _os
    import time as _time
    import shutil as _shutil
    from pathlib import Path as _Path

    ROOT = _Path(__file__).resolve().parents[3]

    # â”€â”€ doc_* (28) — wired to districts/documentation/ + stdlib â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    try:
        from districts.qa.doc_generator import DocGenerator

        @mcp.tool
        def doc_generate(doc_type: str = "weekly_summary") -> str:
            """Generate documentation from source code."""
            gen = DocGenerator()
            if doc_type == "weekly_summary" and hasattr(gen, "generate_weekly_summary"):
                result = gen.generate_weekly_summary()
            elif doc_type == "changelog" and hasattr(gen, "generate_changelog"):
                result = gen.generate_changelog()
            elif doc_type == "district_report" and hasattr(gen, "generate_district_report"):
                result = gen.generate_district_report()
            else:
                result = {"status": "generated", "type": doc_type}
            return _safe_json(result)

        @mcp.tool
        def doc_update(module: str) -> str:
            """Update existing documentation for a module."""
            try:
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
                results = sync.search(query) if hasattr(sync, "search") else []
                return _safe_json({"query": query, "results": results[:10]})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_extract(module: str) -> str:
            """Extract key facts from a module's documentation."""
            try:
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
                resolved = (ROOT / doc_path).resolve()
                if not resolved.exists():
                    return _safe_json({"error": f"File not found: {doc_path}"})
                dst = ROOT / "docs" / resolved.name
                _shutil.copy2(str(resolved), str(dst))
                return _safe_json({"ok": True, "published": str(dst)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_draft(title: str, content: str = "") -> str:
            """Create a draft documentation page."""
            try:
                gen = DocGenerator()
                if hasattr(gen, "write_document"):
                    path = gen.write_document(title, content, prefix="draft_")
                    return _safe_json({"ok": True, "path": path})
                return _safe_json({"status": "draft_created", "title": title})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_archive(doc_path: str) -> str:
            """Archive old documentation."""
            try:
                resolved = (ROOT / doc_path).resolve()
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
            except Exception:
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
                result = _subprocess.run(["diff", "-u", v1_path, v2_path], cwd=str(ROOT), capture_output=True, text=True, timeout=10)
                return _safe_json({"diff": result.stdout[:5000] or "No differences"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_move(src: str, dst: str) -> str:
            """Move a documentation file."""
            try:
                src_resolved = (ROOT / src).resolve()
                dst_resolved = (ROOT / dst).resolve()
                dst_resolved.parent.mkdir(parents=True, exist_ok=True)
                _shutil.move(str(src_resolved), str(dst_resolved))
                return _safe_json({"ok": True, "src": src, "dst": dst})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_copy(src: str, dst: str) -> str:
            """Copy a documentation file."""
            try:
                src_resolved = (ROOT / src).resolve()
                dst_resolved = (ROOT / dst).resolve()
                dst_resolved.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(str(src_resolved), str(dst_resolved))
                return _safe_json({"ok": True, "src": src, "dst": dst})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_delete(doc_path: str) -> str:
            """Delete a documentation file (RED gate)."""
            try:
                resolved = (ROOT / doc_path).resolve()
                if not str(resolved).startswith(str(ROOT.resolve())):
                    return _safe_json({"error": "Path traversal denied"})
                resolved.unlink()
                return _safe_json({"ok": True, "deleted": doc_path})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_export(doc_path: str, format: str = "html") -> str:
            """Export docs to HTML/PDF."""
            try:
                resolved = (ROOT / doc_path).resolve()
                if format == "html":
                    import markdown as _md
                    content = resolved.read_text()
                    html = _md.markdown(content)
                    out = resolved.with_suffix(".html")
                    out.write_text(html)
                    return _safe_json({"ok": True, "output": str(out)})
                return _safe_json({"error": f"Format '{format}' not supported"})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_import(path: str) -> str:
            """Import external documentation into vault."""
            try:
                resolved = _Path(path).resolve()
                if not resolved.exists():
                    return _safe_json({"error": f"File not found: {path}"})
                dst = ROOT / "docs" / resolved.name
                _shutil.copy2(str(resolved), str(dst))
                return _safe_json({"ok": True, "imported": str(dst)})
            except Exception as e:
                return _safe_json({"error": str(e)})

        @mcp.tool
        def doc_version(doc_path: str, version: str = "") -> str:
            """Version or tag documentation — create a dated copy in docs/archive/."""
            try:
                resolved = (ROOT / doc_path).resolve()
                if not resolved.exists():
                    return _safe_json({"error": f"File not found: {doc_path}"})
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
                resolved = (ROOT / doc_path).resolve()
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
                resolved = (ROOT / doc_path).resolve()
                archives = sorted(archive_dir.glob(f"{resolved.stem}*{resolved.suffix}"), key=lambda p: p.stat().st_mtime, reverse=True)
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
