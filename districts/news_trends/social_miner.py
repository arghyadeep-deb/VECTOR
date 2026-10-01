"""
Module: agents/news_trends/social_miner.py
District: news_trends | Focus: Mine real user problems from social platforms (last 30 days)

Stage 1 of the Venture Pipeline (see districts/news_trends/venture_pipeline.py).

Sources (free, no API keys, ToS-friendly):
  • Reddit  — public JSON endpoints (reddit.com/r/<sub>/search.json), 30-day window
  • Hacker News — Algolia search API (hn.algolia.com), 30-day window

Extracts "problem statements" (complaints, wishes, tool requests) using phrase
heuristics, dedupes, and snapshots raw results to data/venture/mined_*.json so
downstream stages (ProblemClusterer) can run offline. X/Instagram are NOT mined:
X read API is paid, Instagram has no practical read API — Reddit+HN are richer
in problem statements anyway.
"""

import sys

__all__ = ["SocialMiner"]

import datetime
import json
import re
import time
from pathlib import Path

from loguru import logger

from core.city.agent_base import AgentBase
from core.config import CONFIG


# Subreddits dense in "somebody should build this" signal. Override via
# CONFIG["venture"]["subreddits"].
_DEFAULT_SUBREDDITS = [
    "SomebodyMakeThis", "AppIdeas", "SaaS", "smallbusiness", "Entrepreneur",
    "productivity", "freelance", "selfhosted", "webdev", "students",
]

# Phrases that mark a post as a PROBLEM statement rather than news/show-off.
_PROBLEM_PATTERNS = [
    r"\bi wish (there was|someone|i could)\b",
    r"\bis there (an app|a tool|a site|software|any way)\b",
    r"\bwhy (is there no|isn't there|cant i|can't i)\b",
    r"\b(so|really|extremely) (annoying|frustrating|tedious)\b",
    r"\bi hate (that|when|how)\b",
    r"\bstruggl(e|ing) (with|to)\b",
    r"\bwaste[sd]? (so much |too much )?time\b",
    r"\bhow do (i|you) (automate|manage|track|organize)\b",
    r"\bthere has to be a better way\b",
    r"\blooking for (a|an) (app|tool|alternative|solution)\b",
    r"\bpay (for|good money for)\b.*\b(tool|app|service)\b",
    r"\bdoes anyone (know|have) (a|an|any) (tool|app|workflow)\b",
]
_PROBLEM_RE = re.compile("|".join(_PROBLEM_PATTERNS), re.IGNORECASE)

_SUBREDDIT_RE = re.compile(r"^[A-Za-z0-9_]{2,21}$")

_UA = {"User-Agent": "VECTOR-personal-research/1.0 (single-user local agent)"}


def looks_like_problem(text: str) -> bool:
    """Heuristic: does this post describe a pain point / tool request?"""
    return bool(_PROBLEM_RE.search(text or ""))


def _out_dir() -> Path:
    d = Path(CONFIG.get("venture", {}).get("data_dir", "data/venture"))
    d.mkdir(parents=True, exist_ok=True)
    return d


class SocialMiner(AgentBase):
    """Mines Reddit + Hacker News for user problem statements (30-day window)."""

    def __init__(self):
        super().__init__(
            agent_id="social_miner",
            name="SocialMiner",
            district="news_trends",
        )
        self.capabilities = ["mine_social", "news_trends", "social", "venture_pipeline"]
        vcfg = CONFIG.get("venture", {})
        self.subreddits: list[str] = list(vcfg.get("subreddits", _DEFAULT_SUBREDDITS))
        self.days: int = int(vcfg.get("window_days", 30))
        self.per_source_limit: int = int(vcfg.get("per_source_limit", 100))
        self._fetch_ok = 0
        self._fetch_failed = 0

    # ── Reddit (public JSON, no auth) ────────────────────────────────────────

    def mine_reddit(self, subreddit: str) -> list[dict]:
        """Newest posts from one subreddit within the window, problem-filtered."""
        import httpx
        posts: list[dict] = []
        cutoff = time.time() - self.days * 86400
        if not _SUBREDDIT_RE.match(str(subreddit)):
            # subreddit names can arrive via task params; never splice them into the URL path
            logger.warning("[VECTOR][social_miner] invalid subreddit name {!r} — skipping", subreddit)
            self._fetch_failed += 1
            return posts
        url = f"https://www.reddit.com/r/{subreddit}/new.json"
        try:
            r = httpx.get(url, params={"limit": self.per_source_limit},
                          headers=_UA, timeout=20.0, follow_redirects=True)
            if r.status_code == 429:
                logger.warning("[VECTOR][social_miner] reddit rate-limited on r/{} — skipping", subreddit)
                self._fetch_failed += 1
                return posts
            r.raise_for_status()
            for child in r.json().get("data", {}).get("children", []):
                d = child.get("data", {})
                if d.get("created_utc", 0) < cutoff:
                    continue
                text = f"{d.get('title', '')} {d.get('selftext', '')}".strip()
                if not looks_like_problem(text):
                    continue
                posts.append({
                    "source": "reddit",
                    "community": subreddit,
                    "title": d.get("title", ""),
                    "text": (d.get("selftext", "") or "")[:1500],
                    "score": int(d.get("score", 0)),
                    "comments": int(d.get("num_comments", 0)),
                    "url": f"https://reddit.com{d.get('permalink', '')}",
                    "created_utc": d.get("created_utc", 0),
                })
            self._fetch_ok += 1
        except Exception as e:
            self._fetch_failed += 1
            logger.warning("[VECTOR][social_miner] reddit r/{} failed: {}", subreddit, e)
        return posts

    # ── Hacker News (Algolia, no auth) ───────────────────────────────────────

    def mine_hackernews(self) -> list[dict]:
        """Ask-HN style problem posts within the window."""
        import httpx
        posts: list[dict] = []
        cutoff = int(time.time() - self.days * 86400)
        queries = ["is there a tool", "i wish there was", "how do you manage",
                   "looking for an alternative", "Ask HN"]
        for q in queries:
            try:
                r = httpx.get(
                    "https://hn.algolia.com/api/v1/search_by_date",
                    params={"query": q, "tags": "story",
                            "numericFilters": f"created_at_i>{cutoff}",
                            "hitsPerPage": min(self.per_source_limit, 50)},
                    headers=_UA, timeout=20.0,
                )
                r.raise_for_status()
                for hit in r.json().get("hits", []):
                    text = f"{hit.get('title', '')} {hit.get('story_text', '') or ''}".strip()
                    if not looks_like_problem(text):
                        continue
                    posts.append({
                        "source": "hackernews",
                        "community": "hn",
                        "title": hit.get("title", ""),
                        "text": (hit.get("story_text", "") or "")[:1500],
                        "score": int(hit.get("points") or 0),
                        "comments": int(hit.get("num_comments") or 0),
                        "url": f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
                        "created_utc": hit.get("created_at_i", 0),
                    })
                self._fetch_ok += 1
            except Exception as e:
                self._fetch_failed += 1
                logger.warning("[VECTOR][social_miner] hn query '{}' failed: {}", q, e)
        return posts

    # ── orchestration ─────────────────────────────────────────────────────────

    def mine_all(self) -> dict:
        """Mine every source, dedupe by URL, snapshot to data/venture/."""
        all_posts: list[dict] = []
        self._fetch_ok = self._fetch_failed = 0
        for sub in self.subreddits:
            all_posts.extend(self.mine_reddit(sub))
            time.sleep(1.0)  # polite pacing — avoids reddit 429s
        all_posts.extend(self.mine_hackernews())

        if self._fetch_ok == 0 and self._fetch_failed > 0:
            # every fetch failed: not "no problems found", and must not become the
            # "latest snapshot" that downstream stages cluster
            logger.error("[VECTOR][social_miner] all {} source fetches failed — no snapshot written",
                         self._fetch_failed)
            return {"status": "error", "error": f"all {self._fetch_failed} source fetches failed",
                    "count": 0, "snapshot": "", "posts": [], "failed_sources": self._fetch_failed}

        seen: set[str] = set()
        unique = []
        for p in all_posts:
            key = p.get("url") or p.get("title")
            if key and key not in seen:
                seen.add(key)
                unique.append(p)
        # engagement-weighted ordering: upvotes + 2x comments (comments = pain intensity)
        unique.sort(key=lambda p: p["score"] + 2 * p["comments"], reverse=True)

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        out = _out_dir() / f"mined_{stamp}.json"
        out.write_text(json.dumps({"mined_at": stamp, "days": self.days,
                                   "posts": unique}, indent=2), encoding="utf-8")
        logger.info("[VECTOR][social_miner] {} problem posts ({} raw) -> {}",
                    len(unique), len(all_posts), out)
        self.award_points(10, "social_mining_complete")
        res = {"count": len(unique), "snapshot": str(out), "posts": unique,
               "failed_sources": self._fetch_failed}
        if self._fetch_failed:
            res["status"] = "partial"
        return res

    @staticmethod
    def latest_snapshot() -> dict | None:
        """Most recent mined_*.json, used by downstream stages."""
        files = sorted(_out_dir().glob("mined_*.json"))
        if not files:
            return None
        try:
            return json.loads(files[-1].read_text(encoding="utf-8"))
        except Exception:
            return None

    async def run(self, task: dict) -> dict:
        p = task.get("params") or {}
        if p.get("subreddits"):
            self.subreddits = list(p["subreddits"])
        if p.get("days"):
            self.days = int(p["days"])
        result = self.mine_all()
        return {"status": "ok", **{k: v for k, v in result.items() if k != "posts"},
                "top_titles": [x["title"] for x in result["posts"][:10]]}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    assert looks_like_problem("I wish there was an app that tracked my attendance")
    assert looks_like_problem("Is there a tool to automate invoice reminders?")
    assert looks_like_problem("Why is there no simple way to merge PDFs offline")
    assert not looks_like_problem("Show HN: my new game engine")
    assert not looks_like_problem("Just hit 10k MRR, AMA")
    miner = SocialMiner()
    assert miner.district == "news_trends"
    print("OK social_miner.py (heuristics + agent init)")
