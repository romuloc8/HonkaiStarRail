"""
道具背景描述提取器。

数据来源:
  ExcelOutput/ItemConfig.json — ID → 道具名、背景描述（ItemBGDesc）

过滤:
  - 仅提取有非空 ItemBGDesc 的记录
  - 排除已由其他提取器处理的类型（光锥、遗器通过专属提取器处理）

每个道具输出一个 Document，body 为 ItemBGDesc。
"""

from __future__ import annotations

import json
import logging

from starrail_rag.core.models import DocType, Document
from starrail_rag.core.textmap import TextMapResolver
from starrail_rag.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

# 由专属提取器处理的道具类型，此处跳过（避免重复）
_SKIP_SUB_TYPES = frozenset(["LightCone", "Relic"])


class ItemLoreExtractor(BaseExtractor):
    """
    提取道具背景描述（世界观碎片）。

    输出每个有 lore 描述的道具一个 Document：
    - title: 道具名称
    - body: 背景描述（ItemBGDesc）
    - metadata: item_id, main_type, sub_type
    """

    @property
    def name(self) -> str:
        return "ItemLoreExtractor"

    def extract(self) -> list[Document]:
        with open(
            self.data_root / "ExcelOutput" / "ItemConfig.json", encoding="utf-8"
        ) as f:
            items = json.load(f)

        documents: list[Document] = []
        skipped_no_desc = 0
        skipped_type = 0

        for item in items:
            sub_type = item.get("ItemSubType", "")
            if sub_type in _SKIP_SUB_TYPES:
                skipped_type += 1
                continue

            bg_desc = item.get("ItemBGDesc", {})
            body = self.resolver.resolve_field(bg_desc) if isinstance(bg_desc, dict) else ""

            if not body:
                skipped_no_desc += 1
                continue

            item_id = item["ID"]
            name = self.resolver.resolve_field(item.get("ItemName", {}))

            documents.append(Document(
                doc_id=f"item_lore_{item_id}",
                doc_type=DocType.ITEM_LORE,
                title=name or f"道具_{item_id}",
                body=body,
                metadata={
                    "item_id": item_id,
                    "main_type": item.get("ItemMainType", ""),
                    "sub_type": sub_type,
                },
            ))

        logger.info(
            "ItemLoreExtractor: %d items with lore "
            "(%d skipped no-desc, %d skipped handled-type)",
            len(documents), skipped_no_desc, skipped_type,
        )
        return documents
