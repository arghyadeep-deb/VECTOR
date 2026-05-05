import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger


class LanguageDetector:
    VOICE_MAP = {
        "en": "bf_emma",
        "hi": "hf_alpha",
        "bn": "bn",
        "as": "as",
        "ja": "jf_alpha",
    }
    SUPPORTED = set(VOICE_MAP.keys())

    def detect(self, text: str) -> str:
        try:
            from langdetect import detect
            lang = detect(text)
            if lang in self.SUPPORTED:
                return lang
            return "en"
        except Exception as e:
            logger.warning(f"[VECTOR][lang] Detection failed: {e}")
            return "en"

    def get_voice(self, lang: str) -> str:
        return self.VOICE_MAP.get(lang, self.VOICE_MAP["en"])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    detector = LanguageDetector()
    tests = [
        ("Hello VECTOR, what is my schedule today?", "en"),
        ("नमस्ते वेक्टर, आज क्या काम है?", "hi"),
        ("こんにちは、今日の予定は？", "ja"),
    ]
    passed = 0
    for text, expected in tests:
        detected = detector.detect(text)
        voice = detector.get_voice(detected)
        ok = detected == expected
        if ok:
            passed += 1
        logger.info(f"[VECTOR][lang] '{text[:30]}...' → {detected} (voice={voice}) {'✅' if ok else '⚠️ expected ' + expected}")
    print(f"✅ language_detector OK ({passed}/{len(tests)} correct)" if passed >= 2 else f"❌ FAILED ({passed}/{len(tests)})")
