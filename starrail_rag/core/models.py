"""
Core data models for the Star Rail RAG pipeline.

All extractors produce Documents; all cleaners consume and return Documents.
This module is the shared contract between every layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DocType(str, Enum):
    """Canonical document types across all extractors."""
    MAIN_MISSION = "main_mission"
    COMPANION_MISSION = "companion_mission"
    CHARACTER_STORY = "character_story"
    LIGHT_CONE = "light_cone"
    RELIC_SET = "relic_set"
    RELIC_PIECE = "relic_piece"
    BOOK = "book"
    ITEM_LORE = "item_lore"


@dataclass
class DialogueLine:
    """A single line of dialogue resolved to plain text."""
    sentence_id: int
    speaker: str          # empty string means narration / system
    text: str
    voice_id: int | None = None


@dataclass
class Document:
    """
    The universal output unit of every extractor.

    - `doc_id`:     Stable, unique identifier (e.g. "main_mission_1000101")
    - `doc_type`:   DocType enum value
    - `title`:      Human-readable title (resolved Chinese string)
    - `dialogues`:  Ordered dialogue lines (empty for non-dialogue sources)
    - `body`:       Free-form prose content (e.g. item lore description)
    - `metadata`:   Arbitrary structured data for downstream use
                    (chapter_id, mission_type, char_id, etc.)
    """
    doc_id: str
    doc_type: DocType
    title: str
    dialogues: list[DialogueLine] = field(default_factory=list)
    body: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.dialogues and not self.body.strip()
