"""Typed paper ingestion contracts for VECTOR research."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "CitationRef",
    "ExtractionRef",
    "PaperArtifact",
    "PaperCard",
    "PaperInput",
    "PaperNode",
    "ResearchSourceRef",
    "ingest_paper",
    "paper_card",
]


class ResearchSourceRef(BaseModel):
    kind: Literal["arxiv", "url", "local", "text", "doi"]
    uri: str
    title: str = ""


class ExtractionRef(BaseModel):
    method: str = "vector_text_ingestion"
    model: str = "deterministic"
    version: str = "1.0"


class CitationRef(BaseModel):
    source_uri: str
    anchor: str = ""
    quote: str = ""


class PaperNode(BaseModel):
    node_id: str
    title: str
    text: str
    level: int = 1
    citations: list[CitationRef] = Field(default_factory=list)


class PaperArtifact(BaseModel):
    title: str
    as_of: str
    created_at: str
    source: ResearchSourceRef
    extraction: ExtractionRef = Field(default_factory=ExtractionRef)
    content_hash: str
    nodes: list[PaperNode]
    citations: list[CitationRef] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    def embedding_text(self) -> str:
        chunks = [self.title, self.source.uri]
        chunks.extend(node.title + "\n" + node.text for node in self.nodes)
        return "\n\n".join(c for c in chunks if c).strip()


class PaperCard(BaseModel):
    title: str
    source_uri: str
    as_of: str
    content_hash: str
    summary: str
    key_sections: list[str]
    tags: list[str] = Field(default_factory=list)


class PaperInput(BaseModel):
    kind: Literal["arxiv", "url", "local", "text", "doi"]
    value: str
    title: str = ""
    tags: list[str] = Field(default_factory=list)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def ingest_paper(input_data: PaperInput | dict) -> PaperArtifact:
    paper_input = input_data if isinstance(input_data, PaperInput) else PaperInput(**input_data)
    if paper_input.kind == "doi":
        raise ValueError("doi ingestion is deferred until a legal open-access resolver is configured")

    text, source_uri, title = _resolve_input(paper_input)
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    nodes = _build_nodes(text, source_uri)
    if not title:
        title = _infer_title(text, source_uri)

    citations = [CitationRef(source_uri=source_uri, anchor=node.title, quote=node.text[:240]) for node in nodes[:5]]
    return PaperArtifact(
        title=title,
        as_of=now,
        created_at=now,
        source=ResearchSourceRef(kind=paper_input.kind, uri=source_uri, title=title),
        content_hash=content_hash,
        nodes=nodes,
        citations=citations,
        tags=paper_input.tags,
    )


def paper_card(artifact: PaperArtifact) -> PaperCard:
    text = artifact.embedding_text()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    summary = " ".join(sentences[:3]).strip()[:700]
    return PaperCard(
        title=artifact.title,
        source_uri=artifact.source.uri,
        as_of=artifact.as_of,
        content_hash=artifact.content_hash,
        summary=summary,
        key_sections=[node.title for node in artifact.nodes[:8]],
        tags=artifact.tags,
    )


def _resolve_input(paper_input: PaperInput) -> tuple[str, str, str]:
    if paper_input.kind == "text":
        return paper_input.value, "inline:text", paper_input.title
    if paper_input.kind == "local":
        path = Path(paper_input.value).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"paper source not found: {path}")
        if path.suffix.lower() == ".pdf":
            raise ValueError("unsupported_pdf_parser: configure pypdf/pdfplumber extraction before PDF ingestion")
        return path.read_text(encoding="utf-8", errors="replace"), str(path), paper_input.title or path.stem
    if paper_input.kind == "arxiv":
        arxiv_id = paper_input.value.strip()
        return paper_input.title or arxiv_id, f"https://arxiv.org/abs/{arxiv_id}", paper_input.title or arxiv_id
    if paper_input.kind == "url":
        raise ValueError("url ingestion requires live fetch and should be run through the research fetcher")
    raise ValueError(f"unsupported paper input kind: {paper_input.kind}")


def _build_nodes(text: str, source_uri: str) -> list[PaperNode]:
    headings = list(_HEADING_RE.finditer(text))
    if not headings:
        chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
        return [
            PaperNode(
                node_id=f"n{i+1}",
                title="Abstract" if i == 0 else f"Section {i+1}",
                text=chunk[:4000],
                level=1,
                citations=[CitationRef(source_uri=source_uri, anchor=f"chunk:{i+1}", quote=chunk[:240])],
            )
            for i, chunk in enumerate(chunks[:20])
        ] or [PaperNode(node_id="n1", title="Paper", text=text[:4000], level=1)]

    nodes: list[PaperNode] = []
    for i, match in enumerate(headings):
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[start:end].strip()
        title = match.group(2).strip()
        nodes.append(PaperNode(
            node_id=f"n{i+1}",
            title=title,
            text=body[:4000],
            level=len(match.group(1)),
            citations=[CitationRef(source_uri=source_uri, anchor=title, quote=body[:240])],
        ))
    return nodes


def _infer_title(text: str, source_uri: str) -> str:
    heading = _HEADING_RE.search(text)
    if heading:
        return heading.group(2).strip()
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first[:120] or source_uri
