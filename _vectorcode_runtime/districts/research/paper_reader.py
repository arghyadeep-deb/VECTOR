import sys
import uuid
import asyncio
import datetime
from pathlib import Path

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from loguru import logger


class PaperReader(AgentBase):
    """
    Fetches and summarizes AI/ML papers from ArXiv.
    Uses ArXiv Atom API (no key required).
    Daily brief written to Obsidian Research/ folder.
    """

    ARXIV_CATEGORIES = ["cs.AI", "cs.LG", "cs.CL", "cs.CV"]
    ARXIV_BASE = "https://export.arxiv.org/api/query"

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="PaperReader",
            district="research",
            generation=generation,
        )
        self.capabilities = ["paper", "research", "search_arxiv"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        logger.info(f"[VECTOR][paper_reader] ready gen={generation} hp={self.health_points}")

    # ── ArXiv fetch ────────────────────────────────────────────────────────────

    async def fetch_recent_papers(
        self, category: str = "cs.AI", max_results: int = 5
    ) -> list[dict]:
        """Fetch recent ArXiv papers. Returns list of {title, authors, abstract, url, id}."""
        try:
            import httpx
            params = {
                "search_query": f"cat:{category}",
                "start": 0,
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(self.ARXIV_BASE, params=params)
            papers = self._parse_arxiv_xml(r.text)
            logger.info(f"[VECTOR][paper_reader] {category} → {len(papers)} papers")
            return papers
        except Exception as e:
            logger.warning(f"[VECTOR][paper_reader] ArXiv fetch failed: {e}")
            return []

    def _parse_arxiv_xml(self, xml: str) -> list[dict]:
        """Parse ArXiv Atom XML response."""
        try:
            import defusedxml.ElementTree as ET
        except ImportError:
            import xml.etree.ElementTree as ET
        papers = []
        try:
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "arxiv": "http://arxiv.org/schemas/atom",
            }
            root = ET.fromstring(xml)
            for entry in root.findall("atom:entry", ns):
                title = (entry.findtext("atom:title", "", ns) or "").strip().replace("\n", " ")
                abstract = (entry.findtext("atom:summary", "", ns) or "").strip()[:500]
                arxiv_id = (entry.findtext("atom:id", "", ns) or "").strip()
                url = arxiv_id
                authors = [
                    a.findtext("atom:name", "", ns)
                    for a in entry.findall("atom:author", ns)
                ][:3]
                if title:
                    papers.append({
                        "title": title,
                        "authors": ", ".join(authors),
                        "abstract": abstract,
                        "url": url,
                        "id": arxiv_id.split("/")[-1],
                    })
        except Exception as e:
            logger.warning(f"[VECTOR][paper_reader] XML parse failed: {e}")
        return papers

    async def daily_brief(self, max_per_category: int = 3) -> bool:
        """Fetch top papers across AI categories → write to Obsidian. Runs at 7AM."""
        all_papers = []
        for cat in self.ARXIV_CATEGORIES[:2]:
            papers = await self.fetch_recent_papers(cat, max_results=max_per_category)
            all_papers.extend(papers)

        if not all_papers:
            logger.warning("[VECTOR][paper_reader] no papers fetched")
            self.deduct_points(15, "no papers fetched")
            return False

        # Deduplicate by id
        seen: set[str] = set()
        unique_papers = []
        for p in all_papers:
            if p["id"] not in seen:
                seen.add(p["id"])
                unique_papers.append(p)

        date_str = datetime.date.today().isoformat()
        lines = [f"## AI/ML Paper Brief — {date_str}\n"]
        for p in unique_papers[:5]:
            lines.append(f"### {p['title']}")
            lines.append(f"*{p['authors']}*")
            lines.append(f"> {p['abstract'][:300]}...")
            lines.append(f"[ArXiv]({p['url']})\n")

        note_content = "\n".join(lines)

        self._memory.store(
            event_type="paper_brief",
            content=f"PaperReader daily brief — {len(unique_papers)} papers",
            tags=["research", "arxiv", "papers"],
            source="paper_reader",
        )
        self._memory.store_chain(
            situation="daily_paper_brief",
            goal_ids=["stay_current"],
            steps=["fetch_arxiv", "deduplicate", "format_brief", "write_vault"],
            action="daily_brief",
            outcome=f"{len(unique_papers)} papers briefed",
            reward=0.85,
        )

        try:
            self._obsidian.write_note(
                title=f"Paper Brief — {date_str}",
                content=note_content,
                folder="Research",
                tags=["research", "arxiv", "papers", "daily", "vector"],
            )
            self.award_points(40, f"paper brief: {len(unique_papers)} papers")
            logger.info(f"[VECTOR][paper_reader] brief written: {len(unique_papers)} papers")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][paper_reader] vault write failed: {e}")
            self.deduct_points(15, "vault write failed")
            return False

    async def search_papers(self, query: str, max_results: int = 5) -> list[dict]:
        """Search ArXiv by keyword."""
        try:
            import httpx
            params = {
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": max_results,
                "sortBy": "relevance",
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(self.ARXIV_BASE, params=params)
            papers = self._parse_arxiv_xml(r.text)
            logger.info(f"[VECTOR][paper_reader] search '{query}' → {len(papers)} papers")
            return papers
        except Exception as e:
            logger.warning(f"[VECTOR][paper_reader] paper search failed: {e}")
            return []

    # ── Loop ──────────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        task_type = task.get("type", "")
        p = task.get("params", {})
        if task_type in {"ingest_paper", "paper_card", "summarize_paper_tree"}:
            try:
                from districts.research.paper_ingestion import ingest_paper, paper_card

                artifact = ingest_paper(p.get("input", p))
                card = paper_card(artifact)
                result = {"status": "ok", "artifact": artifact.model_dump(), "card": card.model_dump()}
                self._memory.store(
                    event_type="paper_ingested",
                    content=f"Paper ingested: {artifact.title}",
                    tags=["research", "paper", "ingestion"],
                    context={"content_hash": artifact.content_hash, "source": artifact.source.uri},
                    source="paper_reader",
                )
                return result
            except Exception as exc:
                return {"status": "error", "error": str(exc)}
        if p.get("query"):
            results = await self.search_papers(p["query"])
            return {"status": "ok", "papers": results}
        results = await self.fetch_recent_papers()
        return {"status": "ok", "papers": results}

    async def run_forever(self) -> None:
        """Daily brief at 07:00. RULE 2 — never crashes."""
        logger.info("[VECTOR][paper_reader] run_forever started — daily at 07:00")
        while self.is_alive:
            try:
                now = datetime.datetime.now()
                if now.hour == 7 and now.minute < 5:
                    await self.daily_brief()
            except Exception as e:
                logger.error(f"[VECTOR][paper_reader] tick error: {e}")
                self.deduct_points(10, "tick error")

            for _ in range(300):
                if not self.is_alive:
                    break
                await asyncio.sleep(60)

        logger.warning("[VECTOR][paper_reader] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        bot = PaperReader()
        assert bot.health_points == 500
        assert bot.name == "PaperReader"

        papers = await bot.fetch_recent_papers("cs.AI", max_results=3)
        assert isinstance(papers, list)

        import tempfile
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            bot._obsidian._vault = vault

            ok = await bot.daily_brief(max_per_category=2)
            if papers:
                assert ok is True
                notes = list((vault / "Research").glob("Paper Brief*.md"))
                assert notes, "No paper brief written"
                assert bot.health_points > 500

        print(f"✅ paper_reader.py OK  HP={bot.health_points} papers={len(papers)}")

    asyncio.run(_smoke())
