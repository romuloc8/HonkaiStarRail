"""
通用 Wiki 分类爬取器。

通过 MediaWiki Category API 枚举某个分类下的所有页面，
逐一获取 wikitext 并解析对话文本。

适用于:
  同行任务   → wiki 分类 "同行任务"
  开拓续闻   → wiki 分类 "开拓续闻"
  冒险任务   → wiki 分类 "冒险任务"
  活动任务   → wiki 分类 "活动任务"

与 WikiMissionExtractor 的区别:
  WikiMissionExtractor 从游戏数据（MainMission.json）获取任务名单，
  本类直接从 wiki 分类系统枚举，更适合游戏数据中没有对应条目的任务类型。

用法 (pipeline config):
  cfg.wiki_categories = [("同行任务", "companion_mission"), ...]
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from urllib.parse import quote

import requests

from starrail_rag.core.models import DocType, Document
from starrail_rag.core.textmap import TextMapResolver
from starrail_rag.extractors.base import BaseExtractor
from starrail_rag.extractors.wiki_mission import (
    _fetch_wikitext,
    _parse_wikitext_dialogues,
    _WIKI_BASE,
)

logger = logging.getLogger(__name__)

_API_BASE = "https://wiki.biligame.com/sr/api.php"

# 分类名 → DocType 映射
_CATEGORY_DOCTYPE: dict[str, DocType] = {
    "同行任务": DocType.COMPANION_MISSION,
    "开拓续闻": DocType.MAIN_MISSION,      # 开拓续闻属于大主线范畴
    "冒险任务": DocType.MAIN_MISSION,
    "活动任务": DocType.MAIN_MISSION,
}


def _get_category_members(
    category: str, session: requests.Session, max_retries: int = 4
) -> list[str]:
    """
    返回 wiki 分类下所有页面标题（自动处理分页 + 限流重试）。
    """
    members: list[str] = []
    params: dict = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmlimit": 500,
        "cmprop": "title",
        "cmtype": "page",
        "format": "json",
    }
    while True:
        for attempt in range(max_retries):
            try:
                r = session.get(_API_BASE, params=params, timeout=15)
                if r.status_code == 200 and r.text:
                    break
                wait = 2 ** (attempt + 1)
                logger.debug(
                    "API %d for Category:%s, retry in %ds",
                    r.status_code, category, wait,
                )
                time.sleep(wait)
            except Exception as exc:  # noqa: BLE001
                wait = 2 ** (attempt + 1)
                logger.debug("API error: %s, retry in %ds", exc, wait)
                time.sleep(wait)
        else:
            logger.warning("Failed to fetch Category:%s after %d attempts", category, max_retries)
            break

        try:
            data = r.json()
        except Exception:
            logger.warning("Failed to parse API response for Category:%s", category)
            break

        batch = data.get("query", {}).get("categorymembers", [])
        members.extend(m["title"] for m in batch)
        cont = data.get("continue", {}).get("cmcontinue")
        if not cont:
            break
        params["cmcontinue"] = cont
        time.sleep(0.5)

    return members


class WikiCategoryExtractor(BaseExtractor):
    """
    从 BiliWiki 分类页枚举并抓取任务对话。

    Parameters
    ----------
    data_root, resolver : 继承自 BaseExtractor（wiki 模式不使用 resolver）。
    categories : 要爬取的 wiki 分类名称列表，默认为 ["同行任务"]。
    request_delay : 每次 HTTP 请求间隔（秒），建议 >= 1.5。
    """

    def __init__(
        self,
        data_root: str | Path,
        resolver: TextMapResolver,
        categories: list[str] | None = None,
        request_delay: float = 1.5,
    ) -> None:
        super().__init__(data_root, resolver)
        self._categories = categories or ["同行任务"]
        self._delay = request_delay
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "StarRailRAG/1.0 (research project)"
        })

    @property
    def name(self) -> str:
        return "WikiCategoryExtractor"

    def _extract_category(self, category: str) -> list[Document]:
        logger.info("Fetching page list for Category:%s …", category)
        titles = _get_category_members(category, self._session)
        logger.info("Category:%s → %d pages", category, len(titles))

        doc_type = _CATEGORY_DOCTYPE.get(category, DocType.MAIN_MISSION)
        documents: list[Document] = []
        not_found = 0
        wikitext_cache: dict[str, list] = {}

        for title in titles:
            if title in wikitext_cache:
                dialogues = wikitext_cache[title]
            else:
                wikitext = _fetch_wikitext(title, self._session)
                time.sleep(self._delay)
                if wikitext is None:
                    not_found += 1
                    wikitext_cache[title] = []
                    continue
                dialogues = _parse_wikitext_dialogues(wikitext)
                wikitext_cache[title] = dialogues

            if not dialogues:
                logger.debug("No dialogue found in '%s'", title)
                continue

            documents.append(Document(
                doc_id=f"wiki_{category}_{quote(title, safe='')}",
                doc_type=doc_type,
                title=title,
                dialogues=dialogues,
                metadata={
                    "source": "wiki",
                    "category": category,
                    "wiki_url": _WIKI_BASE + quote(title, safe=""),
                    "sentence_count": len(dialogues),
                },
            ))
            logger.debug("  '%s': %d lines", title, len(dialogues))

        logger.info(
            "Category:%s done — %d docs with dialogue, %d not found",
            category, len(documents), not_found,
        )
        return documents

    def extract(self) -> list[Document]:
        all_docs: list[Document] = []
        for category in self._categories:
            docs = self._extract_category(category)
            all_docs.extend(docs)

        total_lines = sum(d.metadata["sentence_count"] for d in all_docs)
        logger.info(
            "WikiCategoryExtractor done: %d total docs, %d dialogue lines",
            len(all_docs), total_lines,
        )
        return all_docs
