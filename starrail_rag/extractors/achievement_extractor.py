"""
成就文本提取器。

提取 AchievementData.json 中包含 lore 信息的成就（过滤纯机制性成就），
生成可用于实体提取的文档列表。

用法：
    from starrail_rag.extractors.achievement_extractor import AchievementExtractor
    extractor = AchievementExtractor(data_root, resolver)
    docs = extractor.extract()

输出文件：output/lore/achievements.jsonl
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from starrail_rag.core.models import DocType, Document, NarrativeLayer
from starrail_rag.core.textmap import TextMapResolver
from starrail_rag.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("/workspace/output")

# 纯机制性成就的描述特征（排除，不含 lore）
_MECHANICAL_RE = re.compile(
    r'#\d+\[i\]|'           # 参数化数字
    r'击碎\d|'
    r'施放\d+|'
    r'收集\d+|'
    r'攻击\d+次|'
    r'完成\d+次|'
    r'强化\d+|'
    r'挑战\d+|'
    r'积累\d+|'
    r'达到\d+级|'
    r'消耗\d+'
)

# 含隐性 lore 的成就系列名（这些系列通常含世界观描述）
_LORE_SERIES_KEYWORDS = [
    "通往群星的轨道", "众秘探奇", "与你同行的回忆", "历程记录", "流光遗痕",
    "我，开拓者",
]


class AchievementExtractor(BaseExtractor):
    """
    从游戏成就数据提取 lore 文本。

    筛选标准：
    1. 排除纯机制性成就（含 #N[i] 参数占位符或重复动词"击碎N次"等）
    2. 保留 Rarity=Mid 或 High 的成就（这些更可能含世界观信息）
    3. 描述长度 > 15 字
    """

    def __init__(
        self,
        data_root: str | Path,
        resolver: TextMapResolver,
        output_root: str | Path = OUTPUT_ROOT,
        include_all_rarities: bool = False,
    ) -> None:
        super().__init__(data_root, resolver)
        self.output_root = Path(output_root)
        self._include_all = include_all_rarities

    @property
    def name(self) -> str:
        return "AchievementExtractor"

    def _load_series(self) -> dict[int, str]:
        path = self.data_root / "ExcelOutput" / "AchievementSeries.json"
        data = json.load(open(path))
        items = data if isinstance(data, list) else list(data.values())
        return {
            s.get("SeriesID"): self.resolver.resolve_field(s.get("SeriesTitle", ""))
            for s in items
        }

    def extract(self) -> list[Document]:
        path = self.data_root / "ExcelOutput" / "AchievementData.json"
        data = json.load(open(path))
        items = data if isinstance(data, list) else list(data.values())
        series_map = self._load_series()

        docs = []
        total_skipped = 0

        for a in items:
            title = self.resolver.resolve_field(a.get("AchievementTitle", {}))
            desc = self.resolver.resolve_field(a.get("AchievementDesc", {}))
            rarity = a.get("Rarity", "Low")
            aid = a.get("AchievementID", 0)
            series_id = a.get("SeriesID", 0)
            series_name = series_map.get(series_id, "")

            if not title or not desc:
                total_skipped += 1
                continue

            # 清理 wiki 样式标签和颜色代码
            desc_clean = re.sub(r'<[^>]+>', '', desc)
            desc_clean = re.sub(r'\{[^}]+\}', '', desc_clean).strip()

            # 过滤纯机制性描述
            if _MECHANICAL_RE.search(desc_clean):
                total_skipped += 1
                continue

            # 过滤太短的描述
            if len(desc_clean) < 15:
                total_skipped += 1
                continue

            # Rarity 过滤
            if not self._include_all and rarity not in ("Mid", "High"):
                total_skipped += 1
                continue

            body = f"【成就：{title}】\n{desc_clean}"
            if series_name:
                body = f"【成就系列：{series_name}】\n" + body

            doc = Document(
                doc_id=f"achievement_{aid}",
                doc_type=DocType.ACHIEVEMENT,
                title=title,
                body=body,
                narrative_layer=NarrativeLayer.L1_CONFIRMED,
                metadata={
                    "source_type": "achievement",
                    "achievement_id": aid,
                    "series_id": series_id,
                    "series_name": series_name,
                    "rarity": rarity,
                    "chapter_anchor": "unknown",
                    "narrative_layer": NarrativeLayer.L1_CONFIRMED.value,
                    "reliability": "confirmed",
                },
            )
            docs.append(doc)

        logger.info(
            "AchievementExtractor: %d lore achievements extracted, %d skipped",
            len(docs), total_skipped,
        )
        return docs

    def extract_and_save(self, output_path: Path | None = None) -> list[Document]:
        docs = self.extract()
        if not docs:
            return docs

        out = output_path or (self.output_root / "lore" / "achievements.jsonl")
        out.parent.mkdir(parents=True, exist_ok=True)

        with open(out, "w", encoding="utf-8") as f:
            for doc in docs:
                record = {
                    "doc_id": doc.doc_id,
                    "doc_type": doc.doc_type.value,
                    "title": doc.title,
                    "body": doc.body,
                    "dialogues": [],
                    "metadata": doc.metadata,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info("Saved %d achievements to %s", len(docs), out)
        return docs
