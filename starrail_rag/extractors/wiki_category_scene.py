"""
分类 Wiki 场景级爬取器。

爬取同行任务/开拓续闻/冒险任务/活动任务的场景级数据，
输出到各自的子目录。

使用 MediaWiki Category API 枚举页面，
然后用 WikiSceneExtractor 的场景解析逻辑处理每个页面。

输出结构：
  output/companion/missions.jsonl     同行任务
  output/continuance/missions.jsonl   开拓续闻
  output/adventure/missions.jsonl     冒险任务
  output/activity/missions.jsonl      活动任务
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import requests

from starrail_rag.core.models import DialogueLine, DocType, Document
from starrail_rag.core.textmap import TextMapResolver
from starrail_rag.extractors.base import BaseExtractor
from starrail_rag.extractors.wiki_mission import (
    _fetch_wikitext,
    _expand_plot_options,
    _WIKI_BASE,
    _SKIP_SECTIONS,
    _HEADING_RE,
    _SKIP_TEMPLATE_RE,
    _BULLET_DIALOGUE_RE,
    _PLOT_OPTION_RE,
)
from urllib.parse import quote as _url_quote
from starrail_rag.extractors.wiki_scene import _parse_wikitext_scenes

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("/workspace/output")
_API_BASE = "https://wiki.biligame.com/sr/api.php"

CATEGORY_CONFIG = {
    "同行任务":  {"output_dir": "companion",   "filename": "missions.jsonl", "doc_type": "companion_scene"},
    "开拓续闻":  {"output_dir": "continuance",  "filename": "missions.jsonl", "doc_type": "main_mission_scene"},
    "冒险任务":  {"output_dir": "adventure",    "filename": "missions.jsonl", "doc_type": "main_mission_scene"},
    "活动任务":  {"output_dir": "activity",     "filename": "missions.jsonl", "doc_type": "main_mission_scene"},
}


def _get_category_members(category: str, session: requests.Session,
                           max_retries: int = 4) -> list[str]:
    members, params = [], {
        "action": "query", "list": "categorymembers",
        "cmtitle": f"Category:{category}", "cmlimit": 500,
        "cmprop": "title", "cmtype": "page", "format": "json",
    }
    while True:
        for attempt in range(max_retries):
            try:
                r = session.get(_API_BASE, params=params, timeout=15)
                if r.status_code == 200 and r.text:
                    break
                time.sleep(2 ** (attempt + 1))
            except Exception:
                time.sleep(2 ** (attempt + 1))
        else:
            logger.warning("Failed to fetch Category:%s", category)
            break
        try:
            data = r.json()
        except Exception:
            break
        members.extend(m["title"] for m in data.get("query", {}).get("categorymembers", []))
        cont = data.get("continue", {}).get("cmcontinue")
        if not cont:
            break
        params["cmcontinue"] = cont
        time.sleep(0.5)
    return members


class WikiCategorySceneExtractor(BaseExtractor):
    """
    按 wiki 分类爬取场景级数据，写入对应子目录。

    categories: 要爬取的 wiki 分类名称列表（默认全部 4 类）
    request_delay: 每次请求间隔（秒）
    """

    def __init__(
        self,
        data_root,
        resolver: TextMapResolver,
        categories: list[str] | None = None,
        output_root: str | Path = OUTPUT_ROOT,
        request_delay: float = 1.5,
    ) -> None:
        super().__init__(data_root, resolver)
        self._categories = categories or list(CATEGORY_CONFIG.keys())
        self.output_root = Path(output_root)
        self._delay = request_delay
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "StarRailRAG/1.0 (research)"

    @property
    def name(self) -> str:
        return "WikiCategorySceneExtractor"

    def extract(self) -> list[Document]:
        all_docs: list[Document] = []

        for category in self._categories:
            cfg = CATEGORY_CONFIG.get(category, {})
            out_dir = self.output_root / cfg.get("output_dir", category)
            out_dir.mkdir(parents=True, exist_ok=True)
            filename = cfg.get("filename", "missions.jsonl")
            doc_type_str = cfg.get("doc_type", "main_mission_scene")

            logger.info("Fetching category: %s → %s/%s", category, cfg.get("output_dir"), filename)
            titles = _get_category_members(category, self._session)
            logger.info("  %d pages in Category:%s", len(titles), category)

            wikitext_cache: dict[str, list] = {}
            category_docs: list[Document] = []
            not_found = 0

            for title in titles:
                if title in wikitext_cache:
                    scenes = wikitext_cache[title]
                else:
                    wikitext = _fetch_wikitext(title, self._session)
                    time.sleep(self._delay)
                    if wikitext is None:
                        not_found += 1
                        wikitext_cache[title] = []
                        continue
                    scenes = _parse_wikitext_scenes(wikitext)
                    wikitext_cache[title] = scenes

                if not scenes:
                    continue

                wiki_url = _WIKI_BASE + _url_quote(title, safe="")

                for scene_idx, (scene_title, dialogues) in enumerate(scenes):
                    safe_title = re.sub(r'[^\w\u4e00-\u9fff]', '_', title)
                    doc = Document(
                        doc_id=f"{doc_type_str}_{safe_title}_{scene_idx:03d}",
                        doc_type=DocType.COMPANION_MISSION if "companion" in doc_type_str else DocType.MAIN_MISSION,
                        title=scene_title or title,
                        dialogues=dialogues,
                        metadata={
                            "source": "wiki",
                            "category": category,
                            "mission_title": title,
                            "scene_index": scene_idx,
                            "scene_title": scene_title,
                            "wiki_url": wiki_url,
                            "sentence_count": len(dialogues),
                        },
                    )
                    category_docs.append(doc)

            # 写入文件
            out_path = out_dir / filename
            with open(out_path, "w", encoding="utf-8") as f:
                for doc in category_docs:
                    record = {
                        "doc_id": doc.doc_id,
                        "doc_type": doc.doc_type.value,
                        "title": doc.title,
                        "dialogues": [
                            {"sentence_id": dl.sentence_id, "speaker": dl.speaker, "text": dl.text}
                            for dl in doc.dialogues
                        ],
                        "metadata": doc.metadata,
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

            total_lines = sum(d.metadata["sentence_count"] for d in category_docs)
            logger.info(
                "  → %s/%s: %d scenes, %d lines (%d pages not found)",
                cfg.get("output_dir"), filename, len(category_docs), total_lines, not_found,
            )
            all_docs.extend(category_docs)

        logger.info("WikiCategorySceneExtractor done: %d total scene docs", len(all_docs))
        return all_docs
