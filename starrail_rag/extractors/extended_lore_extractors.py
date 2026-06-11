"""
扩展 lore 提取器集合。

涵盖 6 个此前未索引的游戏数据来源：
  1. RogueMiracleDisplay  — 模拟宇宙奇物背景叙事 (249条)
  2. LoadingDesc          — 加载屏提示 (400条)
  3. AvatarRankConfig     — 角色星魂（Eidolon）描述 (594条)
  4. VoiceAtlas           — 角色语音台词图鉴 (4907条)
  5. RogueAeonStoryConfig — 天才俱乐部星神研究笔记 (26条) ★★★
  6. AvatarSkillConfig    — 技能名典故提取

用法：
    from starrail_rag.extractors.extended_lore_extractors import (
        extract_all_extended_lore
    )
    docs = extract_all_extended_lore('/workspace', resolver)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Callable

from starrail_rag.core.models import DocType, Document, NarrativeLayer
from starrail_rag.core.textmap import TextMapResolver
from starrail_rag.core.cleaner import CleaningPipeline

logger = logging.getLogger(__name__)

_EXCEL = Path("/workspace/ExcelOutput")
_OUTPUT = Path("/workspace/output")
_cleaner = CleaningPipeline()

# 过滤纯机制性文本（含参数占位符）
_MECHANICAL = re.compile(r'#\d+\[i\]|<unbreak>[^<]*</unbreak>|击碎\d+|施放\d+次')


def _clean(text: str) -> str:
    text = re.sub(r'<[^>]+>', '', text)          # HTML / 颜色标签
    text = re.sub(r'\{\{[^}]+\}\}', '', text)    # wiki 模板
    text = re.sub(r'<unbreak>(.*?)</unbreak>', r'\1', text)  # unbreak 标签
    return text.strip()


def _is_lore(text: str, min_len: int = 20) -> bool:
    if not text or len(text) < min_len:
        return False
    if _MECHANICAL.search(text):
        return False
    return True


def _load(filename: str) -> list[dict]:
    path = _EXCEL / filename
    if not path.exists():
        logger.warning("文件不存在: %s", path)
        return []
    data = json.load(open(path))
    return data if isinstance(data, list) else list(data.values())


# ─────────────────────────────────────────────────────────────────────────────
# 1. 模拟宇宙奇物背景叙事 (RogueMiracleDisplay)
# ─────────────────────────────────────────────────────────────────────────────

def extract_rogue_miracles(tr: TextMapResolver) -> list[Document]:
    items = _load("RogueMiracleDisplay.json")
    docs = []
    for item in items:
        name     = tr.resolve_field(item.get("MiracleName", ""))
        desc     = _clean(tr.resolve_field(item.get("MiracleDesc", "")))
        bg_desc  = _clean(tr.resolve_field(item.get("MiracleBGDesc", "")))
        if not name:
            continue
        # 背景描述是核心 lore 来源
        body_parts = []
        if bg_desc and _is_lore(bg_desc):
            body_parts.append(bg_desc)
        if desc and _is_lore(desc, min_len=30):
            body_parts.append(f"（效果说明）{desc}")
        if not body_parts:
            continue
        doc = Document(
            doc_id=f"miracle_{item.get('MiracleDisplayID', item.get('DisplayID', 0))}",
            doc_type=DocType.ITEM_LORE,
            title=f"模拟宇宙奇物·{name}",
            body=f"【奇物：{name}】\n" + "\n".join(body_parts),
            narrative_layer=NarrativeLayer.L7_SIMULATION,
            metadata={
                "source_type":    "rogue_miracle",
                "miracle_name":   name,
                "chapter_anchor": "unknown",
                "narrative_layer": NarrativeLayer.L7_SIMULATION.value,
                "reliability":    "confirmed",
            },
        )
        docs.append(doc)
    logger.info("奇物背景叙事: %d 条", len(docs))
    return docs


# ─────────────────────────────────────────────────────────────────────────────
# 2. 加载屏提示 (LoadingDesc)
# ─────────────────────────────────────────────────────────────────────────────

def extract_loading_descs(tr: TextMapResolver) -> list[Document]:
    items = _load("LoadingDesc.json")
    docs = []
    seen: set[str] = set()
    for item in items:
        # 字段名不固定，遍历找长文本
        texts = []
        for v in item.values():
            if isinstance(v, dict) and "Hash" in v:
                t = _clean(tr.resolve_field(v))
                if _is_lore(t, min_len=15):
                    texts.append(t)
        if not texts:
            continue
        body = "　".join(texts)  # 合并同一条目的多段
        if body in seen:
            continue
        seen.add(body)
        doc = Document(
            doc_id=f"loading_{len(docs):04d}",
            doc_type=DocType.ITEM_LORE,
            title="加载提示",
            body=body,
            narrative_layer=NarrativeLayer.L1_CONFIRMED,
            metadata={
                "source_type":    "loading_desc",
                "chapter_anchor": "unknown",
                "narrative_layer": NarrativeLayer.L1_CONFIRMED.value,
                "reliability":    "confirmed",
            },
        )
        docs.append(doc)
    logger.info("加载屏提示: %d 条", len(docs))
    return docs


# ─────────────────────────────────────────────────────────────────────────────
# 3. 角色星魂描述 (AvatarRankConfig)
# ─────────────────────────────────────────────────────────────────────────────

def extract_eidolons(tr: TextMapResolver) -> list[Document]:
    rank_items = _load("AvatarRankConfig.json")
    avatar_items = _load("AvatarConfig.json")
    # 建立 RankID 前缀 → 角色名 映射
    id_to_name: dict[str, str] = {}
    for a in avatar_items:
        aid = str(a.get("AvatarID") or a.get("ID") or "")
        name = tr.resolve_field(a.get("AvatarName", ""))
        if aid and name:
            id_to_name[aid] = name

    docs = []
    for item in rank_items:
        rank_id = str(item.get("RankID", ""))
        # RankID 格式：角色ID + 0X（星魂编号），角色ID 是前 4 位
        avatar_id_prefix = rank_id[:4]
        char_name = id_to_name.get(avatar_id_prefix, "")
        rank_num = item.get("Rank", 0)
        name = tr.resolve_field(item.get("Name", ""))
        desc = _clean(tr.resolve_field(item.get("Desc", "")))
        if not name or not desc:
            continue
        # 过滤纯数值型（含大量 #1[i] 后清洗仍短的）
        desc_clean = re.sub(r'<unbreak>\d+</unbreak>%?', 'N', desc)
        if len(desc_clean) < 20:
            continue
        doc = Document(
            doc_id=f"eidolon_{rank_id}",
            doc_type=DocType.CHARACTER_STORY,
            title=f"{char_name}·第{rank_num}星魂·{name}" if char_name else f"第{rank_num}星魂·{name}",
            body=f"【{char_name} 第{rank_num}星魂：{name}】\n{desc}",
            narrative_layer=NarrativeLayer.L1_CONFIRMED,
            metadata={
                "source_type":     "eidolon",
                "character_name":  char_name,
                "rank_number":     rank_num,
                "eidolon_name":    name,
                "chapter_anchor":  "unknown",
                "narrative_layer": NarrativeLayer.L1_CONFIRMED.value,
                "reliability":     "confirmed",
            },
        )
        docs.append(doc)
    logger.info("星魂描述: %d 条", len(docs))
    return docs


# ─────────────────────────────────────────────────────────────────────────────
# 4. 角色语音台词图鉴 (VoiceAtlas)
# ─────────────────────────────────────────────────────────────────────────────

def extract_voice_atlas(tr: TextMapResolver) -> list[Document]:
    atlas_items = _load("VoiceAtlas.json")
    avatar_items = _load("AvatarConfig.json")
    id_to_name: dict[int, str] = {}
    for a in avatar_items:
        aid = a.get("AvatarID") or a.get("ID")
        name = tr.resolve_field(a.get("AvatarName", ""))
        if aid and name:
            id_to_name[int(aid)] = name

    # 按角色 ID 聚合所有语音条目
    by_avatar: dict[int, list[tuple[str, str]]] = {}
    for item in atlas_items:
        avatar_id = int(item.get("AvatarID", 0))
        title = tr.resolve_field(item.get("VoiceTitle", ""))
        text  = _clean(tr.resolve_field(item.get("Voice_M", "")))
        if not title or not text or not _is_lore(text, min_len=10):
            continue
        # 过滤纯问候/道别等低 lore 条目
        if title in ("问候", "道别", "战斗开始", "战斗胜利", "即将倒地", "回复", "生命值不足"):
            continue
        by_avatar.setdefault(avatar_id, []).append((title, text))

    docs = []
    for avatar_id, entries in by_avatar.items():
        char_name = id_to_name.get(avatar_id, f"Avatar{avatar_id}")
        body_lines = [f"【{title}】\n{text}" for title, text in entries]
        doc = Document(
            doc_id=f"voice_{avatar_id}",
            doc_type=DocType.CHARACTER_STORY,
            title=f"{char_name}·语音台词",
            body=f"# {char_name} 语音台词\n\n" + "\n\n".join(body_lines),
            narrative_layer=NarrativeLayer.L3_CHARACTER_ACCOUNT,
            metadata={
                "source_type":     "voice_atlas",
                "character_name":  char_name,
                "avatar_id":       avatar_id,
                "voice_count":     len(entries),
                "chapter_anchor":  "unknown",
                "narrative_layer": NarrativeLayer.L3_CHARACTER_ACCOUNT.value,
                "reliability":     "character_account",
                "reliability_note": "角色第一人称自述，具有主观性；语音内容为官方录制，但表述为角色视角",
            },
        )
        docs.append(doc)
    logger.info("角色语音图鉴: %d 个角色，%d 条语音",
                len(docs), sum(len(v) for v in by_avatar.values()))
    return docs


# ─────────────────────────────────────────────────────────────────────────────
# 5. 天才俱乐部星神研究笔记 (RogueAeonStoryConfig) ★★★
# ─────────────────────────────────────────────────────────────────────────────

def extract_aeon_stories(tr: TextMapResolver) -> list[Document]:
    """
    模拟宇宙里，天才俱乐部成员（通常是黑塔）撰写的星神研究笔记。
    内容包含跨星神的历史关联、古代事件的记述，是 lore 密度最高的来源之一。
    可信度标注为 character_account（学者视角），但信息来源涉及实际档案记录。
    """
    items = _load("RogueAeonStoryConfig.json")
    docs = []
    # 按 AeonID 分组，将多段笔记合并
    by_aeon: dict[int, list[tuple[str, str]]] = {}
    for item in items:
        aeon_id = int(item.get("RogueAeonID", 0))
        story_name = tr.resolve_field(item.get("AeonStory_Name", ""))
        story_text = _clean(tr.resolve_field(item.get("AeonStory", "")))
        if story_text and _is_lore(story_text, min_len=30):
            by_aeon.setdefault(aeon_id, []).append((story_name, story_text))

    # 同时加载 DLC 版本（RogueDLCAeon 可能有更多）
    dlc_items = _load("RogueDLCAeon.json")

    # 获取星神名称
    aeon_display = _load("RogueAeonDisplay.json")
    aeon_id_to_name: dict[int, str] = {}
    for ad in aeon_display:
        # RogueAeonID 可能不直接可用，尝试 DisplayID
        name = tr.resolve_field(ad.get("RogueAeonName", ""))
        path = tr.resolve_field(ad.get("RogueAeonPathName2", ""))
        disp_id = ad.get("DisplayID", 0)
        if name and path:
            aeon_id_to_name[disp_id] = f"{name}（{path}星神）"

    for aeon_id, entries in by_aeon.items():
        aeon_name = aeon_id_to_name.get(aeon_id, f"星神{aeon_id}")
        body_lines = [f"【{name}】\n{text}" for name, text in entries]
        doc = Document(
            doc_id=f"aeon_story_{aeon_id}",
            doc_type=DocType.BOOK,
            title=f"星神研究笔记·{aeon_name}",
            body=f"# 天才俱乐部星神研究笔记：{aeon_name}\n\n" + "\n\n".join(body_lines),
            narrative_layer=NarrativeLayer.L2_HISTORICAL_RECORD,
            metadata={
                "source_type":    "aeon_story",
                "aeon_id":        aeon_id,
                "aeon_name":      aeon_name,
                "entry_count":    len(entries),
                "chapter_anchor": "unknown",
                "narrative_layer": NarrativeLayer.L2_HISTORICAL_RECORD.value,
                "reliability":    "historical_record",
                "reliability_note": "天才俱乐部（黑塔）基于档案记录撰写的研究笔记，学者视角有偏好但引用了实际证据",
            },
        )
        docs.append(doc)
    logger.info("星神研究笔记: %d 条（涵盖 %d 个星神）",
                sum(len(v) for v in by_aeon.values()), len(by_aeon))
    return docs


# ─────────────────────────────────────────────────────────────────────────────
# 6. 技能名典故提取 (AvatarSkillConfig)
# ─────────────────────────────────────────────────────────────────────────────

def extract_skill_cultural_names(tr: TextMapResolver) -> list[Document]:
    """
    提取角色技能名称。技能名（尤其仙舟角色）大量使用古典汉语典故，
    这些名称本身就是对角色文化背景的 lore 标注。
    """
    skill_items = _load("AvatarSkillConfig.json")
    avatar_items = _load("AvatarConfig.json")
    id_to_name: dict[str, str] = {}
    for a in avatar_items:
        aid = str(a.get("AvatarID") or a.get("ID") or "")
        name = tr.resolve_field(a.get("AvatarName", ""))
        if aid and name:
            id_to_name[aid] = name

    # 按角色聚合技能名
    by_avatar: dict[str, set[str]] = {}
    for item in skill_items:
        # AvatarSkillConfig 没有直接的 AvatarID 字段
        # SkillID 前 4 位是角色 ID
        skill_id = str(item.get("SkillID", ""))
        aid_prefix = skill_id[:4] if skill_id else ""
        skill_name = tr.resolve_field(item.get("SkillName", ""))
        if skill_name and len(skill_name) > 3 and aid_prefix:
            by_avatar.setdefault(aid_prefix, set()).add(skill_name)

    docs = []
    for aid_prefix, skill_names in by_avatar.items():
        char_name = id_to_name.get(aid_prefix, f"角色{aid_prefix}")
        # 过滤纯英文/数字名
        meaningful = [n for n in skill_names if re.search(r'[\u4e00-\u9fff]', n)]
        if len(meaningful) < 2:
            continue
        body = f"# {char_name} 技能名称\n\n" + "\n".join(f"- {n}" for n in sorted(meaningful))
        doc = Document(
            doc_id=f"skills_{aid_prefix}",
            doc_type=DocType.CHARACTER_STORY,
            title=f"{char_name}·技能名典故",
            body=body,
            narrative_layer=NarrativeLayer.L1_CONFIRMED,
            metadata={
                "source_type":    "skill_names",
                "character_name": char_name,
                "skill_count":    len(meaningful),
                "chapter_anchor": "unknown",
                "narrative_layer": NarrativeLayer.L1_CONFIRMED.value,
                "reliability":    "confirmed",
                "note": "技能名含大量古典汉语典故，是角色文化背景和设计意图的直接体现",
            },
        )
        docs.append(doc)
    logger.info("技能名典故: %d 个角色", len(docs))
    return docs


# ─────────────────────────────────────────────────────────────────────────────
# 主函数：提取所有扩展 lore，保存到 output/lore/
# ─────────────────────────────────────────────────────────────────────────────

EXTRACTOR_MAP: dict[str, tuple[Callable, str]] = {
    "rogue_miracles":    (extract_rogue_miracles,     "lore/rogue_miracles.jsonl"),
    "loading_descs":     (extract_loading_descs,       "lore/loading_descs.jsonl"),
    "eidolons":          (extract_eidolons,             "lore/eidolons.jsonl"),
    "voice_atlas":       (extract_voice_atlas,          "lore/voice_atlas.jsonl"),
    "aeon_stories":      (extract_aeon_stories,         "lore/aeon_stories.jsonl"),
    "skill_names":       (extract_skill_cultural_names, "lore/skill_names.jsonl"),
}


def extract_all_extended_lore(
    data_root: str | Path = "/workspace",
    resolver: TextMapResolver | None = None,
    sources: list[str] | None = None,   # None = all
) -> dict[str, list[Document]]:
    if resolver is None:
        resolver = TextMapResolver(data_root)
    sources = sources or list(EXTRACTOR_MAP.keys())

    results: dict[str, list[Document]] = {}
    for name in sources:
        if name not in EXTRACTOR_MAP:
            logger.warning("未知来源: %s", name)
            continue
        fn, out_path = EXTRACTOR_MAP[name]
        docs = fn(resolver)
        results[name] = docs

        # 保存到 JSONL
        full_path = _OUTPUT / out_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            for doc in docs:
                record = {
                    "doc_id":    doc.doc_id,
                    "doc_type":  doc.doc_type.value,
                    "title":     doc.title,
                    "body":      doc.body,
                    "dialogues": [],
                    "metadata":  doc.metadata,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info("✓ %s → %s (%d 条)", name, full_path, len(docs))

    return results


if __name__ == "__main__":
    import logging as _logging
    _logging.basicConfig(level=_logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    extract_all_extended_lore()
