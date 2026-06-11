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

from starrail_rag.core.models import (
    DialogueBranch, DialogueLine, DocType, Document, NarrativeLayer,
    DOCTYPE_TO_NARRATIVE_LAYER,
)
from starrail_rag.core.textmap import TextMapResolver
from starrail_rag.extractors.base import BaseExtractor
from starrail_rag.extractors.wiki_mission import (
    _fetch_wikitext,
    _expand_plot_options,
    _branch_result_to_dialogue_lines,
    _WIKI_BASE,
    _SKIP_SECTIONS,
    _HEADING_RE,
    _SKIP_TEMPLATE_RE,
    _BULLET_DIALOGUE_RE,
    _PLOT_OPTION_RE,
)
from urllib.parse import quote as _url_quote
from starrail_rag.extractors.wiki_scene import _parse_wikitext_scenes

# 从 {{任务|...}} 模板提取字段
_TEMPLATE_FIELD_RE = re.compile(r'\|(\w+)\s*=\s*([^\|\n\}]+)')

def _extract_template_fields(wikitext: str) -> dict[str, str]:
    """从 wikitext 的 {{任务|...}} 模板提取关键字段。"""
    fields = {}
    # 找到 {{任务| 到 }} 之间的内容
    m = re.search(r'\{\{任务(.*?)\}\}', wikitext, re.DOTALL)
    if not m:
        return fields
    block = m.group(1)
    for fm in _TEMPLATE_FIELD_RE.finditer(block):
        key = fm.group(1).strip()
        val = fm.group(2).strip()
        # 清理 wiki 链接
        val = re.sub(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', r'\1', val)
        val = re.sub(r'\{\{[^}]+\}\}', '', val).strip()
        if val:
            fields[key] = val
    return fields


def _normalize_region(region: str) -> str:
    """将任务地区规范化为星球/大区级别。"""
    region = region.strip()
    # 按子区域前缀匹配
    for canon, prefixes in [
        ('空间站「黑塔」', ['空间站']),
        ('雅利洛-Ⅵ', ['雅利洛', '贝洛伯格', '磐岩镇', '铆钉镇']),
        ('仙舟「罗浮」', ['仙舟「罗浮」', '罗浮', '仙舟罗浮']),
        ('星穹列车', ['星穹列车']),
        ('匹诺康尼', ['匹诺康尼']),
        ('翁法罗斯', ['翁法罗斯', '奥赫玛', '悬锋', '哀地里亚', '神悟树庭']),
        ('二相乐园', ['二相乐园', '哈托彼亚']),
        ('寰宇万象', ['寰宇万象']),
    ]:
        for prefix in prefixes:
            if region.startswith(prefix) or prefix in region:
                return canon
    return region or '其他'


def _normalize_version(version: str) -> str:
    """将版本号归组为大版本（1.x, 2.x, ...）。"""
    m = re.match(r'^(\d+)\.', version.strip())
    if m:
        return f"{m.group(1)}.x"
    return version or '其他'

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("/workspace/output")
_API_BASE = "https://wiki.biligame.com/sr/api.php"

CATEGORY_CONFIG = {
    "同行任务": {
        "output_dir": "companion",
        "group_by": "character",      # |角色= 字段
        "doc_type": "companion_scene",
    },
    "开拓续闻": {
        "output_dir": "continuance",
        "group_by": "region",         # |任务地区= → normalize 到星球级
        "doc_type": "main_mission_scene",
    },
    "冒险任务": {
        "output_dir": "adventure",
        "group_by": "region",
        "doc_type": "main_mission_scene",
    },
    "活动任务": {
        "output_dir": "activity",
        "group_by": "version",        # |所属版本= → 大版本 1.x / 2.x
        "doc_type": "main_mission_scene",
    },
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
            group_by = cfg.get("group_by", "region")
            doc_type_str = cfg.get("doc_type", "main_mission_scene")

            logger.info("Fetching category: %s → %s/ (group by %s)", category, cfg.get("output_dir"), group_by)
            titles = _get_category_members(category, self._session)
            logger.info("  %d pages in Category:%s", len(titles), category)

            wikitext_cache: dict[str, tuple[list, str]] = {}  # title → (scenes, group_key)
            # group_key → list of Documents
            grouped_docs: dict[str, list[Document]] = {}
            not_found = 0

            for title in titles:
                if title in wikitext_cache:
                    scenes, group_key = wikitext_cache[title]
                else:
                    wikitext = _fetch_wikitext(title, self._session)
                    time.sleep(self._delay)
                    if wikitext is None:
                        not_found += 1
                        wikitext_cache[title] = ([], "")
                        continue

                    scenes = _parse_wikitext_scenes(wikitext)
                    fields = _extract_template_fields(wikitext)

                    # 确定分组键
                    if group_by == "character":
                        raw = fields.get("角色", fields.get("出场人物", ""))
                        # 取第一个角色名（可能有多个）
                        group_key = re.split(r'[、，,/]', raw)[0].strip() or "其他"
                    elif group_by == "version":
                        raw = fields.get("所属版本", "")
                        group_key = _normalize_version(raw)
                    else:  # region
                        raw = fields.get("任务地区", "")
                        group_key = _normalize_region(raw)

                    wikitext_cache[title] = (scenes, group_key)

                if not scenes:
                    continue

                wiki_url = _WIKI_BASE + _url_quote(title, safe="")

                for scene_idx, (scene_title, dialogues, branches) in enumerate(scenes):
                    safe_title = re.sub(r'[^\w\u4e00-\u9fff]', '_', title)
                    # 根据任务类型推断叙事层次
                    nl = DOCTYPE_TO_NARRATIVE_LAYER.get(category, NarrativeLayer.L3_CHARACTER_ACCOUNT)
                    doc = Document(
                        doc_id=f"{doc_type_str}_{safe_title}_{scene_idx:03d}",
                        doc_type=DocType.COMPANION_MISSION if "companion" in doc_type_str else DocType.MAIN_MISSION,
                        title=scene_title or title,
                        dialogues=dialogues,
                        branches=branches,
                        narrative_layer=nl,
                        metadata={
                            "source": "wiki",
                            "category": category,
                            "mission_title": title,
                            "scene_index": scene_idx,
                            "scene_title": scene_title,
                            "group": group_key,
                            "wiki_url": wiki_url,
                            "sentence_count": len(dialogues),
                            "has_player_choices": bool(branches),
                            "narrative_layer": nl.value,
                        },
                    )
                    grouped_docs.setdefault(group_key, []).append(doc)

            # 写入分组文件
            self._write_grouped_output(out_dir, grouped_docs, category)
            category_docs = [doc for docs in grouped_docs.values() for doc in docs]
            total_lines = sum(d.metadata["sentence_count"] for d in category_docs)
            logger.info(
                "  → %s/: %d groups, %d scenes, %d lines (%d not found)",
                cfg.get("output_dir"), len(grouped_docs), len(category_docs), total_lines, not_found,
            )
            all_docs.extend(category_docs)

        logger.info("WikiCategorySceneExtractor done: %d total scene docs", len(all_docs))
        return all_docs

    def _write_grouped_output(self, out_dir: Path, grouped_docs: dict[str, list[Document]], category: str) -> None:
        """按分组写入多个 JSONL 文件，文件名为分组键（安全化）。"""
        # 清空旧的 missions.jsonl（如果存在）
        old_single = out_dir / "missions.jsonl"
        if old_single.exists():
            old_single.unlink()

        for group_key, docs in sorted(grouped_docs.items()):
            safe_name = re.sub(r'[^\w\u4e00-\u9fff·，「」\-]', '_', group_key).strip('_')
            safe_name = re.sub(r'_+', '_', safe_name)
            filename = f"{safe_name}.jsonl"
            with open(out_dir / filename, "w", encoding="utf-8") as f:
                for doc in docs:
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
            lines = sum(d.metadata["sentence_count"] for d in docs)
            logger.info("    %s: %d scenes, %d lines", filename, len(docs), lines)
