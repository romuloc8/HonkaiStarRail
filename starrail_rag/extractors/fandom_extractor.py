"""
Fandom Wiki 爬取器：使用 MediaWiki API 获取游戏官方 Data Bank 和时间线。

来源：
  - Data_Bank/Aeons, Data_Bank/Factions, Data_Bank/Terms
  - Aeon (总览), Faction (总览)
  - Timeline

用法：
    python3 -m starrail_rag.extractors.fandom_extractor

输出：
    output/lore/fandom_databank.jsonl
    output/lore/fandom_timeline.jsonl
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import requests

from starrail_rag.core.models import DocType, Document, NarrativeLayer

logger = logging.getLogger(__name__)
OUTPUT = Path("/workspace/output")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; StarRailRAGBot/1.0; +https://github.com/romuloc8)",
    "Accept": "application/json",
}
_FANDOM_API = "https://honkai-star-rail.fandom.com/api.php"

PAGE_CONFIGS = [
    ("Aeon",              "星神（Aeon）总览",           NarrativeLayer.L1_CONFIRMED, "confirmed"),
    ("Data_Bank/Aeons",   "Data Bank — Aeons",         NarrativeLayer.L1_CONFIRMED, "confirmed"),
    ("Faction",           "阵营（Faction）总览",         NarrativeLayer.L1_CONFIRMED, "confirmed"),
    ("Data_Bank/Factions","Data Bank — Factions",      NarrativeLayer.L1_CONFIRMED, "confirmed"),
    ("Data_Bank/Terms",   "Data Bank — Terms（术语）",  NarrativeLayer.L1_CONFIRMED, "confirmed"),
    ("Timeline",          "星穹铁道时间线",              NarrativeLayer.L2_HISTORICAL_RECORD, "historical_record"),
]


def _fetch_wikitext(page_title: str, max_retries: int = 3) -> str | None:
    """使用 MediaWiki API 获取 wikitext（比直接 HTTP 更不易被封锁）。"""
    params = {
        "action": "query",
        "titles": page_title,
        "prop": "revisions",
        "rvprop": "content",
        "format": "json",
        "rvslots": "main",
    }
    for attempt in range(max_retries):
        try:
            resp = requests.get(_FANDOM_API, params=params, headers=_HEADERS, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                pages = data.get("query", {}).get("pages", {})
                for pid, page in pages.items():
                    if int(pid) < 0:
                        logger.warning("页面不存在: %s", page_title)
                        return None
                    revs = page.get("revisions", [])
                    if revs:
                        return revs[0].get("slots", {}).get("main", {}).get("*", "")
                return None
            logger.warning("HTTP %d for '%s'", resp.status_code, page_title)
        except Exception as e:
            logger.warning("Fetch failed ('%s'): %s", page_title, e)
        time.sleep(2 ** attempt)
    return None


def _wikitext_to_text(wikitext: str) -> str:
    """将 Wikitext 转换为纯文本，保留核心 lore 内容。"""
    # 移除模板（保留可能含 lore 的 Data Bank 模板内容）
    # 先提取 Data Bank 模板内的描述
    databank_content = re.findall(r'\{\{Data Bank\|[^|]+\|([^}]+)\}\}', wikitext)
    # 移除 wiki 模板
    text = re.sub(r'\{\{[^{}]*\}\}', '', wikitext, flags=re.DOTALL)
    # 移除 wiki 链接，保留链接文字
    text = re.sub(r'\[\[(?:[^|]*\|)?([^\]]+)\]\]', r'\1', text)
    # 移除外部链接
    text = re.sub(r'\[https?://\S+\s+([^\]]+)\]', r'\1', text)
    text = re.sub(r'\[https?://\S+\]', '', text)
    # 移除标题标记，转为文字
    text = re.sub(r'={2,}\s*(.+?)\s*={2,}', r'\n## \1\n', text)
    # 移除 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 移除文件/图片引用
    text = re.sub(r'\[\[(?:File|Image):[^\]]+\]\]', '', text, flags=re.IGNORECASE)
    # 清理空白
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    # 追加 Data Bank 模板内容
    if databank_content:
        text += "\n\n## Data Bank 条目\n" + "\n".join(databank_content)
    return text.strip()


def extract_all_fandom(output_dir: Path = OUTPUT) -> dict[str, list[Document]]:
    results: dict[str, list[Document]] = {}
    db_docs: list[Document] = []
    tl_docs: list[Document] = []

    for page_title, label, layer, reliability in PAGE_CONFIGS:
        logger.info("爬取: %s ...", page_title)
        wikitext = _fetch_wikitext(page_title)
        time.sleep(1.2)

        if not wikitext:
            logger.warning("  跳过: 无法获取 '%s'", page_title)
            continue

        content = _wikitext_to_text(wikitext)
        if len(content) < 100:
            logger.warning("  内容太短 (%d chars): %s", len(content), page_title)
            continue

        # Timeline 单独处理
        is_timeline = "Timeline" in page_title
        target = tl_docs if is_timeline else db_docs

        doc = Document(
            doc_id=f"fandom_{page_title.lower().replace('/', '_').replace(' ', '_')}",
            doc_type=DocType.BOOK if is_timeline else DocType.ITEM_LORE,
            title=label,
            body=f"# {label}\n来源：https://honkai-star-rail.fandom.com/wiki/{page_title}\n\n{content[:10000]}",
            narrative_layer=layer,
            metadata={
                "source_type":    "fandom_wiki",
                "page_title":     page_title,
                "wiki_url":       f"https://honkai-star-rail.fandom.com/wiki/{page_title}",
                "chapter_anchor": "unknown",
                "narrative_layer": layer.value,
                "reliability":    reliability,
                "char_count":     len(content),
            },
        )
        target.append(doc)
        logger.info("  ✓ %s: %d 字符", label, len(content))

    # 保存
    (output_dir / "lore").mkdir(parents=True, exist_ok=True)
    for name, docs, fname in [
        ("databank", db_docs, "fandom_databank.jsonl"),
        ("timeline", tl_docs, "fandom_timeline.jsonl"),
    ]:
        path = output_dir / "lore" / fname
        with open(path, "w", encoding="utf-8") as f:
            for doc in docs:
                f.write(json.dumps({
                    "doc_id": doc.doc_id, "doc_type": doc.doc_type.value,
                    "title": doc.title, "body": doc.body,
                    "dialogues": [], "metadata": doc.metadata,
                }, ensure_ascii=False) + "\n")
        logger.info("✓ %s → %s (%d 条)", name, path, len(docs))
        results[name] = docs

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    extract_all_fandom()
