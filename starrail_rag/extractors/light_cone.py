"""
光锥描述提取器。

数据来源:
  ExcelOutput/ItemConfigEquipment.json  — EquipmentID → 名称、背景故事描述
  ExcelOutput/EquipmentConfig.json      — EquipmentID → 命途、稀有度

每个光锥输出一个 Document，body 为光锥背景故事。
"""

from __future__ import annotations

import json
import logging

from starrail_rag.core.models import DocType, Document
from starrail_rag.core.textmap import TextMapResolver
from starrail_rag.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

_BASE_TYPE_ZH: dict[str, str] = {
    "Knight": "存护", "Rogue": "巡猎", "Mage": "智识",
    "Shaman": "同谐", "Warlock": "虚无", "Warrior": "毁灭",
    "Priest": "丰饶", "Memory": "记忆",
}

_RARITY_ZH: dict[str, str] = {
    "CombatPowerLightconeRarity3": "3星",
    "CombatPowerLightconeRarity4": "4星",
    "CombatPowerLightconeRarity5": "5星",
}


class LightConeExtractor(BaseExtractor):
    """
    提取所有光锥的故事描述文本。

    输出每个光锥一个 Document：
    - title: 光锥名称
    - body: 背景故事描述
    - metadata: equipment_id, path（命途）, rarity
    """

    @property
    def name(self) -> str:
        return "LightConeExtractor"

    def extract(self) -> list[Document]:
        # 基础信息：命途 & 稀有度
        with open(
            self.data_root / "ExcelOutput" / "EquipmentConfig.json", encoding="utf-8"
        ) as f:
            eq_list = json.load(f)
        eq_map: dict[int, dict] = {r["EquipmentID"]: r for r in eq_list}

        # 故事文本
        with open(
            self.data_root / "ExcelOutput" / "ItemConfigEquipment.json", encoding="utf-8"
        ) as f:
            items = json.load(f)

        documents: list[Document] = []
        skipped = 0

        for item in items:
            eid = item["ID"]
            name = self.resolver.resolve_field(item.get("ItemName", {}))
            body = self.resolver.resolve_field(item.get("ItemBGDesc", {}))

            if not body:
                skipped += 1
                continue

            eq_info = eq_map.get(eid, {})
            base_type_en = eq_info.get("AvatarBaseType", "")
            rarity_en = eq_info.get("Rarity", "")

            documents.append(Document(
                doc_id=f"light_cone_{eid}",
                doc_type=DocType.LIGHT_CONE,
                title=name or f"光锥_{eid}",
                body=body,
                metadata={
                    "equipment_id": eid,
                    "path": _BASE_TYPE_ZH.get(base_type_en, base_type_en),
                    "rarity": _RARITY_ZH.get(rarity_en, rarity_en),
                },
            ))

        logger.info(
            "LightConeExtractor: %d light cones (%d skipped, no description)",
            len(documents), skipped,
        )
        return documents
