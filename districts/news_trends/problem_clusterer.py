"""
Module: agents/news_trends/problem_clusterer.py
District: news_trends | Focus: Cluster mined problem posts, rank by demand, flag software-solvable

Stage 2 of the Venture Pipeline. Consumes SocialMiner snapshots.

Clustering: Ollama embeddings (nomic-embed-text) + greedy cosine grouping.
Falls back to token-Jaccard similarity when no embedding server is running,
so the pipeline always completes. Each cluster gets an LLM label + a
"software_solvable" verdict via the agent's district LLM (vchat), with a
keyword fallback when the LLM is unavailable.

Demand score per cluster = Σ over posts of (upvotes + 2×comments) — comment
count weighs double because arguments in comments = pain intensity.
"""

import sys

__all__ = ["ProblemClusterer"]

import datetime
import json
import re
from pathlib import Path

from loguru import logger

from core.city.agent_base import AgentBase
from core.config import CONFIG


def _cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = sum(x * x for x in a) ** 0.5
    db = sum(y * y for y in b) ** 0.5
    return num / (da * db) if da and db else 0.0


_WORD_RE = re.compile(r"[a-z]{3,}")
_STOP = {"the", "and", "for", "that", "this", "with", "have", "there", "what",
         "how", "why", "any", "anyone", "does", "looking", "wish", "tool",
         "app", "way", "you", "your", "but", "not", "can", "cant", "are",
         "was", "all", "get", "use", "using", "just", "like", "really"}


def _stem(w: str) -> str:
    """Crude suffix-stripping stemmer so 'invoices'/'invoice' and
    'freelancers'/'freelance' land on the same token in the fallback path."""
    for suf in ("ers", "ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            w = w[: -len(suf)]
            break
    if len(w) > 4 and w.endswith("e"):
        w = w[:-1]
    return w


def _tokens(text: str) -> set[str]:
    return {_stem(w) for w in _WORD_RE.findall((text or "").lower())
            if w not in _STOP}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_SOFTWARE_HINTS = re.compile(
    r"\b(track|automat|organiz|manag|schedul|remind|convert|merge|sync|"
    r"dashboard|report|invoice|export|import|search|filter|notif|api|"
    r"spreadsheet|email|backup|monitor|generat|summariz|transcrib)", re.I)


class ProblemClusterer(AgentBase):
    """Groups problem posts into ranked demand clusters."""

    def __init__(self):
        super().__init__(
            agent_id="problem_clusterer",
            name="ProblemClusterer",
            district="news_trends",
        )
        self.capabilities = ["cluster_problems", "ers", "news_trends", "venture_pipeline"]
        vcfg = CONFIG.get("venture", {})
        self.sim_threshold = float(vcfg.get("cluster_similarity", 0.72))
        self.jaccard_threshold = float(vcfg.get("cluster_jaccard", 0.30))
        self.top_n = int(vcfg.get("top_clusters", 8))

    # ── embeddings (optional) ────────────────────────────────────────────────

    def _embed(self, texts: list[str]) -> list[list[float]] | None:
        """Batch-embed via Ollama; None when the server/model is unavailable."""
        import httpx
        host = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
        model = CONFIG.get("venture", {}).get("embed_model", "nomic-embed-text")
        vectors: list[list[float]] = []
        try:
            with httpx.Client(timeout=30.0) as client:
                for t in texts:
                    r = client.post(f"{host}/api/embeddings",
                                    json={"model": model, "prompt": t[:1000]})
                    if r.status_code != 200:
                        return None
                    vec = r.json().get("embedding")
                    if not vec:
                        return None
                    vectors.append(vec)
            return vectors
        except Exception as e:
            logger.info("[VECTOR][clusterer] embeddings unavailable ({}) — token fallback", e)
            return None

    # ── clustering ────────────────────────────────────────────────────────────

    def cluster(self, posts: list[dict]) -> list[dict]:
        """Greedy single-pass clustering. Returns ranked cluster dicts."""
        if not posts:
            return []
        texts = [f"{p.get('title', '')} {p.get('text', '')}"[:1000] for p in posts]
        vectors = self._embed(texts)
        token_sets = [_tokens(t) for t in texts] if vectors is None else []

        clusters: list[dict] = []
        for i, post in enumerate(posts):
            best, best_sim = None, 0.0
            for c in clusters:
                j = c["member_ids"][0]              # compare against cluster seed
                sim = (_cosine(vectors[i], vectors[j]) if vectors is not None
                       else _jaccard(token_sets[i], token_sets[j]))
                if sim > best_sim:
                    best, best_sim = c, sim
            threshold = self.sim_threshold if vectors is not None else self.jaccard_threshold
            if best is not None and best_sim >= threshold:
                best["member_ids"].append(i)
                best["posts"].append(post)
            else:
                clusters.append({"member_ids": [i], "posts": [post]})

        for c in clusters:
            c["size"] = len(c["posts"])
            c["demand_score"] = sum(p.get("score", 0) + 2 * p.get("comments", 0)
                                    for p in c["posts"])
            c["sources"] = sorted({p.get("community", "") for p in c["posts"]})
            del c["member_ids"]
        clusters.sort(key=lambda c: (c["size"], c["demand_score"]), reverse=True)
        return clusters

    # ── labeling ──────────────────────────────────────────────────────────────

    def label_cluster(self, cluster: dict) -> dict:
        """LLM label + software-solvable verdict; keyword fallback never fails."""
        sample = "\n".join(f"- {p.get('title', '')}" for p in cluster["posts"][:6])
        label, solvable, idea = "", None, ""
        try:
            raw = self.vchat(
                "These social media posts describe the same user problem:\n"
                f"{sample}\n\n"
                "Reply with EXACTLY three lines:\n"
                "PROBLEM: <one-sentence problem statement>\n"
                "SOFTWARE_SOLVABLE: <yes|no>\n"
                "IDEA: <one-sentence software product idea, or 'none'>"
            )
            for line in (raw or "").splitlines():
                # vchat() echoes the prompt back when the LLM is unreachable; its
                # "<yes|no>" / "<one-sentence ...>" placeholders must not be parsed
                # as answers (they made every cluster software_solvable=True).
                if line.upper().startswith("PROBLEM:"):
                    val = line.split(":", 1)[1].strip()
                    label = "" if val.startswith("<") else val
                elif line.upper().startswith("SOFTWARE_SOLVABLE:"):
                    val = line.split(":", 1)[1].strip().lower()
                    if val.startswith("yes"):
                        solvable = True
                    elif val.startswith("no"):
                        solvable = False
                elif line.upper().startswith("IDEA:"):
                    val = line.split(":", 1)[1].strip()
                    idea = "" if val.startswith("<") else val
        except Exception as e:
            logger.debug("[VECTOR][clusterer] vchat label failed: {}", e)
        if not label:
            label = cluster["posts"][0].get("title", "")[:120]
        if solvable is None:
            solvable = bool(_SOFTWARE_HINTS.search(
                " ".join(p.get("title", "") for p in cluster["posts"])))
        cluster["problem"] = label
        cluster["software_solvable"] = solvable
        cluster["product_idea"] = idea if idea.lower() != "none" else ""
        return cluster

    # ── orchestration ─────────────────────────────────────────────────────────

    def analyze(self, posts: list[dict] | None = None) -> dict:
        """Full stage-2 pass: cluster -> label top N -> snapshot ranked report."""
        if posts is None:
            from districts.news_trends.social_miner import SocialMiner
            snap = SocialMiner.latest_snapshot()
            if not snap:
                # no mined data is not "zero clusters / no trends"
                logger.warning("[VECTOR][clusterer] no mined snapshot available")
                return {"status": "error", "error": "no mined snapshot available (run SocialMiner first)",
                        "total_posts": 0, "cluster_count": 0, "software_solvable": 0,
                        "snapshot": "", "top_clusters": []}
            posts = snap.get("posts", [])
        clusters = self.cluster(posts)
        top = [self.label_cluster(c) for c in clusters[:self.top_n]]
        solvable = [c for c in top if c.get("software_solvable")]

        out_dir = Path(CONFIG.get("venture", {}).get("data_dir", "data/venture"))
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        out = out_dir / f"clusters_{stamp}.json"
        slim = [{k: v for k, v in c.items() if k != "posts"} | {
            "examples": [{"title": p.get("title", ""), "url": p.get("url", ""),
                          "score": p.get("score", 0), "comments": p.get("comments", 0)}
                         for p in c["posts"][:5]],
        } for c in top]
        out.write_text(json.dumps({"analyzed_at": stamp, "total_posts": len(posts),
                                   "clusters": slim}, indent=2), encoding="utf-8")
        logger.info("[VECTOR][clusterer] {} clusters ({} software-solvable) -> {}",
                    len(clusters), len(solvable), out)
        self.award_points(10, "problem_clustering_complete")
        return {"total_posts": len(posts), "cluster_count": len(clusters),
                "software_solvable": len(solvable), "snapshot": str(out),
                "top_clusters": slim}

    async def run(self, task: dict) -> dict:
        p = task.get("params") or {}
        result = self.analyze(p.get("posts"))
        return {"status": "ok", **result}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    fake = [
        {"title": "I wish there was a tool to track freelance invoices", "text": "",
         "score": 50, "comments": 20, "community": "freelance", "url": "u1"},
        {"title": "Is there an app to manage invoice reminders for freelancers", "text": "",
         "score": 30, "comments": 10, "community": "smallbusiness", "url": "u2"},
        {"title": "Why is there no simple offline PDF merger", "text": "",
         "score": 80, "comments": 5, "community": "selfhosted", "url": "u3"},
    ]
    pc = ProblemClusterer()
    clusters = pc.cluster(fake)
    assert len(clusters) == 2, f"expected 2 clusters, got {len(clusters)}"
    assert clusters[0]["size"] == 2  # the two invoice posts merge
    labeled = pc.label_cluster(clusters[0])
    assert labeled["software_solvable"] is True
    print(f"OK problem_clusterer.py ({len(clusters)} clusters, fallback path)")
