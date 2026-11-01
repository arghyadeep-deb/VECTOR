"""Training benchmarks: coding, research, voice, and personality evaluation."""

from core.training.benchmarks.coding_benchmark import CodingBenchmark
from core.training.benchmarks.research_benchmark import ResearchBenchmark
from core.training.benchmarks.voice_benchmark import VoiceBenchmark
from core.training.benchmarks.personality_benchmark import PersonalityBenchmark

__all__ = [
    "CodingBenchmark",
    "ResearchBenchmark",
    "VoiceBenchmark",
    "PersonalityBenchmark",
]
