"""
Extractor registry.

Import all extractors here so callers can do:
    from starrail_rag.extractors import MainMissionExtractor
"""

from starrail_rag.extractors.base import BaseExtractor
from starrail_rag.extractors.main_mission import MainMissionExtractor

__all__ = [
    "BaseExtractor",
    "MainMissionExtractor",
]
