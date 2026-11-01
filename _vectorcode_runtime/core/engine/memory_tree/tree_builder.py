"""
VECTOR Memory Tree — hierarchical summary tree builder.

Builds a 3-level tree from ingested content:
  Level 0: Source (document/channel/integration)
  Level 1: Topic  (auto-clustered from content)
  Level 2: Chunk  (atomic fact/memory unit)

Each level has a rolling summary kept under token budget.
Writes Obsidian-compatible markdown wikis to brain/.

Ported from vector's memory/tree/ architecture.
"""
from __future__ import annotations

__all__ = [
    "MemorySource",
    "MemoryTree",
    "TreeChunk",
    "TreeNode",
    "get_shared_tree",
    "close_shared_tree",
]


import atexit
import concurrent.futures
import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from loguru import logger

_BRAIN_WIKI = Path("brain") / "VECTOR" / "wiki"
_SAVE_LOCK = threading.Lock()


_LEGACY_TREE_DIR = Path.home() / ".vector_ca" / "memory_tree"


def _default_tree_dir() -> Path:
    """Resolve the default memory-tree directory.

    Mirrors core.memory.db_utils.configured_db_path()'s override precedence
    so tests that isolate VECTOR_DB_PATH isolate the tree too — this used to
    be a hardcoded ~/.vector_ca/memory_tree path, silently un-isolatable,
    which was the root cause of a real 90+s hang under concurrent episodic
    writes (KNOWN_ISSUES: MemoryTree reconstructed + full read/parse/rewrite
    on every single EpisodicMemory.store() call).

    configured_db_path() can legitimately return a RELATIVE path (this
    deployment's own .env sets VECTOR_DB_PATH=vector_memory.db, relative to
    the repo root) — .resolve() is required here, not optional: without it,
    this directory silently depends on whatever the current process's CWD
    happens to be at call time, so two callers launched from different
    directories would each get their own un-synced copy of "the" tree.
    Found live during this fix's own verification: an ad-hoc script run
    from the repo root wrote real episodic data into <repo>/memory_tree/
    instead of the historical ~/.vector_ca/memory_tree/, alongside the
    resolve() bug — .resolve() anchors this to the actual configured DB
    location deterministically, matching where the real SQLite DB already
    lives for this deployment.
    """
    override = os.environ.get("VECTOR_MEMORY_TREE_PATH")
    if override:
        return Path(override).resolve()
    try:
        from core.memory.db_utils import configured_db_path
        return configured_db_path().resolve().parent / "memory_tree"
    except Exception:
        return _LEGACY_TREE_DIR


def _migrate_legacy_tree_if_needed(target_dir: Path) -> None:
    """One-time continuity copy: if the resolved tree dir has no data yet
    but the pre-fix hardcoded default (~/.vector_ca/memory_tree) does,
    copy it over so upgrading doesn't silently orphan real accumulated
    memory-tree data. Copies, never moves or deletes the original — safe
    to run on every startup, a no-op once the target has its own file.
    Never allowed to fail tree construction."""
    try:
        target_file = target_dir / "memory_tree.json"
        legacy_file = _LEGACY_TREE_DIR / "memory_tree.json"
        if target_file.exists() or not legacy_file.exists():
            return
        if target_dir.resolve() == _LEGACY_TREE_DIR.resolve():
            return
        import shutil
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_file, target_file)
        logger.info(
            "[VECTOR][memory_tree] migrated {} -> {} for continuity (original left in place)",
            legacy_file, target_file,
        )
    except Exception as e:
        logger.warning("[VECTOR][memory_tree] legacy migration skipped: {}", e)


# â”€â”€ Data structures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@dataclass
class TreeChunk:
    """Atomic memory unit — a single fact or observation."""
    id: str
    source_kind: str        # "conversation" | "document" | "integration" | "observation"
    source_id: str
    topic: str
    content: str
    created_at: str
    score: float = 1.0      # relevance/importance score
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "TreeChunk":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class TreeNode:
    """Topic-level node containing multiple chunks with a rolling summary."""
    topic: str
    summary: str = ""
    chunks: list[TreeChunk] = field(default_factory=list)
    updated_at: str = ""

    def add_chunk(self, chunk: TreeChunk, max_chunks: int | None = None) -> None:
        self.chunks.append(chunk)
        if max_chunks and len(self.chunks) > max_chunks:
            # Bound unbounded growth (mirrors episodic.py's _memory_buffer
            # deque(maxlen=...) — this tree has no equivalent cap otherwise,
            # and grows forever since every store() ingests here).
            self.chunks = self.chunks[-max_chunks:]
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def chunk_count(self) -> int:
        return len(self.chunks)


@dataclass
class MemorySource:
    """Source-level root containing multiple topic nodes."""
    source_kind: str
    source_id: str
    nodes: dict[str, TreeNode] = field(default_factory=dict)
    global_summary: str = ""
    updated_at: str = ""

    def get_or_create_node(self, topic: str) -> TreeNode:
        if topic not in self.nodes:
            self.nodes[topic] = TreeNode(topic=topic)
        return self.nodes[topic]


# â”€â”€ MemoryTree â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class MemoryTree:
    """
    Hierarchical memory tree: Source → Topic → Chunk.

    Usage:
        tree = MemoryTree()
        tree.ingest("conversation", "session_abc", "Python is great for AI", topic="coding")
        wiki = tree.build_wiki("conversation", "session_abc")
        tree.save_wiki(wiki, "session_abc")
    """

    def __init__(self, db_dir: Path | None = None, wiki_dir: Path | None = None) -> None:
        _using_default_dir = db_dir is None
        self._db_dir = db_dir or _default_tree_dir()
        self._db_dir.mkdir(parents=True, exist_ok=True)
        if _using_default_dir:
            # Only migrate when resolving the real default — an explicit
            # db_dir (tests, other callers) is a deliberate isolated
            # location and must never be seeded from production data.
            _migrate_legacy_tree_if_needed(self._db_dir)
        self._wiki_dir = wiki_dir or _BRAIN_WIKI
        self._sources: dict[str, MemorySource] = {}

        try:
            from core.config import CONFIG
            _mt_cfg = CONFIG.get("memory_tree", {})
        except Exception:
            _mt_cfg = {}
        self._max_chunks_per_topic: int = _mt_cfg.get("max_chunks_per_topic", 2000)
        self._save_every_n: int = _mt_cfg.get("save_every_n_ingests", 20)
        self._save_interval_s: float = _mt_cfg.get("save_interval_seconds", 15)

        self._dirty = False
        self._ingests_since_save = 0
        self._last_save_ts = time.monotonic()
        self._last_saved_stat: tuple[int, int] | None = None

        # Guards mutation of self._sources (ingest()/prune_old_chunks()) so a
        # background save's snapshot pass (_build_snapshot) never reads the
        # tree structure mid-mutation. Cheap: only ever held for in-memory
        # dict/list bookkeeping, never across I/O.
        self._data_lock = threading.Lock()
        # Bookkeeping for the async debounced save (see _queue_async_save).
        self._save_state_lock = threading.Lock()
        self._save_in_flight = False
        self._pending_future: "concurrent.futures.Future | None" = None
        # Exactly one background worker: the disk write this offloads
        # (multi-MB write_text + os.replace, see _write_snapshot) is the
        # actual blocking-I/O hazard being fixed here. Capping at 1 worker
        # means this can never spawn more than a single extra OS thread per
        # MemoryTree instance no matter how fast ingest() debounce trips
        # fire — see _queue_async_save()'s in-flight coalescing.
        self._save_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="memtree-save"
        )

        self._load()

    # â”€â”€ Ingestion â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def ingest(
        self,
        source_kind: str,
        source_id: str,
        content: str,
        topic: str | None = None,
        tags: list[str] | None = None,
        score: float = 1.0,
    ) -> TreeChunk:
        """
        Ingest a piece of content into the memory tree.

        Args:
            source_kind: "conversation" | "document" | "integration" | "observation"
            source_id:   Unique identifier for the source (session ID, file path, etc.)
            content:     Text content to store
            topic:       Topic/category (auto-detected if not provided)
            tags:        Optional tags for retrieval
            score:       Importance score 0.0–1.0

        Returns:
            The created TreeChunk.
        """
        if topic is None:
            topic = self._detect_topic(content)

        chunk = TreeChunk(
            id=self._chunk_id(source_id, content),
            source_kind=source_kind,
            source_id=source_id,
            topic=topic,
            content=content,
            created_at=datetime.now(timezone.utc).isoformat(),
            score=score,
            tags=tags or [],
        )

        key = f"{source_kind}:{source_id}"
        with self._data_lock:
            if key not in self._sources:
                self._sources[key] = MemorySource(source_kind=source_kind, source_id=source_id)

            source = self._sources[key]
            node = source.get_or_create_node(topic)
            node.add_chunk(chunk, max_chunks=self._max_chunks_per_topic)
            source.updated_at = datetime.now(timezone.utc).isoformat()

        # Debounced save: a full read/parse/rewrite of the whole tree file on
        # EVERY ingest() was the original root cause of a real 90+s hang
        # under concurrent EpisodicMemory.store() calls (200 calls x
        # full-file round-trip each). Save every N ingests or every T
        # seconds, whichever first — but the write itself is now handed off
        # to a background thread (_queue_async_save) instead of running
        # inline here, because even a DEBOUNCED synchronous write_text() +
        # os.replace() of a multi-MB file was later found to be able to
        # block the caller indefinitely (KNOWN_ISSUES #0: this call chain,
        # reached from governor.dispatch() on the autonomous loop's single
        # event-loop thread, is the suspected cause of a 5.5h loop stall —
        # 0% CPU, no exception, last log line was exactly this ingest()).
        # flush() is available for a guaranteed durable, synchronous
        # checkpoint (used on shutdown). MemoryTree ingestion is already
        # best-effort/non-fatal from episodic.py's perspective (the SQL
        # episodic_memory table is the real source of truth, written first
        # via get_temp_cursor() before this is ever reached) so a save that
        # is merely DELAYED by being queued behind a slow prior write is an
        # acceptable tradeoff — see _queue_async_save() for exactly what is
        # and is not guaranteed about a queued save actually landing.
        self._dirty = True
        self._ingests_since_save += 1
        now = time.monotonic()
        if (
            self._ingests_since_save >= self._save_every_n
            or (now - self._last_save_ts) >= self._save_interval_s
        ):
            self._queue_async_save()
        logger.debug("[VECTOR][memory_tree] ingested chunk topic={} source={}", topic, source_id[:16])
        return chunk

    def flush(self) -> bool:
        """Force a save and BLOCK until it is durably on disk.

        Unlike the debounced auto-save triggered from ingest() (which is
        offloaded to a background thread so callers never block — see
        _queue_async_save()), flush() is the explicit, synchronous,
        guaranteed-durable path: used by close()/close_shared_tree()/atexit
        on shutdown and by callers (tests, prune_old_chunks()) that need to
        know the write has actually landed before proceeding.

        Waits for any save already in flight on the background thread first
        (so this doesn't race its own writer), then performs one final
        synchronous save of anything still dirty (e.g. ingested after that
        in-flight snapshot was taken). Returns True if a save happened.
        """
        pending = self._pending_future
        if pending is not None:
            try:
                pending.result(timeout=30)
            except Exception as e:
                logger.warning(
                    "[VECTOR][memory_tree] pending background save did not "
                    "finish before flush() (waited 30s): {} — proceeding "
                    "with a fresh synchronous save anyway", e,
                )
        if self._dirty:
            self._save()
            return True
        return False

    def close(self) -> None:
        """Full shutdown: guarantee durability, then release the background
        save thread. Wired into close_shared_tree() / atexit so a graceful
        process exit never drops pending MemoryTree state and never leaks
        the save-executor thread. Safe to call multiple times."""
        try:
            self.flush()
        finally:
            self._save_executor.shutdown(wait=True, cancel_futures=False)

    def ingest_document(
        self,
        source_id: str,
        text: str,
        max_chunk_chars: int = 800,
        source_kind: str = "document",
    ) -> list[TreeChunk]:
        """Split a document into chunks and ingest each."""
        chunks = self._split_text(text, max_chunk_chars)
        results = []
        for chunk_text in chunks:
            if chunk_text.strip():
                results.append(self.ingest(source_kind, source_id, chunk_text))
        logger.info("[VECTOR][memory_tree] ingested {} chunks from {}", len(results), source_id[:40])
        return results

    # â”€â”€ Query â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def query(
        self,
        query: str,
        source_kind: str | None = None,
        topic: str | None = None,
        top_k: int = 10,
    ) -> list[TreeChunk]:
        """Simple keyword search across all chunks."""
        keywords = set(query.lower().split())
        scored: list[tuple[float, TreeChunk]] = []

        for key, source in self._sources.items():
            if source_kind and source.source_kind != source_kind:
                continue
            for t, node in source.nodes.items():
                if topic and t != topic:
                    continue
                for chunk in node.chunks:
                    text_lower = chunk.content.lower()
                    hits = sum(1 for kw in keywords if kw in text_lower)
                    if hits:
                        scored.append((hits * chunk.score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:top_k]]

    def get_topics(self, source_kind: str | None = None) -> list[str]:
        topics: set[str] = set()
        for key, source in self._sources.items():
            if source_kind and source.source_kind != source_kind:
                continue
            topics.update(source.nodes.keys())
        return sorted(topics)

    def get_chunks(self, source_kind: str, source_id: str, topic: str | None = None) -> list[TreeChunk]:
        key = f"{source_kind}:{source_id}"
        source = self._sources.get(key)
        if not source:
            return []
        if topic:
            return source.nodes.get(topic, TreeNode(topic=topic)).chunks
        return [c for node in source.nodes.values() for c in node.chunks]

    # â”€â”€ Wiki builder â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def build_wiki(self, source_kind: str, source_id: str) -> str:
        """Build an Obsidian-compatible markdown wiki for a source."""
        key = f"{source_kind}:{source_id}"
        source = self._sources.get(key)
        if not source:
            return f"# {source_id}\n\nNo memory tree data yet.\n"

        lines = [
            f"# Memory Tree — {source_id}",
            f"*Source: {source_kind} | Updated: {source.updated_at[:10]}*",
            "",
        ]

        for topic, node in sorted(source.nodes.items()):
            lines.append(f"## {topic.replace('_', ' ').title()}")
            if node.summary:
                lines.append(f"> {node.summary}")
                lines.append("")
            for chunk in node.chunks[-10:]:  # last 10 per topic
                lines.append(f"- {chunk.content}")
            lines.append("")

        return "\n".join(lines)

    def save_wiki(self, wiki_content: str, name: str) -> Path:
        """Save wiki to brain/ as Obsidian markdown."""
        safe = re.sub(r"[^\w\-]", "_", name)[:50]
        path = self._wiki_dir / f"{safe}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(wiki_content, encoding="utf-8")
        logger.info("[VECTOR][memory_tree] wiki saved: {}", path)
        return path

    def build_and_save_all(self) -> list[Path]:
        """Build + save wikis for all sources."""
        paths = []
        for key, source in self._sources.items():
            wiki = self.build_wiki(source.source_kind, source.source_id)
            paths.append(self.save_wiki(wiki, source.source_id))
        return paths

    # â”€â”€ Topic detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    _TOPIC_KEYWORDS = {
        "coding": {"code", "function", "class", "error", "debug", "python", "rust", "api", "git"},
        "research": {"paper", "study", "research", "found", "analysis", "data", "model"},
        "finance": {"money", "budget", "cost", "price", "stock", "crypto", "payment", "invoice"},
        "health": {"sleep", "exercise", "diet", "fatigue", "energy", "health", "mood"},
        "goals": {"goal", "want", "plan", "achieve", "target", "milestone", "progress"},
        "learning": {"learn", "course", "skill", "read", "study", "understand", "practice"},
        "relationships": {"friend", "family", "colleague", "meeting", "conversation", "message"},
        "tasks": {"todo", "task", "deadline", "complete", "finish", "done", "working"},
    }

    def _detect_topic(self, content: str) -> str:
        words = set(content.lower().split())
        best, best_score = "general", 0
        for topic, keywords in self._TOPIC_KEYWORDS.items():
            score = len(words & keywords)
            if score > best_score:
                best, best_score = topic, score
        return best

    # â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @staticmethod
    def _chunk_id(source_id: str, content: str) -> str:
        raw = f"{source_id}:{content[:100]}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _split_text(text: str, max_chars: int) -> list[str]:
        paragraphs = re.split(r"\n{2,}", text.strip())
        chunks: list[str] = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) > max_chars and current:
                chunks.append(current.strip())
                current = para
            else:
                current = (current + "\n\n" + para).strip() if current else para
        if current:
            chunks.append(current.strip())
        return chunks

    # â”€â”€ Persistence â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _db_path(self) -> Path:
        return self._db_dir / "memory_tree.json"

    def _build_snapshot(self) -> dict:
        """Serialize the current in-memory tree into a plain JSON-able dict.

        Caller should hold self._data_lock while calling this (both
        _queue_async_save() and _save() do) so the snapshot is internally
        consistent even if another thread is mid-ingest(). This is pure CPU
        work over already-in-memory objects — no I/O — so it is safe to run
        on the calling thread without risking an indefinite block; the part
        that CAN hang indefinitely (write_text + os.replace of a
        multi-MB file, e.g. under antivirus/disk contention) is
        _write_snapshot(), which runs off-thread in the normal path.
        """
        data = {}
        for key, source in self._sources.items():
            data[key] = {
                "source_kind": source.source_kind,
                "source_id": source.source_id,
                "global_summary": source.global_summary,
                "updated_at": source.updated_at,
                "nodes": {
                    topic: {
                        "summary": node.summary,
                        "updated_at": node.updated_at,
                        "chunks": [c.to_dict() for c in node.chunks],
                    }
                    for topic, node in source.nodes.items()
                },
            }
        return data

    def _write_snapshot(self, data: dict) -> None:
        """The actual (potentially slow) disk write for a snapshot already
        captured by _build_snapshot(). Runs on the background save-executor
        thread in the normal (debounced auto-save) path; also called
        synchronously from _save() (flush()/shutdown/explicit callers).

        Atomic write: plain write_text over the live file left torn JSON
        when the autonomous loop, MCP server, and tests saved concurrently
        ("Extra data" / empty-file corruption, found 2026-07-08). temp +
        os.replace is atomic on Windows and POSIX; _SAVE_LOCK serializes
        writers WITHIN this process only (it is a threading.Lock, no
        protection against a second OS process — deliberate, this store's
        documented architecture is in-process singleton, see
        autonomous_loop) — but it does matter now that a background save
        can be in flight at the same time a synchronous flush() call fires
        on another thread; without this lock those two writes could
        interleave their write_text() calls into the same tmp-file path
        collision window. This best-effort mtime/size check just makes a
        lost update loud instead of silent.
        """
        path = self._db_path()
        try:
            if self._last_saved_stat is not None and path.exists():
                st = path.stat()
                if (st.st_mtime_ns, st.st_size) != self._last_saved_stat:
                    logger.warning(
                        "[VECTOR][memory_tree] {} was modified by another writer since this "
                        "process's last save — this save will overwrite it (last-writer-wins, no merge)",
                        path,
                    )
        except Exception:
            pass

        tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
        with _SAVE_LOCK:
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp, path)
            try:
                st = path.stat()
                self._last_saved_stat = (st.st_mtime_ns, st.st_size)
            except Exception:
                self._last_saved_stat = None

    def _save(self) -> None:
        """Synchronous, blocking, guaranteed-durable save — builds a fresh
        snapshot and writes it on the CALLING thread. Used by flush() (and
        therefore close()/close_shared_tree()/atexit/tests), never by the
        debounced auto-save inside ingest() — that path uses
        _queue_async_save() instead so the caller never blocks on I/O."""
        with self._data_lock:
            data = self._build_snapshot()
        self._write_snapshot(data)
        self._dirty = False
        self._ingests_since_save = 0
        self._last_save_ts = time.monotonic()

    def _queue_async_save(self) -> None:
        """Non-blocking debounced save: snapshot the tree cheaply on the
        calling thread, then hand the slow part (disk write) off to a
        single-worker background executor so the caller — typically the
        autonomous loop's event-loop thread via
        EpisodicMemory.store() -> ingest() -> here — never blocks on
        write_text()/os.replace(). This is the fix for KNOWN_ISSUES #0's
        suspected root cause: a stalled synchronous write on this exact
        call chain blocking the whole loop thread for hours.

        DURABILITY CONTRACT (read before assuming more than this promises):
          - The SQL `episodic_memory` table, written synchronously via
            get_temp_cursor() in EpisodicMemory.store() BEFORE this is ever
            reached, is the real source of truth. MemoryTree is always a
            best-effort DERIVED index on top of it — this was true before
            this fix and remains true after.
          - Once a snapshot is captured and its save is accepted onto the
            executor's queue, it WILL be written (the executor's single
            worker processes every submitted job; nothing is silently
            dropped from the queue). If the write itself raises, the
            exception is caught in _on_save_done() and self._dirty is set
            back to True so the NEXT debounce trip (or an explicit
            flush()) retries it — a failed write is retried, not lost.
          - What is NOT guaranteed: a save that is only QUEUED (not yet
            written) at the moment of an ungraceful process kill (SIGKILL,
            power loss, crash) is lost — exactly the same
            best-effort-relative-to-SQL guarantee the old synchronous
            debounce already documented (losing "the last few seconds of
            this derived index"). What changes with this fix is only WHEN
            the write happens (off-thread, possibly slightly delayed
            behind a prior slow write) — not whether an ungraceful kill can
            lose it. flush()/close()/close_shared_tree() (wired to atexit)
            remain the only path that guarantees a GRACEFUL shutdown does
            not drop pending state.
          - At most one save is ever in flight per MemoryTree instance
            (self._save_in_flight, checked under _save_state_lock) and the
            executor itself is capped at max_workers=1 — this can never
            spawn more than a single extra OS thread for this tree no
            matter how fast ingest() debounce trips fire. If a save is
            already in flight when this is called, this is a cheap no-op:
            the new data is already marked dirty and will be picked up by
            a future debounce trip (ingests keep accumulating against
            self._sources normally; nothing about ingest() itself blocks).
        """
        with self._save_state_lock:
            if self._save_in_flight:
                return
            self._save_in_flight = True

        with self._data_lock:
            snapshot = self._build_snapshot()

        self._dirty = False
        self._ingests_since_save = 0
        self._last_save_ts = time.monotonic()

        try:
            future = self._save_executor.submit(self._write_snapshot, snapshot)
        except RuntimeError:
            # Executor already shut down (e.g. close() ran concurrently with
            # a final ingest) — write synchronously right here rather than
            # silently dropping this snapshot. Still off the debounce's
            # normal fast path, but correctness (never lose an accepted
            # snapshot) wins over the no-block guarantee in this edge case.
            with self._save_state_lock:
                self._save_in_flight = False
            self._write_snapshot(snapshot)
            return

        self._pending_future = future
        future.add_done_callback(self._on_save_done)

    def _on_save_done(self, future: "concurrent.futures.Future") -> None:
        exc = future.exception()
        if exc is not None:
            logger.error(
                "[VECTOR][memory_tree] background save failed: {} — marking "
                "dirty again so the next debounce trip or flush() retries it",
                exc,
            )
            self._dirty = True
        with self._save_state_lock:
            self._save_in_flight = False
            if self._pending_future is future:
                self._pending_future = None

    def _cleanup_orphaned_tmp_files(self, p: Path) -> None:
        """Best-effort removal of memory_tree.json.tmp<pid> siblings left by a
        process that was killed mid-_save() (evidence: a 19.6MB orphaned tmp
        file was found live on this machine during investigation of the I/O
        hang this fix addresses). Never allowed to fail _load()."""
        try:
            import psutil
        except ImportError:
            return
        try:
            for tmp_file in p.parent.glob(f"{p.name}.tmp*"):
                suffix = tmp_file.name.rsplit(".tmp", 1)[-1]
                if not suffix.isdigit():
                    continue
                pid = int(suffix)
                if not psutil.pid_exists(pid):
                    tmp_file.unlink(missing_ok=True)
                    logger.warning("[VECTOR][memory_tree] removed orphaned tmp file from dead pid {}: {}", pid, tmp_file)
        except Exception:
            pass

    def _load(self) -> None:
        p = self._db_path()
        self._cleanup_orphaned_tmp_files(p)
        if not p.exists():
            return
        try:
            raw = p.read_text(encoding="utf-8")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                # Salvage pre-atomic-write corruption: torn files often hold a valid
                # JSON prefix followed by stale trailing bytes — recover the prefix
                # instead of dropping the whole tree.
                data, end = json.JSONDecoder().raw_decode(raw)
                logger.warning(
                    "[VECTOR][memory_tree] salvaged valid JSON prefix from corrupt file "
                    f"({end}/{len(raw)} chars) — will be rewritten atomically on next save"
                )
            for key, sd in data.items():
                source = MemorySource(
                    source_kind=sd["source_kind"],
                    source_id=sd["source_id"],
                    global_summary=sd.get("global_summary", ""),
                    updated_at=sd.get("updated_at", ""),
                )
                for topic, nd in sd.get("nodes", {}).items():
                    node = TreeNode(
                        topic=topic,
                        summary=nd.get("summary", ""),
                        updated_at=nd.get("updated_at", ""),
                    )
                    for cd in nd.get("chunks", []):
                        try:
                            node.chunks.append(TreeChunk.from_dict(cd))
                        except Exception:
                            logger.warning("[VECTOR] suppressed exception (degraded mode)", exc_info=True)
                    source.nodes[topic] = node
                self._sources[key] = source
        except Exception as e:
            logger.warning("[VECTOR][memory_tree] load failed: {}", e)

    # ── Retention ──────────────────────────────────────────────────────────

    def prune_old_chunks(self, retention_days: int = 90) -> int:
        """Drop chunks older than retention_days, across all sources/topics.

        Modeled on EpisodicMemory.prune_old_episodes() — the tree had no
        equivalent bound before, unlike episodic.py's own bounded
        _memory_buffer, so it grew forever (~20MB/42k chunks observed on one
        machine before this fix). Returns the number of chunks removed.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        removed = 0
        with self._data_lock:
            for source in self._sources.values():
                for node in source.nodes.values():
                    kept = []
                    for chunk in node.chunks:
                        try:
                            created = datetime.fromisoformat(chunk.created_at)
                            if created.tzinfo is None:
                                created = created.replace(tzinfo=timezone.utc)
                        except (ValueError, TypeError):
                            kept.append(chunk)
                            continue
                        if created >= cutoff:
                            kept.append(chunk)
                        else:
                            removed += 1
                    node.chunks = kept
        if removed:
            self._dirty = True
            self.flush()
            logger.info("[VECTOR][memory_tree] pruned {} chunks older than {}d", removed, retention_days)
        return removed


# ── Shared singleton ─────────────────────────────────────────────────────────
# Mirrors core.memory.episodic._db_connection / _db_lock exactly. Confirmed
# safe: the only other direct MemoryTree() construction sites
# (wiki_formatter.py, ingestion_queue.py) already accept an explicit `tree`
# instance from their caller rather than constructing their own, so this
# singleton only changes behavior for callers that used to construct a
# fresh (and therefore always-reloading) MemoryTree() with defaults, which
# in production is only core.memory.episodic.EpisodicMemory.store().

_tree_singleton: "MemoryTree | None" = None
_tree_lock = threading.Lock()


def get_shared_tree(db_dir: Path | None = None, wiki_dir: Path | None = None) -> "MemoryTree":
    global _tree_singleton
    with _tree_lock:
        if _tree_singleton is None:
            _tree_singleton = MemoryTree(db_dir=db_dir, wiki_dir=wiki_dir)
            # close() (not just flush()) so a graceful process exit also
            # waits for any in-flight background save and shuts down the
            # save-executor thread cleanly instead of leaking it.
            atexit.register(_tree_singleton.close)
        return _tree_singleton


def close_shared_tree() -> None:
    """Mirrors close_db_connection(): intentional reset for tests/shutdown.
    Calls close() (flush any pending/dirty state, then shut down the
    per-instance background save thread) rather than just flush(), so
    repeated get_shared_tree()/close_shared_tree() cycles — e.g. across many
    test files — never accumulate live save-executor threads."""
    global _tree_singleton
    with _tree_lock:
        if _tree_singleton is not None:
            try:
                _tree_singleton.close()
            except Exception:
                logger.warning("[VECTOR][memory_tree] close() failed", exc_info=True)
            _tree_singleton = None


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tree = MemoryTree(db_dir=Path(d) / "db", wiki_dir=Path(d) / "wiki")
        tree.ingest("conversation", "sess_001", "Python is great for building AI agents", topic="coding")
        tree.ingest("conversation", "sess_001", "VECTOR uses Ollama for local inference", topic="coding")
        tree.ingest("document", "paper_001", "Transformer architecture uses attention mechanisms", topic="research")
        chunks = tree.query("Python AI", top_k=5)
        assert len(chunks) >= 1
        wiki = tree.build_wiki("conversation", "sess_001")
        assert "coding" in wiki.lower()
        p = tree.save_wiki(wiki, "sess_001")
        assert p.exists()

        # Growth bound + retention (new this pass)
        for i in range(50):
            tree.ingest("test", "cap_test", f"chunk {i}", topic="capped")
        tree._max_chunks_per_topic = 10
        tree._sources["test:cap_test"].nodes["capped"].add_chunk(
            TreeChunk(id="extra", source_kind="test", source_id="cap_test",
                      topic="capped", content="overflow", created_at=datetime.now(timezone.utc).isoformat()),
            max_chunks=10,
        )
        assert len(tree._sources["test:cap_test"].nodes["capped"].chunks) == 10, "per-topic cap not enforced"

        tree.flush()

        # Singleton identity
        t1 = get_shared_tree(db_dir=Path(d) / "singleton", wiki_dir=Path(d) / "wiki2")
        t2 = get_shared_tree()
        assert t1 is t2, "get_shared_tree() must return the same instance"
        close_shared_tree()
        t3 = get_shared_tree(db_dir=Path(d) / "singleton", wiki_dir=Path(d) / "wiki2")
        assert t3 is not t1, "close_shared_tree() must reset the singleton"
        close_shared_tree()
    print("OK memory_tree/tree_builder.py")
