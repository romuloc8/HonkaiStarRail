"""
Extractor registry.

Import all extractors here so callers can do:
    from starrail_rag.extractors import MainMissionExtractor
"""

from starrail_rag.extractors.base import BaseExtractor
from starrail_rag.extractors.main_mission import MainMissionExtractor
from starrail_rag.extractors.wiki_mission import WikiMissionExtractor, CHAPTER_NAMES

__all__ = [
    "BaseExtractor",
    "MainMissionExtractor",
    "WikiMissionExtractor",
    "CHAPTER_NAMES",
]
