"""
Module: agents/languages/__init__.py
District: languages | Focus: Multi-language coaching platform
"""

from .hindi_coach import HindiCoach
from .english_coach import EnglishCoach
from .bengali_coach import BengaliCoach
from .assamese_coach import AssameseCoach
from .japanese_coach import JapaneseCoach

__all__ = [
    "HindiCoach",
    "EnglishCoach",
    "BengaliCoach",
    "AssameseCoach",
    "JapaneseCoach",
]