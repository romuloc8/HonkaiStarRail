"""
Extractor registry.

Import all extractors here so callers can do:
    from starrail_rag.extractors import MainMissionExtractor
"""

from starrail_rag.extractors.base import BaseExtractor
from starrail_rag.extractors.main_mission import MainMissionExtractor
from starrail_rag.extractors.wiki_mission import WikiMissionExtractor, CHAPTER_NAMES
from starrail_rag.extractors.character_story import CharacterStoryExtractor
from starrail_rag.extractors.light_cone import LightConeExtractor
from starrail_rag.extractors.relic_set import RelicSetExtractor
from starrail_rag.extractors.book import BookExtractor
from starrail_rag.extractors.item_lore import ItemLoreExtractor

__all__ = [
    "BaseExtractor",
    "MainMissionExtractor",
    "WikiMissionExtractor",
    "CHAPTER_NAMES",
    "CharacterStoryExtractor",
    "LightConeExtractor",
    "RelicSetExtractor",
    "BookExtractor",
    "ItemLoreExtractor",
]
