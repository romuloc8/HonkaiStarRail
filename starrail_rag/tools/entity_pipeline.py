"""
统一实体生成管线。

替代原来分散的三个脚本（domain_lexicon.py / entity_extractor.py / alias_filter.py），
一次完成：种子提取 → DeepSeek 丰富 → 别称过滤 → 输出 entities.json

流程：
  Phase 1  从游戏结构化数据提取种子实体（角色、星神、命途）
  Phase 2  用 DeepSeek 处理 lore 文本，提取实体描述 + 别称 + 带时间锚点的关系
  Phase 3  合并种子与 DeepSeek 结果，去重，填充属性
  Phase 4  别称过滤（全局唯一 vs 上下文相关）
  Phase 5  输出 output/entities.json

运行：
    python -m starrail_rag.tools.entity_pipeline [--resume] [--phases 1,2,3,4,5]

环境变量：
    HSR_DEEPSEEK_API_KEY
"""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

from starrail_rag.tools.temporal_anchors import ANCHOR_BY_ID, ANCHOR_PROMPT_HINT, TEMPORAL_ANCHORS

logger = logging.getLogger(__name__)

DATA_ROOT = Path("/workspace")
OUTPUT_DIR = DATA_ROOT / "output"
ENTITIES_PATH = OUTPUT_DIR / "entities.json"
RAW_EXTRACTIONS_PATH = OUTPUT_DIR / "entity_pipeline_raw.jsonl"

# -----------------------------------------------------------------------
# 实体 Schema
# -----------------------------------------------------------------------

def empty_entity(canonical: str, entity_type: str) -> dict:
    return {
        "canonical": canonical,
        "type": entity_type,
        "description": "",
        "attributes": {},
        "aliases": [],
        "context_aliases": [],      # [{"text": str, "context": str}]
        "known_relations": [],      # [{"target", "relation", "temporal", "note"}]
        "source_hint": "",
        "mention_count": 0,
        "disambiguation_note": "",  # 只在同名多实体时填写
    }


def empty_relation(target: str, relation: str,
                   anchor: str = "unknown", position: str = "during",
                   note: str = "") -> dict:
    return {
        "target": target,
        "relation": relation,
        "temporal": {
            "anchor": anchor,
            "position": position,       # before | during | after | spanning
        },
        "note": note,
    }

# -----------------------------------------------------------------------
# Phase 1: 种子实体（游戏结构化数据）
# -----------------------------------------------------------------------

_BASE_TYPE_ZH = {
    "Knight": "存护", "Rogue": "巡猎", "Mage": "智识",
    "Shaman": "同谐", "Warlock": "虚无", "Warrior": "毁灭",
    "Priest": "丰饶", "Memory": "记忆", "Elation": "欢愉",
}
_DAMAGE_TYPE_ZH = {
    "Fire": "火", "Ice": "冰", "Thunder": "雷",
    "Wind": "风", "Quantum": "量子", "Imaginary": "虚数", "Physical": "物理",
}
_RARITY_ZH = {
    "CombatPowerAvatarRarityType4": "4星",
    "CombatPowerAvatarRarityType5": "5星",
}
_ICON_TO_PATH_EN = {
    "Knight": "Knight", "Memory": "Memory", "Warrior": "Warrior",
    "Rogue": "Rogue", "Mage": "Mage", "Shaman": "Shaman",
    "Warlock": "Warlock", "Priest": "Priest", "Elation": "Elation",
}


def _resolve(hash_val: int | None, textmap: dict) -> str:
    if not hash_val:
        return ""
    key = str(hash_val)
    if key in textmap:
        return textmap[key]
    signed = ctypes.c_int64(hash_val).value
    return textmap.get(str(signed), "")


def _resolve_field(field: Any, textmap: dict) -> str:
    if isinstance(field, dict):
        return _resolve(field.get("Hash"), textmap)
    return ""


def extract_seeds(data_root: Path) -> dict[str, dict]:
    """
    从游戏 JSON 提取种子实体，返回 canonical → entity dict。
    """
    with open(data_root / "TextMap" / "TextMapCHS.json", encoding="utf-8") as f:
        textmap = json.load(f)

    seeds: dict[str, dict] = {}

    # ── 命途 ──────────────────────────────────────────────────────────
    with open(data_root / "ExcelOutput" / "AvatarBaseType.json", encoding="utf-8") as f:
        base_types = json.load(f)

    path_en_to_zh: dict[str, str] = {}
    for bt in base_types:
        path_en = bt.get("ID", "")
        path_zh = _resolve_field(bt.get("BaseTypeText"), textmap)
        if not path_zh or path_zh == "通用":
            continue
        path_en_to_zh[path_en] = path_zh
        e = empty_entity(path_zh, "path")
        e["attributes"]["path_en"] = path_en
        e["source_hint"] = "AvatarBaseType.json"
        e["mention_count"] = 1
        seeds[path_zh] = e

    # ── 星神 ──────────────────────────────────────────────────────────
    with open(data_root / "ExcelOutput" / "RogueAeonDisplay.json", encoding="utf-8") as f:
        aeon_display = json.load(f)

    for ad in aeon_display:
        aeon_name = _resolve_field(ad.get("RogueAeonName"), textmap)
        path_name2 = _resolve_field(ad.get("RogueAeonPathName2"), textmap)
        if not aeon_name:
            continue
        icon_path = ad.get("AeonIcon", "")
        path_en = next((k for k in _ICON_TO_PATH_EN if k in icon_path), "")
        path_zh = path_en_to_zh.get(path_en, "") or path_name2

        canonical = f"{aeon_name}（{path_zh}星神）" if path_zh else aeon_name
        e = empty_entity(canonical, "aeon")
        e["attributes"]["aeon_name"] = aeon_name
        e["attributes"]["path"] = path_zh
        e["source_hint"] = "RogueAeonDisplay.json"
        e["mention_count"] = 1
        seeds[canonical] = e

    # ── 可玩角色 ──────────────────────────────────────────────────────
    with open(data_root / "ExcelOutput" / "AvatarConfig.json", encoding="utf-8") as f:
        avatars = json.load(f)

    for av in avatars:
        if not av.get("Release"):
            continue
        name = _resolve_field(av.get("AvatarName"), textmap)
        full_name = _resolve_field(av.get("AvatarFullName"), textmap)
        if not name:
            continue
        e = empty_entity(name, "character")
        e["attributes"] = {
            "avatar_id": av["AvatarID"],
            "path": _BASE_TYPE_ZH.get(av.get("AvatarBaseType", ""), ""),
            "element": _DAMAGE_TYPE_ZH.get(av.get("DamageType", ""), ""),
            "rarity": _RARITY_ZH.get(av.get("Rarity", ""), ""),
        }
        if full_name and full_name != name:
            e["aliases"].append(full_name)
        e["source_hint"] = "AvatarConfig.json"
        e["mention_count"] = 1
        seeds[name] = e

    logger.info("Phase 1: %d seed entities extracted", len(seeds))
    return seeds

# -----------------------------------------------------------------------
# Phase 2: DeepSeek 文本丰富
# -----------------------------------------------------------------------

SYSTEM_PROMPT = f"""你是崩坏：星穹铁道世界观的专业分析师，负责构建知识图谱。

你的任务是从游戏文本中提取实体，并为每个实体生成：
1. description（简短客观描述，说明该实体是什么，20-50字）
2. aliases（全局唯一别称，任何地方出现都指向此实体）
3. relations（与其他实体的关系，需标注时间锚点）

实体类型：
  character | aeon | path | faction | location | event | concept

时间锚点（relations 中必须使用下列 id 之一）：
{ANCHOR_PROMPT_HINT}

关系的 position 取值：
  before   — 发生在该锚点之前
  during   — 发生在该锚点期间
  after    — 发生在该锚点之后
  spanning — 跨越该锚点，或持续整个纪元

注意：
- aliases 只包含在文本中明确出现的独特称谓（不要泛化词如「少年」「她」「将军」）
- relations 只包含文本中有明确依据的关系（不要推测）
- 不同实体之间若有关系，两方都要列出（互相引用）
"""

USER_PROMPT_TEMPLATE = """请从以下【{count}段】崩坏：星穹铁道文本中提取实体信息。

{texts}

---
输出 JSON 数组，每个实体格式：
{{
  "canonical": "规范名称",
  "type": "类型",
  "description": "20-50字描述",
  "aliases": ["唯一别称1", "唯一别称2"],
  "relations": [
    {{
      "target": "目标实体canonical名",
      "relation": "关系动词（英文，如 member_of / leads / located_in）",
      "temporal_anchor": "锚点id",
      "temporal_position": "before|during|after|spanning",
      "note": "中文补充说明（可空）"
    }}
  ]
}}

JSON 数组："""

BATCH_TARGET_TOKENS = 1200
BATCH_MAX_DOCS = 6
REQUEST_DELAY = 1.0
MAX_OUTPUT_TOKENS = 2000


def _estimate_tokens(text: str) -> int:
    chinese = len(re.findall(r'[\u4e00-\u9fff]', text))
    return int(chinese / 1.5 + (len(text) - chinese) / 4)


def _doc_to_text(doc: dict) -> str:
    title = doc.get("title", "")
    body = doc.get("body", "")
    dialogues = doc.get("dialogues", [])
    parts = []
    if title:
        parts.append(f"【{title}】")
    if body:
        parts.append(body[:1500])
    elif dialogues:
        lines = [f"{d['speaker']}：{d['text']}" for d in dialogues[:20] if d.get("text")]
        parts.append("\n".join(lines))
    return "\n".join(parts).strip()


def _build_batches(docs: list[dict]) -> list[list[dict]]:
    batches, current, tokens = [], [], 0
    for doc in docs:
        text = _doc_to_text(doc)
        t = _estimate_tokens(text)
        if not text:
            continue
        if current and (tokens + t > BATCH_TARGET_TOKENS or len(current) >= BATCH_MAX_DOCS):
            batches.append(current)
            current, tokens = [], 0
        current.append(doc)
        tokens += t
    if current:
        batches.append(current)
    return batches


def _call_deepseek(client: OpenAI, batch: list[dict], model: str = "deepseek-chat") -> list[dict]:
    texts = []
    for i, doc in enumerate(batch, 1):
        text = _doc_to_text(doc)
        if text:
            texts.append(f"[段落{i}·{doc.get('doc_type', '')}·{doc.get('title', '')}]\n{text}")
    if not texts:
        return []

    prompt = USER_PROMPT_TEMPLATE.format(count=len(texts), texts="\n\n".join(texts))

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=MAX_OUTPUT_TOKENS,
                temperature=0.1,
            )
            content = resp.choices[0].message.content or ""
            start, end = content.find("["), content.rfind("]") + 1
            if start == -1 or end == 0:
                return []
            return json.loads(content[start:end])
        except Exception as exc:  # noqa: BLE001
            wait = 2 ** attempt
            logger.debug("API error (attempt %d): %s, retry in %ds", attempt + 1, exc, wait)
            time.sleep(wait)
    return []


def run_deepseek_extraction(
    doc_paths: list[Path],
    model: str = "deepseek-chat",
    resume: bool = True,
) -> list[dict]:
    """批量处理文档，返回原始提取结果列表。"""
    api_key = os.environ.get("HSR_DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("HSR_DEEPSEEK_API_KEY 未设置")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    docs: list[dict] = []
    for path in doc_paths:
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    docs.append(json.loads(line))
    logger.info("Phase 2: %d documents loaded", len(docs))

    batches = _build_batches(docs)
    logger.info("Phase 2: %d batches to process", len(batches))

    already_done = 0
    all_raw: list[dict] = []

    if resume and RAW_EXTRACTIONS_PATH.exists():
        with open(RAW_EXTRACTIONS_PATH, encoding="utf-8") as f:
            for line in f:
                batch_result = json.loads(line.strip())
                all_raw.extend(batch_result.get("entities", []))
                already_done += 1
        logger.info("Resuming from batch %d/%d", already_done, len(batches))

    RAW_EXTRACTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW_EXTRACTIONS_PATH, "a", encoding="utf-8") as raw_f:
        for i, batch in enumerate(batches):
            if i < already_done:
                continue
            logger.info("Batch %d/%d (%d docs)...", i + 1, len(batches), len(batch))
            entities = _call_deepseek(client, batch, model=model)
            record = {"batch_idx": i, "doc_count": len(batch),
                      "entity_count": len(entities), "entities": entities}
            raw_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            raw_f.flush()
            all_raw.extend(entities)
            logger.info("  → %d entities", len(entities))
            time.sleep(REQUEST_DELAY)

    logger.info("Phase 2: %d raw entities extracted total", len(all_raw))
    return all_raw

# -----------------------------------------------------------------------
# Phase 3: 合并种子 + DeepSeek 结果
# -----------------------------------------------------------------------

def _normalize(name: str) -> str:
    return name.strip().lower()


def _validate_anchor(anchor_id: str) -> str:
    """若 anchor 不在已知列表中，回退到 unknown。"""
    return anchor_id if anchor_id in ANCHOR_BY_ID else "unknown"


def merge(seeds: dict[str, dict], raw_extractions: list[dict]) -> list[dict]:
    """
    合并种子实体和 DeepSeek 提取结果：
    - 种子实体提供结构化属性（命途/属性/稀有度）
    - DeepSeek 结果提供 description、aliases、relations
    - 按 canonical 名合并，种子字段不被覆盖（优先级：种子 > DeepSeek）
    """
    merged: dict[str, dict] = {}

    # 先放入种子
    for canonical, seed in seeds.items():
        merged[_normalize(canonical)] = dict(seed)

    # 合并 DeepSeek 提取
    for raw in raw_extractions:
        if not isinstance(raw, dict):
            continue
        canonical = str(raw.get("canonical", "")).strip()
        if not canonical:
            continue
        key = _normalize(canonical)

        if key not in merged:
            # 新发现的实体（不在种子里）
            e = empty_entity(canonical, raw.get("type", "concept"))
            merged[key] = e
        else:
            # 与种子合并：修正 canonical 大小写为种子版本
            canonical = merged[key]["canonical"]

        e = merged[key]
        e["mention_count"] += 1

        # description：优先保留非空的，DeepSeek 可以填充种子的空值
        if not e["description"] and raw.get("description"):
            e["description"] = raw["description"].strip()

        # source_hint：补充
        if not e["source_hint"] and raw.get("source_hint"):
            e["source_hint"] = raw["source_hint"].strip()

        # aliases：合并去重
        existing_aliases = set(e["aliases"])
        for alias in raw.get("aliases", []):
            alias = alias.strip()
            if alias and alias != canonical and alias not in existing_aliases:
                existing_aliases.add(alias)
                e["aliases"].append(alias)

        # relations：合并，校验 temporal anchor
        existing_relation_keys = {
            (r["target"], r["relation"]) for r in e["known_relations"]
        }
        for rel in raw.get("relations", []):
            if not isinstance(rel, dict):
                continue
            target = str(rel.get("target", "")).strip()
            relation = str(rel.get("relation", "")).strip()
            if not target or not relation:
                continue
            if (target, relation) in existing_relation_keys:
                continue
            anchor = _validate_anchor(rel.get("temporal_anchor", "unknown"))
            position = rel.get("temporal_position", "during")
            if position not in ("before", "during", "after", "spanning"):
                position = "during"
            e["known_relations"].append(empty_relation(
                target=target,
                relation=relation,
                anchor=anchor,
                position=position,
                note=str(rel.get("note", "")).strip(),
            ))
            existing_relation_keys.add((target, relation))

    result = sorted(merged.values(), key=lambda x: -x["mention_count"])
    logger.info("Phase 3: %d merged entities", len(result))
    return result

# -----------------------------------------------------------------------
# Phase 4: 别称过滤
# -----------------------------------------------------------------------

PRONOUNS = frozenset([
    "他", "她", "祂", "它", "你", "我", "吾",
    "他们", "她们", "它们", "你们", "我们",
    "那人", "那位", "此人", "这人", "那他", "那她",
])
GENERIC_NOUNS = frozenset([
    "少年", "少女", "女孩", "男孩", "小孩", "孩子",
    "女人", "男人", "老人", "老者", "长者",
    "女子", "男子", "小姑娘", "小女孩", "小男孩", "小伙子",
    "年轻人", "年轻女子", "年轻男子", "青年",
    "学者", "商人", "旅人", "旅者", "战士", "武者", "剑士",
    "骑士", "信使", "诗人", "医者", "医师", "猎人",
    "外来者", "外来客", "异乡人", "访客", "主角",
    "父亲", "母亲", "儿子", "女儿", "兄弟", "姐妹",
    "哥哥", "弟弟", "姐姐", "妹妹", "丈夫", "妻子",
    "朋友", "同伴", "伙伴", "搭档", "导师", "弟子",
    "将军", "大人", "大人物", "统领", "首领", "领袖",
    "船长", "队长", "先生", "女士", "小姐", "夫人",
    "大哥", "大姐", "老大", "老师", "教授", "博士",
    "守卫", "卫士", "护卫", "侍卫", "判官",
])
RELIABLE_PATTERNS = [
    re.compile(r'.{2,}将军$'),
    re.compile(r'.{2,}大人$'),
    re.compile(r'.{2,}统领$'),
    re.compile(r'#\d+'),
    re.compile(r'^AR-\d+'),
    re.compile(r'[•·]'),
    re.compile(r'「.+」'),
]


def _classify_alias(alias: str, canonical: str) -> str:
    alias = alias.strip()
    if not alias or alias == canonical:
        return "drop"
    if alias in PRONOUNS:
        return "drop"
    if alias in GENERIC_NOUNS:
        return "context"
    for pat in RELIABLE_PATTERNS:
        if pat.search(alias):
            return "keep"
    if re.fullmatch(r'[\u4e00-\u9fff]{1,2}', alias):
        return "context"
    return "keep"


def filter_aliases(entities: list[dict]) -> list[dict]:
    stats = {"kept": 0, "moved": 0, "dropped": 0}
    for e in entities:
        new_aliases, new_ctx = [], list(e.get("context_aliases", []))
        for alias in e.get("aliases", []):
            d = _classify_alias(alias, e["canonical"])
            if d == "keep":
                new_aliases.append(alias)
                stats["kept"] += 1
            elif d == "context":
                if not any(a["text"] == alias for a in new_ctx):
                    new_ctx.append({"text": alias, "context": e.get("source_hint", "")})
                stats["moved"] += 1
            else:
                stats["dropped"] += 1
        e["aliases"] = new_aliases
        e["context_aliases"] = new_ctx
    logger.info(
        "Phase 4: aliases — kept=%d moved_to_context=%d dropped=%d",
        stats["kept"], stats["moved"], stats["dropped"],
    )
    return entities

# -----------------------------------------------------------------------
# Phase 5: 序列化输出
# -----------------------------------------------------------------------

def save_entities(entities: list[dict], path: Path = ENTITIES_PATH) -> None:
    by_type: dict[str, int] = {}
    for e in entities:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1

    total_relations = sum(len(e["known_relations"]) for e in entities)
    with_description = sum(1 for e in entities if e["description"])

    output = {
        "version": "3.0",
        "description": "星穹铁道领域实体词表（统一管线生成）",
        "temporal_anchors": TEMPORAL_ANCHORS,
        "stats": {
            "total_entities": len(entities),
            "with_description": with_description,
            "total_relations": total_relations,
            "by_type": by_type,
        },
        "entities": entities,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info("Phase 5: entities saved to %s", path)

# -----------------------------------------------------------------------
# 主入口
# -----------------------------------------------------------------------

def run_pipeline(
    doc_paths: list[Path] | None = None,
    phases: set[int] | None = None,
    model: str = "deepseek-chat",
    resume: bool = True,
) -> list[dict]:
    if phases is None:
        phases = {1, 2, 3, 4, 5}

    seeds: dict[str, dict] = {}
    raw_extractions: list[dict] = []

    if 1 in phases:
        seeds = extract_seeds(DATA_ROOT)

    if 2 in phases:
        if doc_paths is None:
            doc_paths = [
                OUTPUT_DIR / "book.jsonl",
                OUTPUT_DIR / "relic_set.jsonl",
                OUTPUT_DIR / "character_story.jsonl",
                OUTPUT_DIR / "light_cone.jsonl",
                OUTPUT_DIR / "item_lore.jsonl",
            ]
        raw_extractions = run_deepseek_extraction(doc_paths, model=model, resume=resume)
    elif RAW_EXTRACTIONS_PATH.exists():
        # 从已有的原始结果加载（跳过 Phase 2）
        with open(RAW_EXTRACTIONS_PATH, encoding="utf-8") as f:
            for line in f:
                batch = json.loads(line.strip())
                raw_extractions.extend(batch.get("entities", []))

    entities: list[dict] = []
    if 3 in phases:
        entities = merge(seeds, raw_extractions)
    if 4 in phases:
        entities = filter_aliases(entities)
    if 5 in phases:
        save_entities(entities)

    return entities


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="统一实体生成管线")
    parser.add_argument("--phases", default="1,2,3,4,5",
                        help="执行哪些阶段，逗号分隔（默认 1,2,3,4,5）")
    parser.add_argument("--no-resume", action="store_true",
                        help="不从断点续传，重新开始 Phase 2")
    parser.add_argument("--model", default="deepseek-chat")
    args = parser.parse_args()

    phases = set(int(p) for p in args.phases.split(","))
    entities = run_pipeline(phases=phases, model=args.model, resume=not args.no_resume)

    print(f"\n✓ 实体生成完成：{len(entities)} 个实体")
    by_type: dict[str, int] = {}
    for e in entities:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
        relations_count = sum(len(e["known_relations"]) for e in entities if e["type"] == t)
        print(f"  {t:12s}: {n:4d} 实体  {relations_count:4d} 关系")
    print(f"\n输出: {ENTITIES_PATH}")
