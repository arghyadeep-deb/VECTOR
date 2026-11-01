import sys

__all__ = [
    "ObsidianSync",
    "PermissionDeniedError",
]

import os
import datetime
import hashlib
import time
import threading
from pathlib import Path

from core.config import CONFIG
from loguru import logger

_LIGHTRAG_PATH = Path(__file__).parent.parent.parent / "districts/memory_curator"

# FIX #15: File-level locking to prevent race conditions between agents writing to vault
_vault_write_lock = threading.Lock()


_RAG_RETRY_AFTER_S = 600.0

# 2026-09-29 (live soak-test finding): a vault note whose plain text happens to contain a literal
# tiktoken special-token marker (e.g. a code block pasting a raw LLM completion that includes
# "<|endoftext|>") makes LightRAG's own chunker raise ValueError("disallowed special token") on
# every ingest attempt. VECTOR's own _insert_to_rag() already catches that and logs a warning, so
# nothing crashes -- but the higher-level ingestion pipeline (core/loop or wherever schedules
# ingest_existing/ingest_file) resets a permanently-failing document from FAILED back to PENDING
# and retries it forever, burning real embedding/LLM calls on a document that can never succeed as
# written. Fix at the source: neutralize the literal marker text before LightRAG ever tokenizes it,
# so ingestion actually succeeds instead of retrying indefinitely.
_TIKTOKEN_SPECIAL_TOKENS = ("<|endoftext|>", "<|fim_prefix|>", "<|fim_suffix|>", "<|fim_middle|>", "<|endofprompt|>")


def _neutralize_special_tokens(content: str) -> str:
    """Replace literal tiktoken special-token markers with a visually similar, harmless substitute
    (zero-width space inserted inside the pipes) so the text still reads the same to a human but no
    longer matches tiktoken's disallowed-special-token pattern. Only touches these 5 exact strings."""
    for token in _TIKTOKEN_SPECIAL_TOKENS:
        if token in content:
            content = content.replace(token, token.replace("|", "​|", 1))
    return content


def _zero_filled_index_files(working_dir: str) -> list[str]:
    """Names of LightRAG index files whose first bytes are all NUL (what a crash mid-write leaves on NTFS)."""
    bad: list[str] = []
    try:
        for p in sorted(Path(working_dir).glob("*")):
            if p.is_file() and p.stat().st_size > 0:
                with open(p, "rb") as fh:
                    head = fh.read(64)
                if head and not head.strip(bytes(1)):
                    bad.append(p.name)
    except OSError:
        pass
    return bad


class PermissionDeniedError(PermissionError):
    pass


class ObsidianSync:
    def __init__(self, vault_path: Path | None = None):
        self._vault = Path(vault_path or CONFIG["vault_path"])
        self._cfg = CONFIG.get("obsidian", {})
        self._protected = set(self._cfg.get("protected_paths", [
            "CLAUDE.md", "GOALS.md", "VECTOR", "graphify-out", ".obsidian",
        ]))
        self._vector_folders = set(self._cfg.get("vector_write_folders", [
            "Daily", "Reflections", "Council", "Agent HP", "Research", "Interviews",
        ]))
        self._personal_folders = set(self._cfg.get("personal_write_folders", [
            "00 Notes", "01 Journals", "02 Projects", "03 Reviews", "04 Skills", "wiki",
        ]))
        self._rag = None
        self._QueryParam = None
        self._memory = None
        self._watching = False
        self._rag_failed_at: float | None = None
        logger.info(f"[VECTOR][obsidian] vault={self._vault}")

    # â”€â”€ Permission helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _is_protected(self, path: Path) -> bool:
        try:
            rel = path.relative_to(self._vault)
        except ValueError:
            return True  # outside vault = protected
        parts = rel.parts
        if not parts:
            return True
        top = parts[0]
        return top in self._protected or str(rel) in self._protected

    def _folder_level(self, folder: str) -> str:
        """Returns 'green', 'yellow', or 'forbidden'."""
        if folder in self._vector_folders or folder == ".":
            return "green"
        if folder in self._personal_folders:
            return "yellow"
        return "forbidden"

    # â”€â”€ Write path â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def write_note(
        self,
        title: str,
        content: str,
        folder: str,
        tags: list[str],
        overwrite: bool = False,
        _bypass_gateway: bool = False,
    ) -> Path:
        """
        Write a note to the vault. Atomic (tmp → rename).
        Raises PermissionDeniedError for protected paths or un-gated personal writes.
        """
        target_dir = self._vault / folder
        target = target_dir / f"{title}.md"

        if self._is_protected(target):
            raise PermissionDeniedError(f"Protected path: {target}")

        level = self._folder_level(folder)
        if level == "forbidden":
            raise PermissionDeniedError(f"Folder not in any write list: {folder}")

        if level == "yellow" and not _bypass_gateway:
            raise PermissionDeniedError(
                f"Personal folder '{folder}' requires gateway — "
                "use async write_note_via_gateway() instead"
            )

        if level == "yellow" and overwrite and target.exists() and not _bypass_gateway:
            raise PermissionDeniedError(
                f"Overwriting existing personal note '{title}' requires RED gateway confirmation"
            )

        target_dir.mkdir(parents=True, exist_ok=True)
        body = self._build_note(title, content, tags)
        tmp = target.with_suffix(".tmp")
        with _vault_write_lock:  # FIX #15: prevent race conditions between agents
            tmp.write_text(body, encoding="utf-8")
            os.replace(tmp, target)

        logger.info(f"[VECTOR][obsidian] wrote {folder}/{title}.md")
        self._store_event("vault_write", f"{folder}/{title}.md")
        return target

    def append_to_note(
        self, title: str, content: str, folder: str, _bypass_gateway: bool = True
    ) -> bool:
        """Append a timestamped block to an existing note (creates if missing)."""
        target_dir = self._vault / folder
        target = target_dir / f"{title}.md"

        if self._is_protected(target):
            raise PermissionDeniedError(f"Protected path: {target}")

        if not target.exists():
            return bool(
                self.write_note(title, content, folder, [], _bypass_gateway=_bypass_gateway)
            )

        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        block = f"\n\n---\n*{ts}*\n\n{content}"
        with _vault_write_lock:  # FIX #15: prevent race conditions
            with open(target, "a", encoding="utf-8") as f:
                f.write(block)
        logger.info(f"[VECTOR][obsidian] appended to {folder}/{title}.md")
        self._store_event("vault_append", f"{folder}/{title}.md")
        return True

    def _build_note(self, title: str, content: str, tags: list[str]) -> str:
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        tag_str = ", ".join(f'"{t}"' for t in tags) if tags else ""
        frontmatter = (
            f"---\ndate: {ts}\ntags: [{tag_str}]\nsource: vector\ntype: note\n---\n\n"
        )
        return frontmatter + f"# {title}\n\n{content}\n"

    # â”€â”€ Gateway-aware write (async, for personal folders) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def write_note_via_gateway(
        self,
        title: str,
        content: str,
        folder: str,
        tags: list[str],
        overwrite: bool = False,
    ) -> Path:
        """Routes through permission_gateway for personal folder writes.
        YELLOW for new notes, RED for overwriting existing ones."""
        from core.loop.permission_gateway import PermissionGateway, Action

        target = self._vault / folder / f"{title}.md"
        action_type = (
            "overwrite_note_personal"
            if (overwrite and target.exists())
            else "write_note_personal"
        )
        gw = PermissionGateway()
        result = await gw.execute(
            Action(
                action_type=action_type,
                params={"title": title, "folder": folder, "overwrite": overwrite},
                proposed_by="obsidian_sync",
            )
        )
        if not result.approved:
            raise PermissionDeniedError(f"Gateway denied: {result.reason}")

        return self.write_note(title, content, folder, tags, overwrite=overwrite, _bypass_gateway=True)

    # â”€â”€ Memory helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _get_memory(self):
        if self._memory is None:
            try:
                from core.memory.episodic import EpisodicMemory
                self._memory = EpisodicMemory()
            except Exception as e:
                logger.warning(f"[VECTOR][obsidian] episodic memory unavailable: {e}")
        return self._memory

    def _store_event(self, event_type: str, note_path: str) -> None:
        try:
            mem = self._get_memory()
            if mem is None:
                return
            mem.store(
                event_type=event_type,
                content=note_path,
                tags=["obsidian", event_type],
                source="obsidian_sync",
            )
        except Exception as e:
            logger.warning(f"[VECTOR][obsidian] episodic store failed: {e}")

    # â”€â”€ LightRAG â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def _init_rag(self) -> None:
        """Lazy-init LightRAG with Ollama backend. Gracefully degrades on failure."""
        if self._rag is not None:
            return
        # 2026-09-27: a failed init used to be retried (and logged) on every call -- 113 identical warnings in one
        # backend session. Retry at most every _RAG_RETRY_AFTER_S.
        if self._rag_failed_at is not None and time.monotonic() - self._rag_failed_at < _RAG_RETRY_AFTER_S:
            return
        try:
            sys.path.insert(0, str(_LIGHTRAG_PATH))
            from lightrag import LightRAG, QueryParam  # type: ignore
            from lightrag.llm.ollama import ollama_model_complete, ollama_embed  # type: ignore
            from lightrag.utils import EmbeddingFunc  # type: ignore
            from functools import partial

            working_dir = self._cfg.get("lightrag_working_dir", "./data/lightrag_vault")
            Path(working_dir).mkdir(parents=True, exist_ok=True)

            ollama_host = CONFIG["ollama_host"]
            if not ollama_host.startswith("http"):
                ollama_host = "http://" + ollama_host

            rag = LightRAG(
                working_dir=working_dir,
                llm_model_func=ollama_model_complete,
                # Entity extraction = many small LLM calls. Use the genuinely
                # small 'ambient' model (gemma4:e2b, 5.1B). Despite its name,
                # the retired fast fallback was a 24B/15GB model — loading it evicted every
                # other model (OLLAMA_MAX_LOADED_MODELS=1) and starved the voice
                # pipeline's local calls (2026-07-15 fix).
                # 2026-09-27: `vector-ambient` is an intent-classifier persona (its Modelfile makes it answer every prompt with a JSON
                # intent object) and a thinking model, so LightRAG's entity extraction produced ZERO entities and every query came back
                # empty or "[no-context]". LightRAG needs the plain base model with thinking off.
                llm_model_name=self._cfg.get("lightrag_llm_model", "gemma4:e2b"),
                llm_model_kwargs={
                    "host": ollama_host,
                    "options": {"num_ctx": 8192},
                    "timeout": 120,
                    "think": False,
                },
                embedding_func=EmbeddingFunc(
                    embedding_dim=768,
                    max_token_size=8192,
                    func=partial(
                        ollama_embed.func,
                        embed_model=CONFIG["models"]["embed"],
                        host=ollama_host,
                    ),
                ),
            )
            await rag.initialize_storages()
            self._rag = rag
            self._QueryParam = QueryParam
            logger.info("[VECTOR][obsidian] LightRAG initialized")
        except Exception as e:
            self._rag_failed_at = time.monotonic()
            damaged = _zero_filled_index_files(self._cfg.get("lightrag_working_dir", "./data/lightrag_vault"))
            hint = (f" -- index files are zero-filled (crash damage): {', '.join(damaged)}; the vault index must be rebuilt"
                    if damaged else "")
            logger.warning(f"[VECTOR][obsidian] LightRAG init failed (degraded mode): {e}{hint}")

    async def _insert_to_rag(self, content: str) -> None:
        await self._init_rag()
        if self._rag is None:
            return
        try:
            await self._rag.ainsert(_neutralize_special_tokens(content))
        except Exception as e:
            logger.warning(f"[VECTOR][obsidian] LightRAG insert failed: {e}")

    async def query(self, text: str, mode: str = "hybrid") -> str:
        """Hybrid graph query. Returns '' gracefully if LightRAG not ready."""
        await self._init_rag()
        if self._rag is None:
            return ""
        try:
            result = await self._rag.aquery(text, param=self._QueryParam(mode=mode))
            return result or ""
        except Exception as e:
            logger.warning(f"[VECTOR][obsidian] query failed: {e}")
            return ""

    async def ingest_existing(self, folder: str | None = None) -> int:
        """Bulk-ingest existing vault notes. Skips already-ingested (hash in semantic_memory).
        Returns count of newly ingested files."""
        await self._init_rag()
        if self._rag is None:
            return 0

        root = self._vault / folder if folder else self._vault
        count = 0
        mem = self._get_memory()

        _SUPPORTED_EXTS = {
            ".md", ".pdf", ".docx", ".pptx", ".xlsx", ".html",
            ".htm", ".txt", ".csv", ".jpg", ".jpeg", ".png", ".mp3", ".wav",
        }

        for f in root.rglob("*"):
            if f.is_dir() or f.suffix.lower() not in _SUPPORTED_EXTS:
                continue
            if self._is_protected(f):
                continue
            try:
                stat = f.stat()
                file_hash = hashlib.md5(
                    f"{f}:{stat.st_mtime}".encode()
                ).hexdigest()[:12]
                cache_key = f"lightrag_ingested:{file_hash}"

                if mem is not None:
                    existing = mem.recall(cache_key, limit=1)
                    if existing:
                        continue

                ingested = await self.ingest_file(f)
                if ingested:
                    if mem is not None:
                        mem.remember(cache_key, "1", category="lightrag_cache")
                    count += 1
                    logger.debug(f"[VECTOR][obsidian] ingested {f.name}")
            except Exception as e:
                logger.warning(f"[VECTOR][obsidian] ingest failed for {f}: {e}")

        logger.info(f"[VECTOR][obsidian] bulk ingest complete — {count} new files")
        return count

    # â”€â”€ MarkItDown pre-processor â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _to_markdown(self, file_path: Path) -> str | None:
        """
        Convert any file (PDF, DOCX, PPTX, XLSX, images, audio, HTML, YouTube URL)
        to Markdown via markitdown. Returns None gracefully if markitdown is absent
        or the conversion fails.
        """
        try:
            from markitdown import MarkItDown  # type: ignore
            md = MarkItDown()
            result = md.convert(str(file_path))
            return result.text_content if result else None
        except ImportError:
            logger.debug("[VECTOR][obsidian] markitdown not installed — skipping non-md conversion")
            return None
        except Exception as e:
            logger.warning(f"[VECTOR][obsidian] markitdown conversion failed for {file_path}: {e}")
            return None

    async def ingest_file(self, file_path: str | Path) -> bool:
        """
        Universal file ingestor:
        - .md files go directly to LightRAG
        - Everything else is converted to Markdown via markitdown first
        - Falls back to RAGAnything for rich multi-modal files (PDF, images, audio)
        """
        file_path = Path(file_path)
        if self._is_protected(file_path):
            return False

        if file_path.suffix.lower() == ".md":
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                if len(text.strip()) >= 20:
                    await self._insert_to_rag(text)
                    self._store_event("vault_ingest_md", file_path.name)
                    return True
            except Exception as e:
                logger.warning(f"[VECTOR][obsidian] md ingest failed {file_path}: {e}")
            return False

        # Non-markdown: try markitdown first (fast, handles most formats)
        md_text = self._to_markdown(file_path)
        if md_text and len(md_text.strip()) >= 20:
            await self._insert_to_rag(md_text)
            self._store_event("vault_ingest_converted", file_path.name)
            logger.info(f"[VECTOR][obsidian] markitdown ingested {file_path.name}")
            return True

        # Fallback: RAGAnything for rich multi-modal content
        return await self.ingest_to_rag_anything(file_path)

    async def ingest_to_rag_anything(self, file_path: str | Path) -> bool:
        """Multi-modal ingestion (PDF, image, audio) via RagAnything → same LightRAG graph."""
        await self._init_rag()
        if self._rag is None:
            return False
        try:
            sys.path.insert(0, str(_LIGHTRAG_PATH))
            from rag_anything import RAGAnything  # type: ignore  # noqa: F401

            processor = RAGAnything(lightrag=self._rag)
            await processor.process_file(str(file_path))
            logger.info(f"[VECTOR][obsidian] RagAnything ingested {file_path}")
            return True
        except Exception as e:
            logger.warning(f"[VECTOR][obsidian] RagAnything failed: {e}")
            return False

    # â”€â”€ Watchdog â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    async def start_watching(self) -> None:
        """Watch vault for .md changes with 30s debounce per file. Never crashes."""
        if not self._vault.exists():
            logger.warning(f"[VECTOR][obsidian] vault path not found, watcher skipped: {self._vault}")
            return

        import asyncio
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Path] = asyncio.Queue()
        debounce_sec = self._cfg.get("watch_debounce_sec", 30)

        _WATCH_EXTS = {".md", ".pdf", ".docx", ".pptx", ".xlsx", ".html", ".txt"}

        class _Handler(FileSystemEventHandler):
            def on_modified(self_, event):
                p = Path(str(event.src_path))
                if not event.is_directory and p.suffix.lower() in _WATCH_EXTS:
                    loop.call_soon_threadsafe(queue.put_nowait, p)

            def on_created(self_, event):
                self_.on_modified(event)

        observer = Observer()
        observer.schedule(_Handler(), str(self._vault), recursive=True)
        observer.start()
        self._watching = True
        logger.info(f"[VECTOR][obsidian] watching vault: {self._vault}")

        seen: dict[Path, float] = {}

        try:
            while self._watching:
                try:
                    path = await asyncio.wait_for(queue.get(), timeout=1.0)
                    seen[path] = time.monotonic()
                except asyncio.TimeoutError:
                    pass  # idle tick: nothing changed this second, fall through to the debounce sweep

                now = time.monotonic()
                ready = [p for p, t in list(seen.items()) if now - t >= debounce_sec]
                for p in ready:
                    del seen[p]
                    try:
                        if self._is_protected(p):
                            continue
                        await self.ingest_file(p)
                        self._store_event("vault_change", p.name)
                    except Exception as e:
                        logger.warning(f"[VECTOR][obsidian] watch ingest error {p}: {e}")
        finally:
            observer.stop()
            observer.join()
            logger.info("[VECTOR][obsidian] watcher stopped")


if __name__ == "__main__":
    import asyncio
    sys.stdout.reconfigure(encoding="utf-8")
    import tempfile

    async def _smoke():
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            for f in ["Daily", "Reflections", "00 Notes"]:
                (vault / f).mkdir()
            sync = ObsidianSync(vault_path=vault)

            p = sync.write_note("Smoke Test", "Hello VECTOR", "Daily", ["smoke"])
            assert p.exists(), "write_note failed"
            assert "Hello VECTOR" in p.read_text(encoding="utf-8")
            assert "source: vector" in p.read_text(encoding="utf-8")
            assert list(vault.glob("**/*.tmp")) == [], ".tmp file leaked"

            sync.append_to_note("Smoke Test", "appended", "Daily")
            assert "appended" in p.read_text(encoding="utf-8")

            try:
                sync.write_note("CLAUDE", "evil", ".", [], _bypass_gateway=True)
                assert False, "should have raised"
            except PermissionDeniedError:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

            try:
                sync.write_note("journal", "x", "00 Notes", [], _bypass_gateway=False)
                assert False, "should have raised"
            except PermissionDeniedError:
                logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)

            personal_path = sync.write_note("journal", "x", "00 Notes", [], _bypass_gateway=True)
            assert personal_path.exists()

        print("✅ obsidian_sync.py OK")

    asyncio.run(_smoke())
