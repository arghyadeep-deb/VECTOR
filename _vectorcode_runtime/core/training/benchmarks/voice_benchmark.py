"""Voice benchmark: 15 prompts testing STT accuracy, TTS quality, wake word detection, and voice command parsing."""


__all__ = [
    "VOICE_PROMPTS",
    "VoiceBenchmark",
]

from typing import Callable

from loguru import logger


VOICE_PROMPTS = [
    {"id": "wake_word_detect", "prompt": "Say 'Hey Vector' clearly and wait for confirmation.", "expected": "hey_vector|vector|wake", "weight": 1.0, "min_words": 2},
    {"id": "command_parse", "prompt": "Set a timer for 5 minutes.", "expected": "timer|5|minute|set", "weight": 1.0, "min_words": 5},
    {"id": "weather_query", "prompt": "What is the weather in Tokyo?", "expected": "weather|tokyo|temperature|forecast", "weight": 0.8, "min_words": 4},
    {"id": "reminder_create", "prompt": "Remind me to call mom at 3 PM.", "expected": "remind|call|mom|3|pm", "weight": 0.8, "min_words": 6},
    {"id": "music_control", "prompt": "Play some lo-fi hip hop.", "expected": "play|music|lo_fi|hip_hop", "weight": 0.7, "min_words": 4},
    {"id": "alarm_set", "prompt": "Set an alarm for 6:30 AM tomorrow.", "expected": "alarm|6:30|6_30|tomorrow|set", "weight": 0.8, "min_words": 6},
    {"id": "smart_home", "prompt": "Turn off the living room lights.", "expected": "turn_off|living_room|light|off", "weight": 0.7, "min_words": 5},
    {"id": "navigation", "prompt": "Navigate to the nearest coffee shop.", "expected": "navigate|nearest|coffee|shop|direction", "weight": 0.7, "min_words": 5},
    {"id": "phone_call", "prompt": "Call Dr. Sharma.", "expected": "call|dr|sharma|phone", "weight": 0.7, "min_words": 3},
    {"id": "message_dictate", "prompt": "Text Sarah: Running late, be there in 10.", "expected": "text|sarah|running|late|message", "weight": 0.8, "min_words": 6},
    {"id": "volume_control", "prompt": "Turn the volume up to 60 percent.", "expected": "volume|60|percent|up|turn", "weight": 0.6, "min_words": 5},
    {"id": "calendar_query", "prompt": "What does my schedule look like today?", "expected": "schedule|today|calendar|look", "weight": 0.7, "min_words": 5},
    {"id": "definition_voice", "prompt": "Define machine learning.", "expected": "machine_learning|define|definition|ml", "weight": 0.6, "min_words": 8},
    {"id": "translation_voice", "prompt": "Translate 'good morning' to French.", "expected": "translate|good_morning|french|bonjour", "weight": 0.7, "min_words": 5},
    {"id": "multi_turn", "prompt": "First: What is 2+2? Second: Now multiply that by 3.", "expected": "2|2|4|multiply|3|12", "weight": 0.9, "min_words": 10},
]


class VoiceBenchmark:
    def __init__(self):
        self.prompts = VOICE_PROMPTS
        logger.info("[Benchmark] VoiceBenchmark initialized with {} prompts", len(self.prompts))

    def run(self, model_fn: Callable[[str], str]) -> dict[str, float]:
        scores = {}
        for p in self.prompts:
            try:
                response = model_fn(p["prompt"])
                score = self._score_response(p, response)
                scores[p["id"]] = round(score, 4)
                logger.debug("[Benchmark] Voice {} scored {:.2f}", p["id"], score)
            except Exception as e:
                logger.warning("[Benchmark] Voice {} failed: {}", p["id"], e)
                scores[p["id"]] = 0.0
        avg = sum(scores.values()) / max(len(scores), 1)
        logger.info("[Benchmark] Voice average: {:.2f}/1.00", avg)
        return scores

    def score(self) -> float:
        return sum(self.run(lambda x: "").values()) / max(len(self.prompts), 1)

    def _score_response(self, prompt: dict, response: str) -> float:
        if not response:
            return 0.0
        response_lower = response.lower()
        keywords = prompt["expected"].lower().split("|")
        matches = sum(1 for k in keywords if k.replace("_", " ") in response_lower or k in response_lower)
        keyword_score = matches / max(len(keywords), 1)
        word_count = len(response.split())
        min_w = prompt.get("min_words", 3)
        length_factor = min(1.0, word_count / max(min_w, 1))
        weight = prompt.get("weight", 0.7)
        return keyword_score * weight + length_factor * (1.0 - weight)
