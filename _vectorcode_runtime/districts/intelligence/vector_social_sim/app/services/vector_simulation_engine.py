"""
VECTOR Social Simulation Engine
Custom multi-agent social simulation — no camel-oasis dependency.

Architecture mirrors what OASIS provides:
- VectorSocialSimDB    — SQLite social media state (posts, likes, follows, trace)
- VectorSocialAgent    — LLM-driven agent with persona + feed context
- VectorSocialSimEngine — orchestrates rounds, active-agent selection, logging

The trace table schema is compatible with what report_agent.py reads via
zep_tools, so reports work unchanged.

Supported action spaces:
  Twitter (6): CREATE_POST, LIKE_POST, REPOST, FOLLOW, QUOTE_POST, DO_NOTHING
  Reddit  (10): CREATE_POST, LIKE_POST, DISLIKE_POST, CREATE_COMMENT,
                LIKE_COMMENT, DISLIKE_COMMENT, SEARCH, FOLLOW, MUTE, DO_NOTHING
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import random
import sqlite3
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..utils.logger import get_logger

logger = get_logger("vector_social_sim.engine")


# ── Action types ──────────────────────────────────────────────────────────────

class ActionType(str, Enum):
    CREATE_POST     = "CREATE_POST"
    LIKE_POST       = "LIKE_POST"
    DISLIKE_POST    = "DISLIKE_POST"
    REPOST          = "REPOST"
    QUOTE_POST      = "QUOTE_POST"
    FOLLOW          = "FOLLOW"
    MUTE            = "MUTE"
    CREATE_COMMENT  = "CREATE_COMMENT"
    LIKE_COMMENT    = "LIKE_COMMENT"
    DISLIKE_COMMENT = "DISLIKE_COMMENT"
    SEARCH          = "SEARCH"
    DO_NOTHING      = "DO_NOTHING"
    INTERVIEW       = "INTERVIEW"


TWITTER_ACTIONS = [
    ActionType.CREATE_POST, ActionType.LIKE_POST, ActionType.REPOST,
    ActionType.QUOTE_POST, ActionType.FOLLOW, ActionType.DO_NOTHING,
]

REDDIT_ACTIONS = [
    ActionType.CREATE_POST, ActionType.LIKE_POST, ActionType.DISLIKE_POST,
    ActionType.CREATE_COMMENT, ActionType.LIKE_COMMENT, ActionType.DISLIKE_COMMENT,
    ActionType.SEARCH, ActionType.FOLLOW, ActionType.MUTE, ActionType.DO_NOTHING,
]


# ── Database ──────────────────────────────────────────────────────────────────

class VectorSocialSimDB:
    """
    SQLite social media state store.
    Schema is compatible with OASIS output so zep_tools / report_agent work as-is.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS posts (
                    post_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    username   TEXT    NOT NULL,
                    content    TEXT    NOT NULL,
                    platform   TEXT    DEFAULT 'twitter',
                    created_at TEXT    NOT NULL
                );
                CREATE TABLE IF NOT EXISTS comments (
                    comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id    INTEGER NOT NULL,
                    user_id    INTEGER NOT NULL,
                    username   TEXT    NOT NULL,
                    content    TEXT    NOT NULL,
                    created_at TEXT    NOT NULL
                );
                CREATE TABLE IF NOT EXISTS likes (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    target_id   INTEGER NOT NULL,
                    target_type TEXT    NOT NULL,
                    sentiment   INTEGER DEFAULT 1,
                    created_at  TEXT    NOT NULL
                );
                CREATE TABLE IF NOT EXISTS follows (
                    follower_id INTEGER NOT NULL,
                    followee_id INTEGER NOT NULL,
                    created_at  TEXT    NOT NULL,
                    PRIMARY KEY (follower_id, followee_id)
                );
                CREATE TABLE IF NOT EXISTS trace (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    action     TEXT    NOT NULL,
                    info       TEXT,
                    created_at TEXT    NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_trace_user   ON trace(user_id);
                CREATE INDEX IF NOT EXISTS idx_trace_action ON trace(action);
                CREATE INDEX IF NOT EXISTS idx_posts_user   ON posts(user_id);
            """)

    def add_post(self, user_id: int, username: str, content: str,
                 platform: str = "twitter") -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO posts (user_id, username, content, platform, created_at)"
                " VALUES (?,?,?,?,?)",
                (user_id, username, content, platform, _now()),
            )
            return cur.lastrowid

    def add_comment(self, post_id: int, user_id: int, username: str,
                    content: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO comments (post_id, user_id, username, content, created_at)"
                " VALUES (?,?,?,?,?)",
                (post_id, user_id, username, content, _now()),
            )
            return cur.lastrowid

    def add_like(self, user_id: int, target_id: int, target_type: str,
                 sentiment: int = 1) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO likes"
                " (user_id, target_id, target_type, sentiment, created_at)"
                " VALUES (?,?,?,?,?)",
                (user_id, target_id, target_type, sentiment, _now()),
            )

    def add_follow(self, follower_id: int, followee_id: int) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO follows (follower_id, followee_id, created_at)"
                " VALUES (?,?,?)",
                (follower_id, followee_id, _now()),
            )

    def log_trace(self, user_id: int, action: str, info: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO trace (user_id, action, info, created_at) VALUES (?,?,?,?)",
                (user_id, action, json.dumps(info, ensure_ascii=False), _now()),
            )

    def get_recent_posts(self, limit: int = 20,
                         platform: Optional[str] = None) -> List[dict]:
        with self._conn() as conn:
            if platform:
                rows = conn.execute(
                    "SELECT * FROM posts WHERE platform=?"
                    " ORDER BY created_at DESC LIMIT ?",
                    (platform, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM posts ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

    def get_followed_posts(self, user_id: int, limit: int = 10) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT p.* FROM posts p"
                " JOIN follows f ON p.user_id = f.followee_id"
                " WHERE f.follower_id = ?"
                " ORDER BY p.created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_interview_result(self, user_id: int) -> dict:
        """Compatible with the trace-query in simulation scripts."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT user_id, info, created_at FROM trace"
                " WHERE action=? AND user_id=?"
                " ORDER BY created_at DESC LIMIT 1",
                (ActionType.INTERVIEW.value, user_id),
            ).fetchone()
        if not row:
            return {"agent_id": user_id, "response": None, "timestamp": None}
        try:
            info = json.loads(row["info"]) if row["info"] else {}
            return {
                "agent_id": user_id,
                "response": info.get("response", info),
                "timestamp": row["created_at"],
            }
        except Exception:
            return {"agent_id": user_id, "response": row["info"], "timestamp": row["created_at"]}

    def stats(self) -> dict:
        with self._conn() as conn:
            posts   = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            comments= conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
            actions = conn.execute("SELECT action, COUNT(*) FROM trace GROUP BY action").fetchall()
        return {
            "posts": posts,
            "comments": comments,
            "action_counts": {r[0]: r[1] for r in actions},
        }


# ── Agent ─────────────────────────────────────────────────────────────────────

class VectorSocialAgent:
    """
    LLM-driven social simulation agent.
    Given their persona + current platform feed, decides what action to take.
    """

    def __init__(self, profile: dict, llm_client, platform: str) -> None:
        self.user_id  = int(profile.get("user_id", 0))
        self.username = profile.get("username", f"user_{self.user_id}")
        self.name     = profile.get("name", self.username)
        self.bio      = profile.get("bio", "")
        self.persona  = profile.get("persona", "")
        self.platform = platform
        self.llm      = llm_client
        self.profile  = profile
        self.available_actions = TWITTER_ACTIONS if platform == "twitter" else REDDIT_ACTIONS

    # ── Internals ──

    def _feed_context(self, db: VectorSocialSimDB) -> str:
        """Build a readable feed for prompt context."""
        followed = db.get_followed_posts(self.user_id, limit=5)
        trending = db.get_recent_posts(limit=10, platform=self.platform)

        seen: set = set()
        lines: list[str] = []
        for p in followed + trending:
            pid = p.get("post_id")
            if pid and pid not in seen:
                seen.add(pid)
                lines.append(f'[@{p["username"]}]: {p["content"]}')
            if len(lines) >= 10:
                break

        return "\n".join(lines) if lines else "(feed is currently empty)"

    async def decide_action(self, db: VectorSocialSimDB,
                            simulated_hour: int) -> tuple[ActionType, dict]:
        """Ask the LLM which action to take and return (ActionType, args_dict)."""
        feed         = self._feed_context(db)
        action_names = ", ".join(a.value for a in self.available_actions)

        system_msg = (
            f"You are {self.name} (@{self.username}) on {self.platform.capitalize()}.\n"
            f"Persona: {self.persona}\n"
            f"Bio: {self.bio}"
        )
        user_msg = (
            f"Current {self.platform} feed:\n{feed}\n\n"
            f"Current simulated time: {simulated_hour:02d}:00\n\n"
            f"Choose ONE action from: {action_names}\n\n"
            "Reply with a JSON object:\n"
            "- \"action\": one of the action types above (required)\n"
            "- \"content\": your post text for CREATE_POST (1-3 sentences)\n"
            "- \"target_username\": @username for LIKE_POST/REPOST/FOLLOW/QUOTE_POST\n"
            "- \"comment\": comment text for CREATE_COMMENT or QUOTE_POST\n"
            "- \"query\": search term for SEARCH\n"
            "- \"reason\": 1 sentence why you chose this (required)\n"
            "Return valid JSON only."
        )

        try:
            result = self.llm.chat_json([
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": user_msg},
            ], temperature=0.8)

            action_str = result.get("action", "DO_NOTHING")
            try:
                action = ActionType(action_str)
            except ValueError:
                action = ActionType.DO_NOTHING
            return action, result

        except Exception as exc:
            logger.warning("Agent %s LLM error: %s", self.username, exc)
            return ActionType.DO_NOTHING, {"reason": f"llm_error: {str(exc)[:60]}"}

    def execute_action(self, action: ActionType, args: dict,
                       db: VectorSocialSimDB,
                       recent_posts: List[dict]) -> dict:
        """Write the action's effects into the DB and return a result summary."""
        result: dict = {"action": action.value, "agent": self.username}

        def _pick_target_post(target_username: str) -> Optional[dict]:
            """Find a recent post by @username, or fall back to any recent post."""
            for p in recent_posts:
                if p.get("username") == target_username:
                    return p
            return recent_posts[0] if recent_posts else None

        if action == ActionType.CREATE_POST:
            content = args.get("content") or f"{self.name} shares thoughts on the topic."
            pid = db.add_post(self.user_id, self.username, content, self.platform)
            result.update(post_id=pid, content=content)

        elif action in (ActionType.LIKE_POST, ActionType.DISLIKE_POST):
            sentiment = 1 if action == ActionType.LIKE_POST else -1
            target = _pick_target_post(args.get("target_username", ""))
            if target:
                db.add_like(self.user_id, target["post_id"], "post", sentiment)
                result["target_post_id"] = target["post_id"]

        elif action == ActionType.REPOST:
            target = _pick_target_post(args.get("target_username", ""))
            if target:
                content = f"RT @{target['username']}: {target['content']}"
                pid = db.add_post(self.user_id, self.username, content, self.platform)
                result.update(post_id=pid, reposted_from=target["username"])

        elif action == ActionType.QUOTE_POST:
            comment_text = args.get("comment") or args.get("content") or "Interesting!"
            target = _pick_target_post(args.get("target_username", ""))
            if target:
                content = f"QT @{target['username']}: {target['content']}\n\n{comment_text}"
                pid = db.add_post(self.user_id, self.username, content, self.platform)
                result.update(post_id=pid, comment=comment_text)

        elif action == ActionType.FOLLOW:
            result["followed_username"] = args.get("target_username", "")
            # follower→followee by user_id lookup is best-effort
            for p in recent_posts:
                if p.get("username") == args.get("target_username"):
                    db.add_follow(self.user_id, p["user_id"])
                    result["followee_id"] = p["user_id"]
                    break

        elif action == ActionType.MUTE:
            result["muted_username"] = args.get("target_username", "")

        elif action == ActionType.CREATE_COMMENT:
            comment_text = args.get("comment") or args.get("content") or "Interesting point!"
            target = _pick_target_post(args.get("target_username", ""))
            if target:
                cid = db.add_comment(target["post_id"], self.user_id,
                                     self.username, comment_text)
                result.update(comment_id=cid, content=comment_text,
                               target_post_id=target["post_id"])

        elif action in (ActionType.LIKE_COMMENT, ActionType.DISLIKE_COMMENT):
            sentiment = 1 if action == ActionType.LIKE_COMMENT else -1
            if recent_posts:
                db.add_like(self.user_id, recent_posts[0]["post_id"], "comment", sentiment)

        elif action == ActionType.SEARCH:
            result["query"] = args.get("query", "")

        elif action == ActionType.DO_NOTHING:
            pass

        # Always write to trace (compatible with OASIS schema)
        trace_info = {**args, **result, "username": self.username}
        db.log_trace(self.user_id, action.value, trace_info)

        return result

    async def interview(self, prompt: str, db: VectorSocialSimDB) -> str:
        """Answer an interview question in character."""
        feed = self._feed_context(db)
        system_msg = (
            f"You are {self.name} (@{self.username}).\n"
            f"Persona: {self.persona}\n"
            f"Bio: {self.bio}\n\n"
            f"Recent activity on {self.platform}:\n{feed}"
        )
        user_msg = f"Interview question: {prompt}\n\nAnswer in character (1-3 sentences)."
        try:
            return self.llm.chat(
                [{"role": "system", "content": system_msg},
                 {"role": "user",   "content": user_msg}],
                temperature=0.7,
            )
        except Exception as exc:
            return f"[Interview failed: {exc}]"


# ── Engine ────────────────────────────────────────────────────────────────────

class VectorSocialSimEngine:
    """
    Orchestrates the full social simulation loop.
    Drop-in replacement for camel-oasis TwitterSimulationRunner / RedditSimulationRunner.

    Usage:
        engine = VectorSocialSimEngine(config, db_path, llm_client, platform="twitter")
        engine.load_twitter_profiles(csv_path)
        result = await engine.run_simulation(total_rounds=10)
    """

    def __init__(self, config: dict, db_path: str, llm_client,
                 platform: str = "twitter") -> None:
        self.config   = config
        self.db_path  = db_path
        self.platform = platform
        self.llm      = llm_client
        self.db       = VectorSocialSimDB(db_path)
        self.agents:  Dict[int, VectorSocialAgent] = {}
        self._agent_configs: Dict[int, dict] = {
            c.get("agent_id", i): c
            for i, c in enumerate(config.get("agent_configs", []))
        }

    # ── Profile loaders ───────────────────────────────────────────────────────

    def load_twitter_profiles(self, csv_path: str) -> int:
        """Load agents from a Twitter CSV profile file. Returns agent count."""
        with open(csv_path, "r", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    uid = int(row.get("user_id", 0))
                    self.agents[uid] = VectorSocialAgent(dict(row), self.llm, "twitter")
                except Exception as exc:
                    logger.warning("Skipping profile row: %s", exc)
        logger.info("Loaded %d Twitter agents from %s", len(self.agents), csv_path)
        return len(self.agents)

    def load_reddit_profiles(self, json_path: str) -> int:
        """Load agents from a Reddit JSON profile file. Returns agent count."""
        with open(json_path, "r", encoding="utf-8") as fh:
            profiles = json.load(fh)
        for profile in profiles:
            try:
                uid = int(profile.get("user_id", 0))
                self.agents[uid] = VectorSocialAgent(profile, self.llm, "reddit")
            except Exception as exc:
                logger.warning("Skipping profile: %s", exc)
        logger.info("Loaded %d Reddit agents from %s", len(self.agents), json_path)
        return len(self.agents)

    # ── Active-agent selection ────────────────────────────────────────────────

    def _active_agents(self, simulated_hour: int) -> List[VectorSocialAgent]:
        """Select agents that are active this round based on config."""
        tc       = self.config.get("time_config", {})
        base_min = tc.get("agents_per_hour_min", 3)
        base_max = tc.get("agents_per_hour_max", 10)
        peaks    = set(tc.get("peak_hours",     [9, 10, 11, 14, 15, 20, 21, 22]))
        offpeak  = set(tc.get("off_peak_hours", [0, 1, 2, 3, 4, 5]))

        multiplier = (
            tc.get("peak_activity_multiplier", 1.5)    if simulated_hour in peaks else
            tc.get("off_peak_activity_multiplier", 0.3) if simulated_hour in offpeak else
            1.0
        )
        target = int(random.uniform(base_min, base_max) * multiplier)

        candidates: List[VectorSocialAgent] = []
        for uid, agent in self.agents.items():
            cfg = self._agent_configs.get(uid, {})
            active_hours   = cfg.get("active_hours", list(range(8, 23)))
            activity_level = float(cfg.get("activity_level", 0.5))
            if simulated_hour in active_hours and random.random() < activity_level:
                candidates.append(agent)

        random.shuffle(candidates)
        return candidates[:target]

    # ── Main simulation loop ──────────────────────────────────────────────────

    async def run_simulation(
        self,
        total_rounds: int = 10,
        max_concurrent: int = 10,
        progress_callback: Optional[Callable] = None,
    ) -> dict:
        """
        Run the full simulation.

        Args:
            total_rounds:       number of rounds to simulate
            max_concurrent:     max agents running LLM calls simultaneously
            progress_callback:  optional fn(round_num, total, summary_dict)

        Returns:
            dict with status, action_counts, db_path, stats
        """
        if not self.agents:
            return {"status": "error", "error": "No agents loaded"}

        tc              = self.config.get("time_config", {})
        minutes_per_rnd = tc.get("minutes_per_round", 30)
        semaphore       = asyncio.Semaphore(max_concurrent)
        action_counts: Dict[str, int] = {}

        # Publish initial event posts
        for post in self.config.get("event_config", {}).get("initial_posts", []):
            aid     = int(post.get("poster_agent_id", 0))
            content = post.get("content", "")
            if aid in self.agents and content:
                a = self.agents[aid]
                self.db.add_post(a.user_id, a.username, content, self.platform)
                self.db.log_trace(a.user_id, "CREATE_POST",
                                  {"content": content, "initial_event": True})

        logger.info("Starting %s simulation: %d rounds, %d agents",
                    self.platform, total_rounds, len(self.agents))

        for rnd in range(total_rounds):
            sim_min  = rnd * minutes_per_rnd
            sim_hour = (sim_min // 60) % 24
            active   = self._active_agents(sim_hour)
            if not active:
                continue

            recent_posts = self.db.get_recent_posts(limit=25, platform=self.platform)

            async def _run_one(agent: VectorSocialAgent) -> None:
                async with semaphore:
                    action, args = await agent.decide_action(self.db, sim_hour)
                    agent.execute_action(action, args, self.db, recent_posts)
                    action_counts[action.value] = action_counts.get(action.value, 0) + 1

            await asyncio.gather(*[_run_one(a) for a in active],
                                  return_exceptions=True)

            if progress_callback:
                progress_callback(rnd + 1, total_rounds, {
                    "simulated_hour": sim_hour,
                    "active_agents":  len(active),
                    "action_counts":  dict(action_counts),
                })

            if (rnd + 1) % 5 == 0 or rnd == 0:
                logger.info("Round %d/%d [%02d:00] — %d agents active",
                            rnd + 1, total_rounds, sim_hour, len(active))

        final_stats = self.db.stats()
        logger.info("Simulation complete. Posts: %d, Actions: %s",
                    final_stats["posts"], action_counts)

        return {
            "status":        "completed",
            "platform":      self.platform,
            "total_rounds":  total_rounds,
            "total_agents":  len(self.agents),
            "action_counts": {k: v for k, v in action_counts.items() if v > 0},
            "db_path":       self.db_path,
            "stats":         final_stats,
        }

    # ── Interview ─────────────────────────────────────────────────────────────

    async def interview_agent(self, user_id: int, prompt: str) -> dict:
        """Interview a specific agent and log the response to the trace table."""
        if user_id not in self.agents:
            return {"agent_id": user_id, "response": None,
                    "error": f"Agent {user_id} not found"}
        agent    = self.agents[user_id]
        response = await agent.interview(prompt, self.db)
        self.db.log_trace(user_id, ActionType.INTERVIEW.value,
                          {"prompt": prompt, "response": response})
        return {
            "agent_id":  user_id,
            "username":  agent.username,
            "name":      agent.name,
            "response":  response,
        }

    async def batch_interview(self,
                              interviews: List[Dict[str, Any]]) -> dict:
        """Interview multiple agents concurrently."""
        tasks = [
            self.interview_agent(
                int(item.get("agent_id", 0)),
                item.get("prompt", "How are you feeling about recent events?"),
            )
            for item in interviews
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            "interviews_count": len(results),
            "results": {
                str(interviews[i].get("agent_id")): (
                    r if not isinstance(r, Exception) else {"error": str(r)}
                )
                for i, r in enumerate(results)
            },
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().isoformat()


def build_engine_from_config(config_path: str, llm_client,
                              platform: str = "twitter") -> VectorSocialSimEngine:
    """Convenience factory: load config.json and return a ready engine."""
    with open(config_path, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    db_path = os.path.join(os.path.dirname(config_path),
                           f"{platform}_simulation.db")
    return VectorSocialSimEngine(config, db_path, llm_client, platform)
