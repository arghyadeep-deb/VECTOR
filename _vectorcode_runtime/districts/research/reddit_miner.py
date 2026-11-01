import sys
import uuid
import asyncio
import datetime
import os
from pathlib import Path

from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.memory.episodic import EpisodicMemory
from core.memory.obsidian_sync import ObsidianSync
from core.loop.context_engine import ContextEngine
from loguru import logger

# Target subreddits — read-only JSON API, no OAuth needed
_SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA",
    "entrepreneur",
    "learnprogramming",
    "cscareerquestions",
]


class RedditMiner(AgentBase):
    """
    Mines Reddit for tech/AI trends and startup opportunities.
    Uses Reddit's public JSON API (no OAuth required for read).
    Stores hot posts in Obsidian Research/ and semantic_memory.
    """

    REDDIT_BASE = "https://www.reddit.com/r/{sub}/hot.json"

    def __init__(self, generation: int = 1, ghost: dict | None = None):
        super().__init__(
            agent_id=str(uuid.uuid4()),
            name="RedditMiner",
            district="research",
            generation=generation,
        )
        self.capabilities = ["reddit", "research", "search"]
        if ghost:
            self.inherit_ghost(ghost)
        self._memory = EpisodicMemory()
        self._obsidian = ObsidianSync()
        self._context = ContextEngine()
        logger.info(f"[VECTOR][reddit_miner] ready gen={generation} hp={self.health_points}")

    # ── Fetch ──────────────────────────────────────────────────────────────────

    async def fetch_hot(self, subreddit: str, limit: int = 10) -> list[dict]:
        """Fetch hot posts from a subreddit via public JSON endpoint."""
        try:
            import httpx
            url = self.REDDIT_BASE.format(sub=subreddit)
            headers = {"User-Agent": "VECTOR/1.0 (research bot; contact arghyadeep)"}
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                r = await client.get(url, params={"limit": limit}, headers=headers)
            if r.status_code != 200:
                logger.warning(f"[VECTOR][reddit_miner] r/{subreddit} HTTP {r.status_code}")
                return []
            data = r.json()
            posts = []
            for child in data.get("data", {}).get("children", []):
                p = child.get("data", {})
                if p.get("stickied"):
                    continue
                posts.append({
                    "title": p.get("title", ""),
                    "score": p.get("score", 0),
                    "url": f"https://reddit.com{p.get('permalink', '')}",
                    "flair": p.get("link_flair_text") or "",
                    "comments": p.get("num_comments", 0),
                    "subreddit": subreddit,
                    "selftext": (p.get("selftext") or "")[:300],
                })
            logger.info(f"[VECTOR][reddit_miner] r/{subreddit} → {len(posts)} posts")
            return posts
        except Exception as e:
            logger.warning(f"[VECTOR][reddit_miner] r/{subreddit} failed: {e}")
            return []

    async def mine_all(self, posts_per_sub: int = 8) -> list[dict]:
        """Mine all configured subreddits concurrently."""
        tasks = [self.fetch_hot(sub, limit=posts_per_sub) for sub in _SUBREDDITS]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_posts: list[dict] = []
        for r in results:
            if isinstance(r, list):
                all_posts.extend(r)
        all_posts.sort(key=lambda p: p["score"], reverse=True)
        logger.info(f"[VECTOR][reddit_miner] total {len(all_posts)} posts from {len(_SUBREDDITS)} subs")
        return all_posts

    async def intelligence_report(self) -> bool:
        """
        Mine Reddit, extract top signals, write to Obsidian Research/.
        Stores opportunity signals in semantic_memory.
        """
        posts = await self.mine_all(posts_per_sub=8)
        date_str = datetime.date.today().isoformat()

        if not posts:
            logger.warning("[VECTOR][reddit_miner] no posts fetched")
            self.deduct_points(10, "no posts fetched")
            return False

        hydration = self._context.session_hydration_prompt()  # RULE 1

        # LLM extracts 3 opportunity signals
        top_titles = "\n".join(
            f"r/{p['subreddit']} [{p['score']}↑]: {p['title']}"
            for p in posts[:20]
        )
        opportunities = ""
        try:
            if os.getenv("VECTOR_REDDIT_MINER_LLM") != "1":
                raise RuntimeError("LLM disabled; set VECTOR_REDDIT_MINER_LLM=1 to enable")
            from core.inference.vectorcode_llm import chat
            opportunities = chat(
                model=CONFIG["models"]["reasoning"],
                messages=[
                    {"role": "system", "content": hydration},
                    {
                        "role": "user",
                        "content": (
                            "From these Reddit posts, identify 3 actionable insights or opportunities "
                            "for a CS student building AI tools. Be specific.\n\n" + top_titles
                        ),
                    },
                ],
                timeout=2.0,
            )
            if not opportunities:
                raise RuntimeError("empty model response")
        except Exception as e:
            logger.warning(f"[VECTOR][reddit_miner] LLM unavailable: {e}")
            opportunities = "\n".join(f"- {p['title']}" for p in posts[:5])

        # Build note
        lines = [f"## Reddit Intelligence — {date_str}\n", "### Top Signals\n"]
        for p in posts[:10]:
            lines.append(f"- **[{p['title']}]({p['url']})** — r/{p['subreddit']} ({p['score']}↑)")
        lines.append(f"\n### Opportunities\n\n{opportunities}")
        note_content = "\n".join(lines)

        # Store opportunity signals in semantic_memory
        self._memory.remember(
            key=f"reddit_opportunities:{date_str}",
            value=opportunities[:500],
            category="opportunity",
            confidence=0.65,
        )
        self._memory.store(
            event_type="reddit_brief",
            content=f"RedditMiner intelligence report — {len(posts)} posts",
            tags=["research", "reddit", "opportunities"],
            source="reddit_miner",
        )
        self._memory.store_chain(
            situation="reddit_intelligence",
            goal_ids=["find_opportunities"],
            steps=["mine_subreddits", "extract_signals", "write_vault"],
            action="intelligence_report",
            outcome=f"{len(posts)} posts mined",
            reward=0.75,
        )

        try:
            self._obsidian.write_note(
                title=f"Reddit Intel — {date_str}",
                content=note_content,
                folder="Research",
                tags=["reddit", "intel", "opportunities", "vector"],
            )
            self.award_points(35, f"reddit intel: {len(posts)} posts")
            logger.info(f"[VECTOR][reddit_miner] report written: {len(posts)} posts")
            return True
        except Exception as e:
            logger.error(f"[VECTOR][reddit_miner] vault write failed: {e}")
            self.deduct_points(15, "vault write failed")
            return False

    # ── Loop ──────────────────────────────────────────────────────────────────

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        posts = await self.mine_all(p.get("posts_per_sub", 8))
        return {"status": "ok", "posts": posts, "count": len(posts)}

    async def run_forever(self) -> None:
        """Daily intelligence report at 07:10. RULE 2 — never crashes."""
        logger.info("[VECTOR][reddit_miner] run_forever started — daily at 07:10")
        while self.is_alive:
            try:
                now = datetime.datetime.now()
                if now.hour == 7 and 10 <= now.minute < 15:
                    await self.intelligence_report()
            except Exception as e:
                logger.error(f"[VECTOR][reddit_miner] tick error: {e}")
                self.deduct_points(10, "tick error")

            for _ in range(300):
                if not self.is_alive:
                    break
                await asyncio.sleep(60)

        logger.warning("[VECTOR][reddit_miner] died — HP=0")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    async def _smoke():
        bot = RedditMiner()
        assert bot.health_points == 500
        assert bot.name == "RedditMiner"

        import tempfile
        with tempfile.TemporaryDirectory() as d:
            vault = Path(d)
            (vault / "Research").mkdir()
            bot._obsidian._vault = vault

            ok = await bot.intelligence_report()
            assert isinstance(ok, bool)

        print(f"✅ reddit_miner.py OK  HP={bot.health_points} ok={ok}")

    asyncio.run(_smoke())
