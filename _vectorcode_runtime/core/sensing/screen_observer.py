"""
Module: core/sensing/screen_observer.py
ScreenObserver: captures the primary monitor, OCRs visible text,
and classifies the owner's current activity.
RULE 5 — screenshot data stays local, never transmitted externally.
"""

import sys

import numpy as np
from datetime import datetime, timezone
from loguru import logger

from core.config import CONFIG


class ScreenObserver:
    """Captures screen, OCRs text, classifies current activity.

    Activity categories and their trigger keywords:
        coding        — source code / terminal / IDE signals
        browsing      — browser URLs / browser process names
        studying      — educational content, notes, PDFs
        communication — messaging / email apps
        distraction   — social / entertainment platforms
        idle          — default when nothing matches
    """

    ACTIVITY_KEYWORDS: dict[str, list[str]] = {
        "coding": [
            "def ", "import ", "class ", "function", "git", "terminal",
            "vscode", "nvim", "vim", "pylance", "traceback", "error:",
            "warning:", "pytest", "cargo", "npm run", "docker", "kubectl",
            "bash", "powershell", "cmd.exe",
        ],
        "browsing": [
            "http://", "https://", "www.", "chrome", "firefox", "edge",
            "safari", "brave", "opera", "browser",
        ],
        "studying": [
            "lecture", "course", "notes", "pdf", "obsidian", "notion",
            "anki", "flashcard", "textbook", "chapter", "exercise",
            "coursera", "udemy", "khan", "mit ocw",
        ],
        "communication": [
            "whatsapp", "telegram", "discord", "gmail", "mail",
            "outlook", "slack", "teams", "zoom", "meet", "signal",
            "inbox", "compose", "reply",
        ],
        "distraction": [
            "youtube", "instagram", "facebook", "netflix", "twitter",
            "x.com", "tiktok", "reddit", "twitch", "prime video",
            "hotstar", "spotify", "reels", "shorts",
        ],
        "idle": [],
    }

    def __init__(self) -> None:
        self._sct = None          # mss ScreenCapture instance, lazy
        self._tess_ok: bool | None = None   # None = not yet checked

    # ── private ───────────────────────────────────────────────────────────────

    def _ensure_mss(self) -> bool:
        """Returns True if mss is importable (instance created per-capture to avoid resource leak)."""
        try:
            import mss  # noqa: F401
            return True
        except ImportError as exc:
            logger.warning(f"[VECTOR][screen] mss unavailable: {exc}")
            return False
        except Exception as exc:
            logger.warning(f"[VECTOR][screen] mss check failed: {exc}")
            return False

    def _ensure_tesseract(self) -> bool:
        """Check pytesseract availability once and cache result."""
        if self._tess_ok is not None:
            return self._tess_ok
        try:
            import pytesseract
            # Quick functional check — will raise if Tesseract binary absent
            pytesseract.get_tesseract_version()
            self._tess_ok = True
        except Exception as exc:
            logger.warning(
                f"[VECTOR][screen] pytesseract/Tesseract not available: {exc}. "
                f"OCR disabled — activity classification will use keyword matching on empty text."
            )
            self._tess_ok = False
        return self._tess_ok

    # ── public API ─────────────────────────────────────────────────────────────

    def capture(self) -> np.ndarray:
        """Capture monitor[1] (primary display) and return a BGR numpy array.

        Falls back to a 100×100 black frame on any error.
        """
        try:
            if not self._ensure_mss():
                return np.zeros((100, 100, 3), dtype=np.uint8)

            import mss
            with mss.mss() as sct:
                monitor = sct.monitors[1]   # monitors[0] = all combined, [1] = primary
                sct_img = sct.grab(monitor)
                # mss returns BGRA; drop alpha channel to get BGR
                bgr = np.array(sct_img, dtype=np.uint8)[:, :, :3]
            logger.debug(
                f"[VECTOR][screen] Captured frame {bgr.shape[1]}x{bgr.shape[0]}"
            )
            return bgr

        except Exception as exc:
            logger.error(f"[VECTOR][screen] capture error: {exc}")
            return np.zeros((100, 100, 3), dtype=np.uint8)

    def ocr_text(self, frame: np.ndarray) -> str:
        """Run Tesseract OCR on a BGR frame and return stripped text.

        Returns empty string if Tesseract is unavailable or OCR fails.
        """
        try:
            if not self._ensure_tesseract():
                return ""

            import pytesseract
            from PIL import Image

            # Convert BGR → RGB for PIL
            rgb = frame[:, :, ::-1]
            pil_img = Image.fromarray(rgb)

            text: str = pytesseract.image_to_string(pil_img, timeout=10)
            return text.strip()

        except Exception as exc:
            logger.error(f"[VECTOR][screen] ocr_text error: {exc}")
            return ""

    def classify_activity(self, text: str) -> str:
        """Keyword-match *text* against ACTIVITY_KEYWORDS.

        The category with the highest keyword hit count wins.
        Ties are broken by the order defined in ACTIVITY_KEYWORDS.
        Returns "idle" when nothing matches.
        """
        text_lower = text.lower()
        best_category = "idle"
        best_count = 0

        for category, keywords in self.ACTIVITY_KEYWORDS.items():
            if not keywords:
                continue
            count = sum(1 for kw in keywords if kw.lower() in text_lower)
            if count > best_count:
                best_count = count
                best_category = category

        return best_category

    def active_window_title(self) -> str:
        """Title of the foreground window — 'what the owner is doing RIGHT NOW'.

        This is the cheapest, most reliable screen-context signal: no OCR, no
        install, always available on Windows. When Tesseract isn't installed
        (OCR disabled) this is the ONLY thing that tells VECTOR the owner is in
        'main.py - Visual Studio Code' vs 'YouTube - Google Chrome' vs Spotify
        (2026-07-17 owner: "it should understand my complete screen when I do
        some work" — OCR was dead so screen_summary was just '[idle]')."""
        if sys.platform != "win32":
            return ""
        try:
            import ctypes
            u32 = ctypes.windll.user32
            h = u32.GetForegroundWindow()
            n = u32.GetWindowTextLengthW(h)
            if n <= 0:
                return ""
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(h, buf, n + 1)
            return buf.value.strip()
        except Exception:
            return ""

    def observe(self) -> dict:
        """Full pipeline: capture → active-window → OCR → classify.

        Returns::
            {
                "activity":     str,   # classified category
                "window":       str,   # foreground window title (no OCR needed)
                "text_snippet": str,   # first 200 chars of OCR output
                "timestamp":    str,   # ISO-8601 UTC
            }
        On any unhandled error returns activity="unknown".
        """
        ts = datetime.now(timezone.utc).isoformat()
        window = self.active_window_title()
        try:
            frame    = self.capture()
            raw_text = self.ocr_text(frame)
            # Fold the window title into classification too — even with OCR off,
            # "Visual Studio Code"/"YouTube"/"Spotify" in the title classifies the
            # activity correctly.
            activity = self.classify_activity((raw_text + " " + window).strip())
            snippet  = raw_text[:200]

            logger.info(
                f"[VECTOR][screen] observe → activity={activity!r} "
                f"window={window[:40]!r} text_len={len(raw_text)}"
            )
            return {
                "activity":     activity,
                "window":       window,
                "text_snippet": snippet,
                # Full OCR text (capped) — stuck detection needs whole error
                # blocks, not the 200-char snippet.
                "raw_text":     raw_text[:4000],
                "timestamp":    ts,
            }

        except Exception as exc:
            logger.error(f"[VECTOR][screen] observe error: {exc}")
            return {
                "activity":     "unknown",
                "window":       window,
                "text_snippet": "",
                "raw_text":     "",
                "timestamp":    ts,
            }


# ── smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    ok = True

    try:
        observer = ScreenObserver()
        result = observer.observe()

        assert isinstance(result, dict),           "observe must return dict"
        assert "activity"     in result,           "missing 'activity' key"
        assert "text_snippet" in result,           "missing 'text_snippet' key"
        assert "timestamp"    in result,           "missing 'timestamp' key"
        assert isinstance(result["activity"], str), "activity must be str"

        # classify_activity unit test
        coding_text = "def main():\n    import sys\n    git commit"
        assert observer.classify_activity(coding_text) == "coding", \
            "classify_activity should return 'coding' for code text"

        dist_text = "youtube.com instagram reels netflix"
        assert observer.classify_activity(dist_text) == "distraction", \
            "classify_activity should return 'distraction'"

        logger.info(
            f"[VECTOR][screen] ScreenObserver OK — activity={result['activity']!r}"
        )
    except Exception as exc:
        logger.error(f"[VECTOR][screen] ScreenObserver smoke test FAILED: {exc}")
        ok = False

    print("✅ screen_observer.py OK" if ok else "❌ screen_observer.py FAILED")
