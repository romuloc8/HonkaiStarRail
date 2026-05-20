"""
角色故事提取器。

数据来源:
  ExcelOutput/StoryAtlas.json    — AvatarID → 多段故事文本 (Hash)
  ExcelOutput/AvatarConfig.json  — AvatarID → 角色名、命途、属性等

每个角色输出一个 Document，body 为所有故事段落的拼接。
metadata 包含 avatar_id、命途（AvatarBaseType）、属性（DamageType）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from starrail_rag.core.models import DocType, Document
from starrail_rag.core.textmap import TextMapResolver
from starrail_rag.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

# 命途英文代号 → 中文
_BASE_TYPE_ZH: dict[str, str] = {
    "Knight": "存护",
    "Rogue": "巡猎",
    "Mage": "智识",
    "Shaman": "同谐",
    "Warlock": "虚无",
    "Warrior": "毁灭",
    "Priest": "丰饶",
    "Memory": "记忆",
}

# 属性英文代号 → 中文
_DAMAGE_TYPE_ZH: dict[str, str] = {
    "Fire": "火", "Ice": "冰", "Thunder": "雷",
    "Wind": "风", "Quantum": "量子", "Imaginary": "虚数",
    "Physical": "物理",
}

# 稀有度英文 → 星级
_RARITY_ZH: dict[str, str] = {
    "CombatPowerAvatarRarityType4": "4星",
    "CombatPowerAvatarRarityType5": "5星",
}


class CharacterStoryExtractor(BaseExtractor):
    """
    提取所有可玩角色的故事文本。

    输出每个角色一个 Document：
    - title: 角色名
    - body: 全部故事段落（\n\n 分隔）
    - metadata: avatar_id, path（命途）, element（属性）, rarity
    """

    @property
    def name(self) -> str:
        return "CharacterStoryExtractor"

    def extract(self) -> list[Document]:
        # 读取角色基础信息
        with open(self.data_root / "ExcelOutput" / "AvatarConfig.json", encoding="utf-8") as f:
            avatar_list = json.load(f)

        avatar_map: dict[int, dict] = {r["AvatarID"]: r for r in avatar_list}

        # 读取故事文本
        with open(self.data_root / "ExcelOutput" / "StoryAtlas.json", encoding="utf-8") as f:
            story_rows = json.load(f)

        # 按 AvatarID 聚合故事段落（保持 StoryID 顺序）
        stories_by_avatar: dict[int, list[tuple[int, str]]] = {}
        for row in story_rows:
            aid = row["AvatarID"]
            sid = row["StoryID"]
            text = self.resolver.resolve_field(row.get("Story", {}))
            if text:
                stories_by_avatar.setdefault(aid, []).append((sid, text))

        # 对每个 AvatarID 排序故事
        for aid in stories_by_avatar:
            stories_by_avatar[aid].sort(key=lambda x: x[0])

        documents: list[Document] = []

        for aid, story_chunks in stories_by_avatar.items():
            avatar = avatar_map.get(aid, {})
            char_name = self.resolver.resolve_field(avatar.get("AvatarName", {}))
            if not char_name:
                char_name = f"角色_{aid}"

            base_type_en = avatar.get("AvatarBaseType", "")
            damage_type_en = avatar.get("DamageType", "")
            rarity_en = avatar.get("Rarity", "")

            body = "\n\n".join(text for _, text in story_chunks)

            doc = Document(
                doc_id=f"character_story_{aid}",
                doc_type=DocType.CHARACTER_STORY,
                title=char_name,
                body=body,
                metadata={
                    "avatar_id": aid,
                    "path": _BASE_TYPE_ZH.get(base_type_en, base_type_en),
                    "element": _DAMAGE_TYPE_ZH.get(damage_type_en, damage_type_en),
                    "rarity": _RARITY_ZH.get(rarity_en, rarity_en),
                    "story_count": len(story_chunks),
                },
            )
            documents.append(doc)

        logger.info(
            "CharacterStoryExtractor: %d characters, %d with stories",
            len(avatar_map), len(documents),
        )
        return documents
