"""
VECTOR Ingestion Queue — async document pipeline feeding the Memory Tree.

Pipeline stages (from vector memory/ingestion/mod.rs):
  1. Chunk      — split document into manageable pieces
  2. Extract    — structured + heuristic entity/relation extraction
  3. Aggregate  — dedup, alias resolution, normalization
  4. Persist    — upsert to MemoryTree
"""
from __future__ import annotations

__all__ = [
    "ExtractionResult",
    "IngestionJob",
    "IngestionQueue",
]


import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from loguru import logger
from core.engine.memory_tree.tree_builder import MemoryTree, TreeChunk


@dataclass
class IngestionJob:
    source_kind: str
    source_id: str
    content: str
    topic: str | None = None
    tags: list[str] | None = None
    score: float = 1.0


@dataclass
class ExtractionResult:
    entities: list[str]
    relations: list[tuple[str, str, str]]   # (subject, relation, object)
    summary: str


def _extract_entities(text: str) -> list[str]:
    """Heuristic entity extraction — capitalized phrases and quoted strings."""
    entities = []
    # Quoted strings
    entities.extend(re.findall(r'"([^"]{3,50})"', text))
    # CamelCase identifiers
    entities.extend(re.findall(r'\b[A-Z][a-zA-Z0-9]{2,}\b', text))
    return list(dict.fromkeys(entities))[:20]


def _extract_relations(text: str) -> list[tuple[str, str, str]]:
    """Simple relation extraction: 'X is Y', 'X uses Y', 'X has Y'."""
    patterns = [
        r'(\w+(?:\s\w+)?)\s+is\s+([\w\s]{3,30})',
        r'(\w+(?:\s\w+)?)\s+uses\s+([\w\s]{3,30})',
        r'(\w+(?:\s\w+)?)\s+has\s+([\w\s]{3,30})',
        r'(\w+(?:\s\w+)?)\s+supports\s+([\w\s]{3,30})',
    ]
    relations = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            subj = m.group(1).strip()
            rel = pat.split(r'\s+')[1].strip('\\s+')
            obj = m.group(2).strip()
            if len(subj) > 1 and len(obj) > 1:
                relations.append((subj, "is/uses/has", obj))
    return relations[:10]


def _extract(text: str) -> ExtractionResult:
    return ExtractionResult(
        entities=_extract_entities(text),
        relations=_extract_relations(text),
        summary=text[:200].replace("\n", " "),
    )


def _deduplicate(chunks: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for c in chunks:
        key = re.sub(r'\s+', ' ', c.lower().strip())[:80]
        if key not in seen:
            seen.add(key)
            result.append(c)
    return result


class IngestionQueue:
    """
    Async ingestion queue — processes documents into MemoryTree.

    Usage:
        q = IngestionQueue(tree)
        await q.enqueue("document", "readme.md", text_content)
        await q.flush()
    """

    def __init__(self, tree: MemoryTree, max_chunk_chars: int = 800) -> None:
        self._tree = tree
        self._max_chunk = max_chunk_chars
        self._queue: asyncio.Queue[IngestionJob] = asyncio.Queue()
        self._callbacks: list[Callable[[list[TreeChunk]], None]] = []

    def on_complete(self, callback: Callable[[list[TreeChunk]], None]) -> None:
        self._callbacks.append(callback)

    async def enqueue(
        self,
        source_kind: str,
        source_id: str,
        content: str,
        topic: str | None = None,
        tags: list[str] | None = None,
        score: float = 1.0,
    ) -> None:
        await self._queue.put(IngestionJob(
            source_kind=source_kind,
            source_id=source_id,
            content=content,
            topic=topic,
            tags=tags,
            score=score,
        ))

    def enqueue_sync(self, source_kind: str, source_id: str, content: str, **kw) -> None:
        self._queue.put_nowait(IngestionJob(source_kind=source_kind, source_id=source_id, content=content, **kw))

    async def flush(self) -> list[TreeChunk]:
        """Process all queued jobs. Returns all ingested chunks."""
        all_chunks: list[TreeChunk] = []
        while not self._queue.empty():
            job = await self._queue.get()
            chunks = await self._process(job)
            all_chunks.extend(chunks)
            self._queue.task_done()
        for cb in self._callbacks:
            cb(all_chunks)
        return all_chunks

    async def run_forever(self, poll_interval: float = 2.0) -> None:
        """Background worker — runs until cancelled."""
        logger.info("[VECTOR][ingestion_queue] background worker started")
        while True:
            try:
                job = await asyncio.wait_for(self._queue.get(), timeout=poll_interval)
                await self._process(job)
                self._queue.task_done()
            except asyncio.TimeoutError:
                pass  # idle poll: no job arrived
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[VECTOR][ingestion_queue] error: {}", e)

    async def _process(self, job: IngestionJob) -> list[TreeChunk]:
        # Stage 1: chunk
        raw_chunks = self._tree._split_text(job.content, self._max_chunk)
        # Stage 2: deduplicate
        chunks = _deduplicate(raw_chunks)
        # Stage 3: extract + ingest
        results: list[TreeChunk] = []
        for chunk_text in chunks:
            if not chunk_text.strip():
                continue
            extraction = _extract(chunk_text)
            tags = (job.tags or []) + extraction.entities[:3]
            c = self._tree.ingest(
                source_kind=job.source_kind,
                source_id=job.source_id,
                content=chunk_text,
                topic=job.topic,
                tags=tags,
                score=job.score,
            )
            results.append(c)
        logger.debug("[VECTOR][ingestion_queue] processed {} chunks from {}", len(results), job.source_id[:20])
        return results


if __name__ == "__main__":
    import tempfile, asyncio

    async def _test():
        with tempfile.TemporaryDirectory() as d:
            tree = MemoryTree(db_dir=Path(d) / "db", wiki_dir=Path(d) / "wiki")
            queue = IngestionQueue(tree)
            await queue.enqueue("document", "test_doc", "VECTOR is an AI system built in Python.\n\nIt uses Ollama for local inference.\n\nThe system has 8 districts.")
            chunks = await queue.flush()
            assert len(chunks) >= 1
        print("OK ingestion_queue.py")

    asyncio.run(_test())
