"""
Abstract base class for all extractors.

To add a new extractor (e.g. CharacterStoryExtractor):
    1. Create starrail_rag/extractors/character_story.py
    2. Subclass BaseExtractor
    3. Implement extract() -> list[Document]
    4. Register in starrail_rag/extractors/__init__.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starrail_rag.core.models import Document
    from starrail_rag.core.textmap import TextMapResolver


class BaseExtractor(ABC):
    """
    Contract for all data source extractors.

    Subclasses receive:
        data_root  – Path to the root of the StarRailData repository
        resolver   – Shared TextMapResolver (locale already configured)

    They produce:
        list[Document] – Ready to pass to CleaningPipeline then to indexing
    """

    def __init__(self, data_root: str | Path, resolver: TextMapResolver) -> None:
        self.data_root = Path(data_root)
        self.resolver = resolver

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name used in logging and CLI output."""

    @abstractmethod
    def extract(self) -> list[Document]:
        """
        Run the full extraction for this source.
        Must be idempotent and side-effect-free.
        """
