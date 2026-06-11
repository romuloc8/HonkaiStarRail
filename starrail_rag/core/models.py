"""
Core data models for the Star Rail RAG pipeline.

All extractors produce Documents; all cleaners consume and return Documents.
This module is the shared contract between every layer.

v2 changes:
  - DialogueLine: added is_player_utterance, branch_id
  - DialogueBranch: structured representation of player-choice branches
  - NarrativeLayer: epistemic source classification (L1–L7)
  - ReliabilityLevel: information reliability enum
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DocType(str, Enum):
    """Canonical document types across all extractors."""
    MAIN_MISSION       = "main_mission"
    COMPANION_MISSION  = "companion_mission"
    CHARACTER_STORY    = "character_story"
    LIGHT_CONE         = "light_cone"
    RELIC_SET          = "relic_set"
    RELIC_PIECE        = "relic_piece"
    BOOK               = "book"
    ITEM_LORE          = "item_lore"
    ACHIEVEMENT        = "achievement"


class NarrativeLayer(str, Enum):
    """
    Epistemic source layer — determines base reliability of a scene.

    L1  confirmed          直接在主线/主要叙事中发生的可观察事实
    L2  historical_record  世界内档案/史书（经作者视角过滤）
    L3  character_account  角色第一人称叙述（主观，可能不完整）
    L4  speculation        说话者明确表示不确定
    L5  in_char_fiction    世界观内部的虚构作品（《钟表小子》等）
    L6  reconstructed      穷观阵/忆质/梦境等记忆推演
    L7  simulation         模拟宇宙内部叙事（明确标注为模拟）
    """
    L1_CONFIRMED          = "confirmed"
    L2_HISTORICAL_RECORD  = "historical_record"
    L3_CHARACTER_ACCOUNT  = "character_account"
    L4_SPECULATION        = "speculation"
    L5_IN_CHAR_FICTION    = "in_character_fiction"
    L6_RECONSTRUCTED      = "reconstructed"
    L7_SIMULATION         = "simulation"


class ReliabilityLevel(str, Enum):
    """
    Information reliability — used in entity relations and chunk metadata.
    Maps directly to NarrativeLayer but usable standalone.
    """
    CONFIRMED           = "confirmed"
    HISTORICAL_RECORD   = "historical_record"
    CHARACTER_ACCOUNT   = "character_account"
    LEGEND              = "legend"
    SPECULATION         = "speculation"
    IN_CHARACTER_FICTION = "in_character_fiction"
    RECONSTRUCTED       = "reconstructed"
    RETRACTED           = "retracted"   # manually annotated only


# Source-type to base NarrativeLayer mapping (used by extractors)
DOCTYPE_TO_NARRATIVE_LAYER: dict[str, NarrativeLayer] = {
    "开拓任务":   NarrativeLayer.L1_CONFIRMED,
    "终末任务":   NarrativeLayer.L1_CONFIRMED,
    "同行任务":   NarrativeLayer.L3_CHARACTER_ACCOUNT,
    "开拓续闻":   NarrativeLayer.L2_HISTORICAL_RECORD,
    "冒险任务":   NarrativeLayer.L3_CHARACTER_ACCOUNT,
    "活动任务":   NarrativeLayer.L3_CHARACTER_ACCOUNT,
    "character_story": NarrativeLayer.L3_CHARACTER_ACCOUNT,
    "book":            NarrativeLayer.L2_HISTORICAL_RECORD,
    "relic_set":       NarrativeLayer.L5_IN_CHAR_FICTION,
    "item_lore":       NarrativeLayer.L2_HISTORICAL_RECORD,
    "light_cone":      NarrativeLayer.L2_HISTORICAL_RECORD,
    "achievement":     NarrativeLayer.L1_CONFIRMED,
}


@dataclass
class DialogueLine:
    """A single line of dialogue resolved to plain text."""
    sentence_id: int
    speaker: str          # empty string means narration / system
    text: str
    voice_id: int | None = None
    # v2: branch metadata
    is_player_utterance: bool = False   # True = 开拓者的玩家选项台词
    branch_id: str | None = None        # "A"/"B"/... when inside a player-choice branch


@dataclass
class DialogueBranch:
    """
    A player-choice branch block within a scene.
    Stores all alternatives so downstream can decide how to handle them.
    """
    branch_id: str                  # "A", "B", "C"...
    option_text: str                # player-visible choice label
    dialogues: list[DialogueLine]
    is_canonical: bool = False      # always False (game has no "correct" option)


@dataclass
class Document:
    """
    The universal output unit of every extractor.

    - `doc_id`:          Stable, unique identifier
    - `doc_type`:        DocType enum value
    - `title`:           Human-readable title (resolved Chinese string)
    - `dialogues`:       Ordered dialogue lines (primary / merged-branch content)
    - `body`:            Free-form prose content
    - `metadata`:        Arbitrary structured data for downstream use
    - `branches`:        Player-choice branch alternatives (v2, may be empty)
    - `narrative_layer`: Base reliability of this document's content
    """
    doc_id: str
    doc_type: DocType
    title: str
    dialogues: list[DialogueLine] = field(default_factory=list)
    body: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    # v2: branch support
    branches: list[DialogueBranch] = field(default_factory=list)
    narrative_layer: NarrativeLayer = NarrativeLayer.L1_CONFIRMED

    def is_empty(self) -> bool:
        return not self.dialogues and not self.body.strip()

    def has_player_choices(self) -> bool:
        return bool(self.branches)

    def branches_differ(self) -> bool:
        """True when player choice leads to meaningfully different NPC responses."""
        if len(self.branches) < 2:
            return False
        first = tuple((d.speaker, d.text) for d in self.branches[0].dialogues)
        return any(
            tuple((d.speaker, d.text) for d in b.dialogues) != first
            for b in self.branches[1:]
        )
