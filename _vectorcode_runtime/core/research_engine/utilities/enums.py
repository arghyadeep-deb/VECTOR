# utilities/enums.py
from enum import Enum

__all__ = [
    "KnowledgeAccumulationApproach",
    "SearchMode",
]



class KnowledgeAccumulationApproach(Enum):
    QUESTION = "QUESTION"
    ITERATION = "ITERATION"
    NO_KNOWLEDGE = "NO_KNOWLEDGE"
    MAX_NR_OF_CHARACTERS = "MAX_NR_OF_CHARACTERS"


class SearchMode(Enum):
    """Search mode for filtering search engines."""

    ALL = "all"  # Include all available search engines
    SCIENTIFIC = (
        "scientific"  # Include only scientific and generic search engines
    )
