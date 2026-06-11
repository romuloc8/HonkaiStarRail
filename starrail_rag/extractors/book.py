"""
游戏内书籍 / 档案提取器。

数据来源:
  ExcelOutput/LocalbookConfig.json   — BookID → 书名、正文内容
  ExcelOutput/BookSeriesConfig.json  — 系列 ID → 系列标题、简介

每本书输出一个 Document，body 为书籍正文。
metadata 包含系列信息，便于后续按系列聚合。
"""

from __future__ import annotations

import json
import logging

from starrail_rag.core.models import DocType, Document
from starrail_rag.core.textmap import TextMapResolver
from starrail_rag.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


class BookExtractor(BaseExtractor):
    """
    提取游戏内所有书籍的正文内容。

    输出每本书一个 Document：
    - title: 书名
    - body: 书籍正文
    - metadata: book_id, series_id, series_title, series_comment
    """

    @property
    def name(self) -> str:
        return "BookExtractor"

    def extract(self) -> list[Document]:
        # 系列信息
        with open(
            self.data_root / "ExcelOutput" / "BookSeriesConfig.json", encoding="utf-8"
        ) as f:
            series_list = json.load(f)

        series_map: dict[int, dict] = {}
        for r in series_list:
            sid = r["BookSeriesID"]
            series_map[sid] = {
                "title": self.resolver.resolve_field(r.get("BookSeries", {})),
                "comment": self.resolver.resolve_field(r.get("BookSeriesComments", {})),
            }

        # 书籍内容
        with open(
            self.data_root / "ExcelOutput" / "LocalbookConfig.json", encoding="utf-8"
        ) as f:
            book_list = json.load(f)

        documents: list[Document] = []
        skipped = 0

        for book in book_list:
            book_id = book["BookID"]
            series_id = book.get("BookSeriesID", 0)
            title = self.resolver.resolve_field(book.get("BookInsideName", {}))
            body = self.resolver.resolve_field(book.get("BookContent", {}))

            if not body:
                skipped += 1
                continue

            series_info = series_map.get(series_id, {})

            documents.append(Document(
                doc_id=f"book_{book_id}",
                doc_type=DocType.BOOK,
                title=title or f"书籍_{book_id}",
                body=body,
                metadata={
                    "book_id": book_id,
                    "series_id": series_id,
                    "series_title": series_info.get("title", ""),
                    "series_comment": series_info.get("comment", ""),
                    "inside_index": book.get("BookSeriesInsideID", 0),
                },
            ))

        logger.info(
            "BookExtractor: %d books extracted (%d skipped, no content)",
            len(documents), skipped,
        )
        return documents
