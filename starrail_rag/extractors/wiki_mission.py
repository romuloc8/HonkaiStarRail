"""
BiliWiki 开拓任务剧情提取器。

数据来源: https://wiki.biligame.com/sr/

策略:
  1. 从游戏数据（MainMission.json + TextMapCHS）拿到所有已解析的任务名称
  2. 直接用任务名构建 wiki URL（URL = base + quote(任务名)）
  3. 获取 wikitext 原始格式（?action=raw），解析对话文本

Wikitext 对话格式:
  * 普通台词:   *角色名：台词内容
  * 分支选项:   {{剧情选项|选项1=...|剧情1=*角色：台词|选项2=...|剧情2=...}}
  * 旁白:       *(旁白)：内容  或 *（括号内文字）：内容
  * 标题:       === 小节名称 ===
  * 跳过:       {{任务|...}}  {{任务描述|...}}  ==剧情梗概==
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

from starrail_rag.core.models import DialogueLine, DocType, Document
from starrail_rag.core.textmap import TextMapResolver
from starrail_rag.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

_WIKI_BASE = "https://wiki.biligame.com/sr/"

# 所有开拓任务章节名称（用于 metadata，顺序即游戏顺序）
CHAPTER_NAMES: list[str] = [
    "今天是昨天的明天",
    "于枯索的冬夜里",
    "于曈昽的骄阳下",
    "乘槎驭风仙窟游",
    "云树百丈蔽重楼",
    "劫波渡尽战云收",
    "喧哗与骚动",
    "鸽群中的猫",
    "在我们的时代里",
    "记忆是梦的开场白",
    "再见，匹诺康尼",
    "在第八日启程",
    "落木逐火英雄纪",
    "门扉之启，王座之终",
    "走过安眠地的花丛",
    "在黎明升起时坠落",
    "因为太阳将要毁伤",
    "英雄未死之前",
    "于长夜重返大地",
    "成为昨日的明天",
    "欢迎来到乐园",
    "献给破晓的失控",
    "如是，众生欢笑不已",
]

# -----------------------------------------------------------------------
# Wikitext 解析
# -----------------------------------------------------------------------

# 普通对话行：*Speaker：Text（* 开头，中文冒号分割）
_BULLET_DIALOGUE_RE = re.compile(
    r'^\*(?P<speaker>[^：\n*{]{1,30})：(?P<text>.+)$'
)

# {{剧情选项}} 模板的完整块（可能多行）
_PLOT_OPTION_RE = re.compile(r'\{\{剧情选项(.*?)\}\}', re.DOTALL)

# 提取选项文本：选项N=<text> 或 选项N =<text>
_OPTION_TEXT_RE = re.compile(r'选项\d+\s*=\s*([^|}\n]+)')

# 提取某一支剧情内的对话行：剧情N=...*Speaker：Text...
_OPTION_BRANCH_RE = re.compile(r'剧情\d+\s*=((?:[^|]|\|(?!选项|\|))*)', re.DOTALL)

# 在一段剧情文本内提取 *Speaker：Text
_OPTION_DIALOGUE_RE = re.compile(
    r'\*(?P<speaker>[^：\n*{]{1,30})：(?P<text>[^\n*|{}]+)'
)

# 剧情描述块（跳过不作为对话）
_TASK_DESC_RE = re.compile(r'\{\{任务描述\|.*?\}\}', re.DOTALL)

# 折叠/展开标签（wiki 折叠 template）
_FOLD_RE = re.compile(r'\{\{折叠|展开[^}]*\}\}')

# 章节标题
_HEADING_RE = re.compile(r'^={2,4}\s*(.+?)\s*={2,4}$')

# 跳过的章节（不含对话）
_SKIP_SECTIONS = frozenset([
    "任务流程", "任务相关", "任务条件", "前置任务",
    "后续任务", "系列任务", "任务奖励", "剧情梗概",
    "相关成就", "相关道具", "相关书籍", "出场人物",
])

# 跳过的 wikitext 模板行（以 {{ 开头且不是剧情选项）
_SKIP_TEMPLATE_RE = re.compile(r'^\{\{(?!剧情选项)')


def _expand_plot_options(block_content: str) -> list[str]:
    """
    解析 {{剧情选项}} 模板内容，返回展开后的 *Speaker：Text 行列表。

    规则:
    - 提取所有 选项N 文本作为 *开拓者：<选项> 行
    - 提取所有 剧情N 的 NPC 响应行
    - 若所有分支 NPC 响应相同 → 合并选项，NPC 响应只写一次
    - 若分支响应不同 → 每个分支完整保留（体现选项的平行性）
    """
    # 提取 选项N 文本
    option_texts = re.findall(r'选项\d+\s*=\s*([^|}\n]+)', block_content)

    # 提取各分支 剧情N 对话
    branches: list[list[str]] = []
    for bm in re.finditer(r'剧情\d+\s*=((?:[^|]|\|(?!选项\d))*)', block_content, re.DOTALL):
        branch_text = bm.group(1)
        lines_in_branch = [
            f"*{m.group('speaker')}：{m.group('text').strip()}"
            for m in _OPTION_DIALOGUE_RE.finditer(branch_text)
        ]
        if lines_in_branch:
            branches.append(lines_in_branch)

    if not branches:
        return []

    all_same = len(set(tuple(b) for b in branches)) == 1

    result: list[str] = []
    if all_same:
        # 响应一致 → 合并选项
        if option_texts:
            merged = " / ".join(t.strip() for t in option_texts if t.strip())
            result.append(f"*开拓者：{merged}")
        result.extend(branches[0])
    else:
        # 响应不同 → 平行展示每个分支
        for opt_text, branch_lines in zip(option_texts, branches):
            if opt_text.strip():
                result.append(f"*开拓者：{opt_text.strip()}")
            result.extend(branch_lines)

    return result


def _parse_wikitext_dialogues(wikitext: str) -> list[DialogueLine]:
    """
    从 wikitext 中提取对话行，返回有序 DialogueLine 列表。

    步骤:
    1. 展开 {{剧情选项}} 块（保留玩家选项文本 + 平行/合并分支）
    2. 按行扫描，跳过非剧情 section
    3. 提取 *Speaker：Text 格式行
    4. 去重（相同 speaker+text 只保留首次）
    """
    # 展开分支选项，替换原块
    extra_lines: list[str] = []

    def _expand_and_remove(m: re.Match) -> str:
        expanded = _expand_plot_options(m.group(1))
        extra_lines.extend(expanded)
        return ""

    wikitext_clean = _PLOT_OPTION_RE.sub(_expand_and_remove, wikitext)
    wikitext_clean += "\n" + "\n".join(extra_lines)

    lines = wikitext_clean.splitlines()
    dialogues: list[DialogueLine] = []
    seen: set[tuple[str, str]] = set()
    fake_id = 0
    in_skip = False

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        hm = _HEADING_RE.match(line)
        if hm:
            in_skip = hm.group(1).strip() in _SKIP_SECTIONS
            continue

        if in_skip:
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
        dialogues.append(DialogueLine(sentence_id=fake_id, speaker=speaker, text=text))

    return dialogues


# -----------------------------------------------------------------------
# HTTP helpers
# -----------------------------------------------------------------------

def _wiki_raw_url(page_name: str) -> str:
    return (
        "https://wiki.biligame.com/sr/index.php?title="
        + quote(page_name, safe="")
        + "&action=raw"
    )


def _fetch_wikitext(
    page_name: str,
    session: requests.Session,
    timeout: int = 15,
    max_retries: int = 3,
) -> str | None:
    url = _wiki_raw_url(page_name)
    for attempt in range(max_retries):
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 404:
                logger.debug("Wiki page not found: '%s'", page_name)
                return None
            # Rate-limited or server error — back off and retry
            wait = 2 ** attempt
            logger.debug(
                "HTTP %d for '%s', retry %d/%d in %ds",
                resp.status_code, page_name, attempt + 1, max_retries, wait,
            )
            time.sleep(wait)
        except requests.RequestException as exc:
            wait = 2 ** attempt
            logger.debug("Network error for '%s': %s, retry in %ds", page_name, exc, wait)
            time.sleep(wait)
    logger.warning("Failed to fetch wiki page '%s' after %d attempts", page_name, max_retries)
    return None


# -----------------------------------------------------------------------
# Extractor
# -----------------------------------------------------------------------

class WikiMissionExtractor(BaseExtractor):
    """
    从 BiliWiki 抓取开拓任务对话文本。

    流程:
    1. 读取游戏数据中的 MainMission（Type=Main），用 TextMapCHS 解析任务名
    2. 用任务名直接构建 wiki URL（?action=raw 获取 wikitext）
    3. 解析 wikitext，提取对话行

    相比游戏 JSON 提取，wiki 版本包含:
    - CG 场景字幕（游戏 dump 里缺失的 .playable 内容）
    - 所有分支选项的完整文本
    - 额外对话（检查场景物品触发）
    - 后期章节完整数据（匹诺康尼 / 翁法罗斯 / 乐园）

    Parameters
    ----------
    data_root, resolver : 继承自 BaseExtractor。
    chapters : 限定章节名称列表（None = 全部）。
    mission_types : MainMission.Type 筛选（默认 ["Main"]）。
    request_delay : 每次 HTTP 请求间隔（秒）。
    """

    def __init__(
        self,
        data_root: str | Path,
        resolver: TextMapResolver,
        chapters: list[str] | None = None,
        mission_types: list[str] | None = None,
        request_delay: float = 1.0,
    ) -> None:
        super().__init__(data_root, resolver)
        self._chapters = set(chapters) if chapters else None
        self._mission_types = set(mission_types or ["Main"])
        self._delay = request_delay
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "StarRailRAG/1.0 (research project)"
        })

    @property
    def name(self) -> str:
        return "WikiMissionExtractor"

    def _load_missions(self) -> list[dict]:
        path = self.data_root / "ExcelOutput" / "MainMission.json"
        with open(path, encoding="utf-8") as f:
            all_missions = json.load(f)
        return [
            m for m in all_missions
            if m.get("Type") in self._mission_types
        ]

    def _load_chapter_map(self) -> dict[int, str]:
        path = self.data_root / "ExcelOutput" / "MissionChapterConfig.json"
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        return {
            row["ID"]: self.resolver.resolve_field(row.get("ChapterName", ""))
            for row in rows
        }

    def extract(self) -> list[Document]:
        missions = self._load_missions()
        chapter_map = self._load_chapter_map()
        documents: list[Document] = []
        not_found = 0

        # Cache: wiki page name → parsed dialogues (避免同名任务重复请求)
        wikitext_cache: dict[str, list[DialogueLine]] = {}

        logger.info(
            "Starting wiki extraction for %d missions (delay=%.1fs)",
            len(missions), self._delay,
        )

        for mission in missions:
            mid = mission.get("MainMissionID", 0)
            chapter_id = mission.get("ChapterID", 0)
            chapter_name = chapter_map.get(chapter_id, "")

            # 章节过滤
            if self._chapters and chapter_name not in self._chapters:
                continue

            mission_name = self.resolver.resolve_field(mission.get("Name", {}))
            if not mission_name:
                logger.debug("Mission %d has no resolved name, skipping", mid)
                continue

            if mission_name in wikitext_cache:
                dialogues = wikitext_cache[mission_name]
            else:
                wikitext = _fetch_wikitext(mission_name, self._session)
                time.sleep(self._delay)
                if wikitext is None:
                    not_found += 1
                    wikitext_cache[mission_name] = []
                    logger.debug("No wiki page for mission %d '%s'", mid, mission_name)
                    continue
                dialogues = _parse_wikitext_dialogues(wikitext)
                wikitext_cache[mission_name] = dialogues

            doc = Document(
                doc_id=f"wiki_mission_{mid}",
                doc_type=DocType.MAIN_MISSION,
                title=mission_name,
                dialogues=dialogues,
                metadata={
                    "source": "wiki",
                    "mission_id": mid,
                    "mission_type": mission.get("Type", ""),
                    "chapter_id": chapter_id,
                    "chapter_name": chapter_name,
                    "wiki_url": _WIKI_BASE + quote(mission_name, safe=""),
                    "sentence_count": len(dialogues),
                },
            )
            documents.append(doc)
            logger.debug("  [%d] '%s': %d lines", mid, mission_name, len(dialogues))

        non_empty = sum(1 for d in documents if not d.is_empty())
        logger.info(
            "Wiki extraction done: %d docs (%d non-empty, %d not found on wiki), "
            "%d total dialogue lines",
            len(documents), non_empty, not_found,
            sum(d.metadata["sentence_count"] for d in documents),
        )
        return documents
