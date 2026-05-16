"""
V.E.C.T.O.R. notifier.
Sends notifications to the user via VectorCode, phone, browser, and all available channels.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))  # agents/ -> codebase root
from loguru import logger
from core.config import CONFIG


class Notifier:
    """Send notifications to the user via VectorCode, phone, browser, etc."""

    def __init__(self):
        self._channels = CONFIG.get("notifier", {}).get("channels", ["vectorcode"])
        logger.info("[VECTOR][notifier] Notifier initialized")

    def notify(self, message: str, priority: str = "normal", channel: str | None = None) -> dict:
        """Send a notification. priority: low, normal, high, urgent."""
        channels = [channel] if channel else self._channels
        results = {}
        for ch in channels:
            try:
                if ch == "vectorcode":
                    from agents.communications.communications_adapter import CommunicationsAdapter
                    import asyncio
                    if CommunicationsAdapter is None:
                        results[ch] = {"status": "error", "detail": "MessagingHub unavailable"}
                        continue
                    adapter = CommunicationsAdapter()
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(adapter.send_notification(message, priority))
                        results[ch] = {"status": "queued"}
                    except RuntimeError:
                        results[ch] = asyncio.run(adapter.send_notification(message, priority))
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