"""
遗器套装提取器。

数据来源:
  ExcelOutput/RelicSetConfig.json    — SetID → 套装名称
  ExcelOutput/ItemConfigRelic.json   — 各件遗器 → 名称、背景描述
  ExcelOutput/RelicConfig.json       — 遗器 ID → SetID 映射

每个遗器套装输出一个 Document，body 由各件遗器的描述组合而成。
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict

from starrail_rag.core.models import DocType, Document
from starrail_rag.core.textmap import TextMapResolver
from starrail_rag.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

# 遗器部位英文 → 中文
_RELIC_TYPE_ZH: dict[str, str] = {
    "HEAD": "头部",
    "HAND": "手部",
    "BODY": "躯干",
    "FOOT": "脚部",
    "NECK": "位面球",
    "OBJECT": "连结绳",
}


class RelicSetExtractor(BaseExtractor):
    """
    提取所有遗器套装的世界观描述。

    输出每个套装一个 Document：
    - title: 套装名称
    - body: 各件遗器描述的拼接（去重）
    - metadata: set_id, piece_count, rarity
    """

    @property
    def name(self) -> str:
        return "RelicSetExtractor"

    def extract(self) -> list[Document]:
        # 套装名称
        with open(
            self.data_root / "ExcelOutput" / "RelicSetConfig.json", encoding="utf-8"
        ) as f:
            set_configs = json.load(f)
        set_name_map: dict[int, str] = {
            r["SetID"]: self.resolver.resolve_field(r.get("SetName", {}))
            for r in set_configs
        }

        # 各遗器件的 SetID 映射
        with open(
            self.data_root / "ExcelOutput" / "RelicConfig.json", encoding="utf-8"
        ) as f:
            relic_configs = json.load(f)
        relic_set_map: dict[int, int] = {r["ID"]: r["SetID"] for r in relic_configs}

        # 遗器件背景描述
        with open(
            self.data_root / "ExcelOutput" / "ItemConfigRelic.json", encoding="utf-8"
        ) as f:
            relic_items = json.load(f)

        # 按 SetID 聚合（同一件遗器有多个稀有度版本，描述相同，去重）
        set_pieces: dict[int, list[tuple[str, str, str]]] = defaultdict(list)
        seen_desc_per_set: dict[int, set[str]] = defaultdict(set)

        for item in relic_items:
            rid = item["ID"]
            set_id = relic_set_map.get(rid)
            if not set_id:
                continue

            name = self.resolver.resolve_field(item.get("ItemName", {}))
            body = self.resolver.resolve_field(item.get("ItemBGDesc", {}))
            rarity = item.get("Rarity", "")

            if not body:
                continue

            # 同一描述只保留一份（不同稀有度同描述）
            if body in seen_desc_per_set[set_id]:
                continue
            seen_desc_per_set[set_id].add(body)
            set_pieces[set_id].append((name, body, rarity))

        documents: list[Document] = []

        for set_id, pieces in set_pieces.items():
            set_name = set_name_map.get(set_id, f"遗器套装_{set_id}")
            # 拼接各件描述
            body_parts = []
            for piece_name, piece_desc, _ in pieces:
                body_parts.append(f"【{piece_name}】\n{piece_desc}")
            body = "\n\n".join(body_parts)

            # 取最高稀有度
            rarities = [p[2] for p in pieces]
            max_rarity = max(rarities) if rarities else ""

            documents.append(Document(
                doc_id=f"relic_set_{set_id}",
                doc_type=DocType.RELIC_SET,
                title=set_name,
                body=body,
                metadata={
                    "set_id": set_id,
                    "piece_count": len(pieces),
                    "rarity": max_rarity,
                },
            ))

        logger.info(
            "RelicSetExtractor: %d relic sets extracted",
            len(documents),
        )
        return documents
