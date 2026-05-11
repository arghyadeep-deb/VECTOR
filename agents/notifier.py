"""
V.E.C.T.O.R. notifier.
Sends notifications to the user via all available channels.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from loguru import logger
from core.config import CONFIG


class Notifier:
    """Send notifications to the user via Hermes, phone, browser, etc."""

    def __init__(self):
        self._channels = CONFIG.get("notifier", {}).get("channels", ["hermes"])
        logger.info("[VECTOR][notifier] Notifier initialized")

    def notify(self, message: str, priority: str = "normal", channel: str | None = None) -> dict:
        """Send a notification. priority: low, normal, high, urgent."""
        channels = [channel] if channel else self._channels
        results = {}
        for ch in channels:
            try:
                if ch == "hermes":
                    from agents.districts.communications.hermes_adapter import HermesAdapter
                    import asyncio
                    adapter = HermesAdapter()
                    results[ch] = asyncio.get_event_loop().run_until_complete(
                        adapter.send_message("internal", "user", message)
                    )
                elif ch == "phone":
                    logger.info(f"[VECTOR][notifier] Phone notification: {message}")
                    results[ch] = {"status": "ok"}
            except Exception as e:
                logger.error(f"[VECTOR][notifier] Failed to notify via {ch}: {e}")
                results[ch] = {"status": "error", "detail": str(e)}
        return {"notification": message, "priority": priority, "results": results}

    def alert(self, message: str) -> dict:
        """Send an urgent alert."""
        return self.notify(message, priority="high")


if __name__ == "__main__":
    n = Notifier()
    print(n.notify("V.E.C.T.O.R. is running", priority="low"))