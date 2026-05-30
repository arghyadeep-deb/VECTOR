"""NudgeEngine — monitors activity patterns and generates proactive nudges."""

import asyncio

__all__ = [
    "nudge_engine",
    "NudgeEngine",
]

import datetime
import subprocess
import sys
import time
from pathlib import Path

from loguru import logger
from core.config import CONFIG


class NudgeEngine:
    def __init__(self):
        self._latest: dict | None = None
        self._session_start = time.time()
        self._last_idle_time = 0.0
        self._check_interval = 30

    @property
    def latest(self) -> dict | None:
        return self._latest

    def dismiss(self):
        self._latest = None

    def push(self, text: str, source: str = "proactive", need: str = "") -> dict:
        """Surface a proactive nudge directly (e.g. from the anticipation engine).

        The frontend polls /nudge/latest, so setting _latest here makes the
        prediction visible to the owner without an LLM round-trip.
        """
        self._latest = {
            "text": text,
            "rule": source,
            "need": need,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "signals": {},
        }
        logger.info(f"[VECTOR][nudge] (proactive) {source}: {text}")
        return self._latest

    async def tick(self):
        signals = self._collect_signals()
        rule = self._match_rule(signals)
        if rule:
            text = await self._generate_nudge(rule, signals)
            self._latest = {
                "text": text,
                "rule": rule["name"],
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "signals": signals,
            }
            logger.info(f"[VECTOR][nudge] {rule['name']}: {text}")

    def _collect_signals(self) -> dict:
        signals = {
            "uptime_minutes": (time.time() - self._session_start) / 60,
            "git_commits_1h": self._count_git_commits(60),
            "git_commits_5m": self._count_git_commits(5),
            "idle_seconds": 0,
            "errors_5m": 0,
        }
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            if cpu < 5:
                signals["idle_seconds"] = self._last_idle_time + self._check_interval
            else:
                signals["idle_seconds"] = 0
                self._last_idle_time = 0
        except Exception:
            signals["idle_seconds"] = 0
        return signals

    def _count_git_commits(self, minutes: int) -> int:
        try:
            since = f"{minutes} minutes ago"
            r = subprocess.run(
                ["git", "log", f"--since={since}", "--oneline"],
                capture_output=True, text=True, timeout=5,
                cwd=Path(__file__).parent.parent.parent,
            )
            return len(r.stdout.strip().split("\n")) if r.stdout.strip() else 0
        except Exception:
            return 0

    def _match_rule(self, signals: dict) -> dict | None:
        rules = [
            {
                "name": "deep_work",
                "condition": (
                    signals["uptime_minutes"] >= 45
                    and signals["idle_seconds"] < 30
                    and signals["git_commits_5m"] >= 1
                ),
                "template": "deep_work",
            },
            {
                "name": "long_session",
                "condition": signals["uptime_minutes"] >= 120 and signals["idle_seconds"] < 30,
                "template": "long_session",
            },
            {
                "name": "idle",
                "condition": signals["idle_seconds"] >= 600,
                "template": "idle",
            },
        ]
        for rule in rules:
            if rule["condition"]:
                return rule
        return None

    async def _generate_nudge(self, rule: dict, signals: dict) -> str:
        import httpx
        prompts = {
            "deep_work": (
                "Generate a one-sentence encouraging nudge for a developer "
                "who has been coding for 45+ minutes with recent git commits. "
                "Acknowledge their focus briefly. No emoji."
            ),
            "long_session": (
                "Generate a one-sentence gentle nudge suggesting a short break "
                "for a developer who has been working for 2+ hours. No emoji."
            ),
            "idle": (
                "Generate a one-sentence helpful nudge for a developer who has "
                "been idle for 10+ minutes. Ask if they need help researching "
                "something. No emoji."
            ),
        }
        prompt = prompts.get(rule["template"], "")
        if not prompt:
            return "You seem to be in a good rhythm. Keep going."

        try:
            ollama_host = CONFIG.get("ollama_host", "http://127.0.0.1:11434")
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{ollama_host}/api/generate",
                    json={"model": "llama3.2:latest", "prompt": prompt, "stream": False},
                )
                if r.status_code == 200:
                    return r.json().get("response", "").strip()
        except Exception as e:
            logger.warning(f"[VECTOR][nudge] LLM failed: {e}")

        return self._fallback_nudge(rule["template"])

    def _fallback_nudge(self, template: str) -> str:
        fallbacks = {
            "deep_work": "You've been in deep focus for 45 minutes. The work is solid.",
            "long_session": "You've been at this for 2 hours. A quick break will help.",
            "idle": "You seem idle. Want me to run some diagnostics?",
        }
        return fallbacks.get(template, "Stay sharp, sir.")


nudge_engine = NudgeEngine()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("OK")
