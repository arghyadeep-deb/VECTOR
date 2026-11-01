import sys
import re

from loguru import logger

_FILLERS = re.compile(r"\b(?:um|uh|like|you know|sort of|kind of|actually|basically|literally|honestly)\b", re.IGNORECASE)
_MULTI_SPACE = re.compile(r"\s{2,}")

_SENTIMENT_RATES = {
    "neutral": 160,
    "positive": 175,
    "negative": 150,
    "urgent": 190,
    "calm": 140,
    "excited": 185,
}


class VoicePersonality:
    def modulate(self, text: str, sentiment: str = "neutral", tone_config: dict | None = None) -> str:
        cleaned = self.remove_fillers(text)
        result = self.add_pauses(cleaned, tone_config)
        return result

    def remove_fillers(self, text: str) -> str:
        result = _FILLERS.sub("", text)
        result = _MULTI_SPACE.sub(" ", result)
        return result.strip()

    def add_pauses(self, text: str, tone_config: dict | None = None) -> str:
        if tone_config is None:
            tone_config = {}
        pause_style = tone_config.get("pause_style", "none")
        if pause_style == "dramatic":
            text = text.replace(". ", ". ... ")
            text = text.replace("! ", "! ... ")
            text = text.replace("? ", "? ... ")
        elif pause_style == "conversational":
            text = text.replace(". ", ". .. ")
            text = text.replace(", ", ", .. ")
        return text

    def get_speech_rate(self, sentiment: str = "neutral", tone_config: dict | None = None) -> int:
        if tone_config and "speed" in tone_config:
            return int(tone_config["speed"])
        return _SENTIMENT_RATES.get(sentiment, 160)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    vp = VoicePersonality()
    test = "So um, like, you know we need to basically check the logs"
    cleaned = vp.remove_fillers(test)
    modulated = vp.modulate("Hello, how are you? I am fine!", "positive")
    rate = vp.get_speech_rate("urgent")
    logger.info(f"[VECTOR][vp] fillers: '{test}' -> '{cleaned}'")
    print(f"\u2705 voice_personality OK (rate={rate}wpm, modulated_len={len(modulated)})")
