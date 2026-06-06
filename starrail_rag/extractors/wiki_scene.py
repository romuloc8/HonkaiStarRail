"""
场景级 Wiki 爬取器。

在 WikiMissionExtractor 基础上改造，将每个 wiki 任务页的 === 小节 ===
解析为独立的场景文档，而不是整个任务合为一个文档。

输出结构：
  output/main_story/{章节序号}_{章节名}.jsonl
  output/companion/missions.jsonl
  output/continuance/missions.jsonl
  output/adventure/missions.jsonl
  output/activity/missions.jsonl

每条文档（场景）格式：
  doc_id          scene 级别唯一 ID
  doc_type        "main_mission_scene" | "companion_scene" | ...
  parent_mission  父任务标题
  scene_title     本场景标题（来自 wiki === 标题 ===）
  scene_index     在任务内的序号（0-based）
  dialogues       本场景的对话行
  metadata        章节名、任务 ID、wiki_url 等
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import quote

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
    CHAPTER_NAMES,
)

# Inline helpers not exported from wiki_mission
def _clean_text(text: str) -> str:
    return re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text).strip()

_DIALOGUE_RE = re.compile(r'^(?P<speaker>[^：\n]{1,30})：(?P<text>.+)$', re.UNICODE)

_NON_DIALOGUE_PATTERNS = [
    re.compile(r'^任务奖励'), re.compile(r'^折叠$'), re.compile(r'^展开'),
    re.compile(r'^过场动画'), re.compile(r'^彩蛋'), re.compile(r'^歌词'),
    re.compile(r'^\['), re.compile(r'^MediaWiki:'),
]

logger = logging.getLogger(__name__)

OUTPUT_ROOT = Path("/workspace/output")

# 章节名 → 输出文件夹内的前缀序号
CHAPTER_ORDER = {name: f"{i+1:02d}" for i, name in enumerate(CHAPTER_NAMES)}


def _parse_wikitext_scenes(
    wikitext: str,
    category: str = "开拓任务",
) -> list[tuple[str, list[DialogueLine], list[DialogueBranch]]]:
    """
    将 wikitext 解析为场景列表。
    每个场景是 (scene_title, dialogues, branches) 的元组。
    """
    placeholder_map: dict[str, dict] = {}

    def _mark_and_remove(m: re.Match) -> str:
        result = _expand_plot_options(m.group(1))
        key = f"__BRANCH_{len(placeholder_map)}__"
        placeholder_map[key] = result
        return "\n" + key + "\n"

    wikitext_marked = _PLOT_OPTION_RE.sub(_mark_and_remove, wikitext)
    lines = wikitext_marked.splitlines()

    scenes: list[tuple[str, list[DialogueLine], list[DialogueBranch]]] = []
    current_title = ""
    current_dialogues: list[DialogueLine] = []
    current_branches: list[DialogueBranch] = []
    seen: set[tuple[str, str]] = set()
    fake_id = 0
    in_skip = False

    def _flush():
        nonlocal current_dialogues, current_branches, seen
        if current_dialogues:
            scenes.append((current_title, current_dialogues, current_branches))
        current_dialogues = []
        current_branches = []
        seen = set()

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        hm = _HEADING_RE.match(line)
        if hm:
            heading_text = hm.group(1).strip()
            heading_level = len(re.match(r'^(=+)', line).group(1))
            if heading_level >= 3:
                _flush()
                current_title = heading_text
            in_skip = heading_text in _SKIP_SECTIONS
            continue

        if in_skip:
            continue

        if line in placeholder_map:
            br_result = placeholder_map[line]
            new_lines, new_branches = _branch_result_to_dialogue_lines(br_result, fake_id)
            for dl in new_lines:
                key = (dl.speaker, dl.text)
                if key not in seen:
                    seen.add(key)
                    current_dialogues.append(dl)
                    fake_id = dl.sentence_id
            current_branches.extend(new_branches)
            continue

        if _SKIP_TEMPLATE_RE.match(line):
            continue
        if line.startswith("|") or line.startswith("----"):
            continue

        dm = _BULLET_DIALOGUE_RE.match(line)
        if not dm:
            continue

        speaker = dm.group("speaker").strip()
        text = dm.group("text").strip()
        if not text or not speaker:
            continue

        key = (speaker, text)
        if key in seen:
            continue
        seen.add(key)

        fake_id -= 1
        is_player = (speaker == "开拓者")
        current_dialogues.append(
            DialogueLine(sentence_id=fake_id, speaker=speaker, text=text,
                         is_player_utterance=is_player)
        )

    _flush()

    return [(t, d, b) for t, d, b in scenes if d]


class WikiSceneExtractor(BaseExtractor):
    """
    场景级 Wiki 爬取器。

    将每个任务的 wiki 页面按 === 小节 === 分割为独立场景文档，
    并将结果写入按章节组织的 JSONL 文件。

    参数
    ----
    output_root : 输出根目录（默认 /workspace/output）
    mission_types : 要爬取的 MainMission.Type（默认 ["Main"]）
    request_delay : 请求间隔秒数
    """

    def __init__(
        self,
        data_root: str | Path,
        resolver: TextMapResolver,
        output_root: str | Path = OUTPUT_ROOT,
        mission_types: list[str] | None = None,
        request_delay: float = 1.2,
    ) -> None:
        super().__init__(data_root, resolver)
        self.output_root = Path(output_root)
        self._mission_types = set(mission_types or ["Main"])
        self._delay = request_delay
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "StarRailRAG/1.0 (research)"

    @property
    def name(self) -> str:
        return "WikiSceneExtractor"

    def _load_missions(self):
        import json as _json
        with open(self.data_root / "ExcelOutput" / "MainMission.json", encoding="utf-8") as f:
            all_missions = _json.load(f)
        return [m for m in all_missions if m.get("Type") in self._mission_types]

    def _load_chapter_map(self) -> dict[int, str]:
        import json as _json
        with open(self.data_root / "ExcelOutput" / "MissionChapterConfig.json", encoding="utf-8") as f:
            rows = _json.load(f)
        return {
            row["ID"]: self.resolver.resolve_field(row.get("ChapterName", ""))
            for row in rows
        }

    def extract(self) -> list[Document]:
        missions = self._load_missions()
        chapter_map = self._load_chapter_map()

        # 按章节分组写入文件
        # chapter_name → list of scene Documents
        chapter_docs: dict[str, list[Document]] = {}
        wikitext_cache: dict[str, list] = {}
        not_found = 0
        total_scenes = 0

        logger.info("Starting scene-level extraction for %d missions", len(missions))

        for mission in missions:
            mid = mission.get("MainMissionID", 0)
            chapter_id = mission.get("ChapterID", 0)
            chapter_name = chapter_map.get(chapter_id, "")
            mission_name = self.resolver.resolve_field(mission.get("Name", {}))

            if not mission_name:
                continue

            # 获取 wikitext（带缓存）
            if mission_name in wikitext_cache:
                scenes = wikitext_cache[mission_name]
            else:
                wikitext = _fetch_wikitext(mission_name, self._session)
                time.sleep(self._delay)
                if wikitext is None:
                    not_found += 1
                    wikitext_cache[mission_name] = []
                    continue
                scenes = _parse_wikitext_scenes(wikitext, category="开拓任务")
                wikitext_cache[mission_name] = scenes

            if not scenes:
                continue

            wiki_url = _WIKI_BASE + quote(mission_name, safe="")

            for scene_idx, (scene_title, dialogues, branches) in enumerate(scenes):
                scene_id = f"scene_{mid}_{scene_idx:03d}"
                doc = Document(
                    doc_id=scene_id,
                    doc_type=DocType.MAIN_MISSION,
                    title=scene_title or mission_name,
                    dialogues=dialogues,
                    branches=branches,
                    narrative_layer=NarrativeLayer.L1_CONFIRMED,
                    metadata={
                        "source": "wiki",
                        "mission_id": mid,
                        "mission_title": mission_name,
                        "chapter_name": chapter_name,
                        "scene_index": scene_idx,
                        "scene_title": scene_title,
                        "wiki_url": wiki_url,
                        "sentence_count": len(dialogues),
                        "has_player_choices": bool(branches),
                        "narrative_layer": NarrativeLayer.L1_CONFIRMED.value,
                    },
                )
                chapter_docs.setdefault(chapter_name, []).append(doc)
                total_scenes += 1

            logger.debug("[%d] %s → %d scenes", mid, mission_name, len(scenes))

        # 写入文件
        self._write_output(chapter_docs)

        logger.info(
            "Scene extraction done: %d scenes across %d chapters, %d missions not found",
            total_scenes, len(chapter_docs), not_found,
        )
        # 返回所有 doc（供管线统计用）
        return [doc for docs in chapter_docs.values() for doc in docs]

    def _write_output(self, chapter_docs: dict[str, list[Document]]) -> None:
        """将场景文档按章节写入 output/main_story/ 目录。"""
        import json as _json

        out_dir = self.output_root / "main_story"
        out_dir.mkdir(parents=True, exist_ok=True)

        for chapter_name, docs in sorted(
            chapter_docs.items(),
            key=lambda x: min(d.metadata.get("mission_id", 0) for d in x[1])
        ):
            prefix = CHAPTER_ORDER.get(chapter_name, "99")
            # 文件名：序号_章节名（去除特殊字符）
            safe_name = re.sub(r'[^\w\u4e00-\u9fff·，。、—]', '_', chapter_name)
            filename = f"{prefix}_{safe_name}.jsonl"
            filepath = out_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                for doc in docs:
                    record = {
                        "doc_id": doc.doc_id,
                        "doc_type": doc.doc_type.value,
                        "title": doc.title,
                        "dialogues": [
                            {"sentence_id": dl.sentence_id,
                             "speaker": dl.speaker,
                             "text": dl.text}
                            for dl in doc.dialogues
                        ],
                        "metadata": doc.metadata,
                    }
                    f.write(_json.dumps(record, ensure_ascii=False) + "\n")

            logger.info(
                "  → %s (%d scenes, %d lines)",
                filename,
                len(docs),
                sum(d.metadata["sentence_count"] for d in docs),
            )
