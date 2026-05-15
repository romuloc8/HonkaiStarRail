"""
统一实体生成管线（优化版 v2）。

优化记录（见 WORKFLOW_OPTIMIZATION_LOG.md）：
  Phase 1 → 属性表上下文注入：不再生成种子实体，仅从 AvatarConfig 等提取
            path/element/rarity 属性表，作为 Phase 2 DeepSeek prompt 的背景知识
  Phase 2 → 一体化提取：description + attributes + 别称分类 + 关系，一次完成
            别称分类（全局唯一 vs 上下文相关）由 DeepSeek 直接判断，不再依赖启发式规则
  Phase 3 → 去除：无需合并种子与 DeepSeek 结果
  Phase 4 → 去除：别称过滤已并入 Phase 2 prompt schema

数据流：
  游戏属性表（AvatarConfig 等）→ 属性上下文
        ↓ 注入 system prompt
  lore 文本批次 → deepseek-chat → 实体列表（含 attributes / aliases / context_aliases / relations）
        ↓
  实体去重（全部名称 → deepseek-chat）
        ↓
  entities.json

运行：
    python -m starrail_rag.tools.entity_pipeline [--phases 1,2,3,4] [--resume]

环境变量：
    HSR_DEEPSEEK_API_KEY
    ALI_API_KEY（或 DASHSCOPE_API_KEY）
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
from typing import Callable

from openai import OpenAI

logger = logging.getLogger(__name__)

DATA_ROOT = Path("/workspace")
OUTPUT_DIR = DATA_ROOT / "output"
ENTITIES_PATH = OUTPUT_DIR / "entities.json"
RAW_EXTRACTIONS_PATH = OUTPUT_DIR / "entity_pipeline_raw.jsonl"

# ──────────────────────────────────────────────────────────────────────────────
# Phase 1：从游戏数据提取属性表（不生成实体，仅作为上下文）
# ──────────────────────────────────────────────────────────────────────────────

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


def _resolve(hash_val: int | None, textmap: dict) -> str:
    if not hash_val:
        return ""
    key = str(hash_val)
    if key in textmap:
        return textmap[key]
    signed = ctypes.c_int64(hash_val).value
    return textmap.get(str(signed), "")


def extract_game_attributes(data_root: Path = DATA_ROOT) -> str:
    """
    从游戏结构化数据提取角色/星神/命途的属性，
    返回可直接注入 prompt 的文本格式。

    格式：角色名: path=命途 element=属性 rarity=稀有度
    """
    with open(data_root / "TextMap" / "TextMapCHS.json", encoding="utf-8") as f:
        textmap = json.load(f)

    lines = []

    # 命途
    with open(data_root / "ExcelOutput" / "AvatarBaseType.json", encoding="utf-8") as f:
        base_types = json.load(f)
    path_en_to_zh: dict[str, str] = {}
    for bt in base_types:
        path_en = bt.get("ID", "")
        name_field = bt.get("BaseTypeText")
        path_zh = _resolve(name_field.get("Hash") if isinstance(name_field, dict) else 0, textmap)
        if path_zh and path_zh != "通用":
            path_en_to_zh[path_en] = path_zh

    # 可玩角色属性
    with open(data_root / "ExcelOutput" / "AvatarConfig.json", encoding="utf-8") as f:
        avatars = json.load(f)
    for av in avatars:
        if not av.get("Release"):
            continue
        name_field = av.get("AvatarName", {})
        name = _resolve(name_field.get("Hash") if isinstance(name_field, dict) else 0, textmap)
        if not name:
            continue
        path_en = av.get("AvatarBaseType", "")
        path_zh = path_en_to_zh.get(path_en, "")
        element = _DAMAGE_TYPE_ZH.get(av.get("DamageType", ""), "")
        rarity = _RARITY_ZH.get(av.get("Rarity", ""), "")
        parts = []
        if path_zh:
            parts.append(f"命途={path_zh}")
        if element:
            parts.append(f"属性={element}")
        if rarity:
            parts.append(f"稀有度={rarity}")
        if parts:
            lines.append(f"{name}: {' '.join(parts)}")

    # 星神
    with open(data_root / "ExcelOutput" / "RogueAeonDisplay.json", encoding="utf-8") as f:
        aeon_display = json.load(f)
    for ad in aeon_display:
        aeon_field = ad.get("RogueAeonName", {})
        aeon_name = _resolve(aeon_field.get("Hash") if isinstance(aeon_field, dict) else 0, textmap)
        path_field = ad.get("RogueAeonPathName2", {})
        path_zh = _resolve(path_field.get("Hash") if isinstance(path_field, dict) else 0, textmap)
        if aeon_name and path_zh:
            lines.append(f"{aeon_name}: 类型=星神 命途={path_zh}")

    logger.info("Game attributes extracted: %d entries", len(lines))
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Phase 2：DeepSeek 一体化提取
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = """你是崩坏：星穹铁道世界观的专业分析师，负责构建知识图谱。

【游戏内已知实体属性（请直接使用这些属性，不要重复创建）】
{game_attributes}

【任务】
从游戏文本中提取命名实体，为每个实体生成：
1. canonical（规范名称）
2. type：character | aeon | path | faction | location | event | concept
3. description：20-50字简洁描述
4. attributes：结合上方属性表填写 path/element/rarity（已知的直接填，未知留空）
5. aliases：【全局唯一别称】——任何上下文中出现都指向此实体（如「丹恒•腾荒」）
6. context_aliases：【上下文相关别称】——只在特定文本中才指向此实体
   格式：{{"text": "别称", "context": "适用场景"}}
   规则：代词（他/她/祂）、泛化词（少年/将军/医生）均为 context_aliases
7. relations：与其他实体的关系，需标注时间锚点

【时间锚点 ID（relations 中必须使用）】
epoch_titan, epoch_xianzhou_founding, event_jimu, event_buliren,
event_yinyue, event_belo_isolation, era_kakavasha,
arc_main_110, arc_main_belobog, arc_main_luofu, arc_main_penacony,
arc_main_amphoreus, arc_main_paradise, arc_post_main, unknown

position: before | during | after | spanning

【注意】relations 只包含文本中有明确依据的关系，不要推测。"""

USER_PROMPT_TEMPLATE = """请从以下【{count}段】崩坏：星穹铁道文本中提取实体信息。

{texts}

---
输出 JSON 数组，每个实体格式：
{{
  "canonical": "规范名称",
  "type": "类型",
  "description": "20-50字描述",
  "attributes": {{"path": "", "element": "", "rarity": ""}},
  "aliases": ["全局唯一别称"],
  "context_aliases": [{{"text": "别称", "context": "适用场景"}}],
  "relations": [
    {{
      "target": "目标实体",
      "relation": "英文动词",
      "temporal_anchor": "锚点id",
      "temporal_position": "before|during|after|spanning",
      "note": "说明（可空）"
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


def _call_deepseek(
    client: OpenAI,
    batch: list[dict],
    system_prompt: str,
    model: str = "deepseek-chat",
) -> list[dict]:
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
                    {"role": "system", "content": system_prompt},
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
        except Exception as exc:
            wait = 2 ** attempt
            logger.debug("API error (attempt %d): %s, retry in %ds", attempt + 1, exc, wait)
            time.sleep(wait)
    return []


def run_deepseek_extraction(
    doc_paths: list[Path],
    game_attributes: str,
    model: str = "deepseek-chat",
    resume: bool = True,
) -> list[dict]:
    """Phase 2：对 lore 文档批量运行 DeepSeek 提取。"""
    api_key = os.environ.get("HSR_DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("HSR_DEEPSEEK_API_KEY 未设置")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(game_attributes=game_attributes)

    docs: list[dict] = []
    for path in doc_paths:
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    docs.append(json.loads(line))
    logger.info("Loaded %d documents", len(docs))

    batches = _build_batches(docs)
    logger.info("Built %d batches", len(batches))

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
            entities = _call_deepseek(client, batch, system_prompt, model=model)
            record = {
                "batch_idx": i,
                "doc_count": len(batch),
                "entity_count": len(entities),
                "entities": entities,
            }
            raw_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            raw_f.flush()
            all_raw.extend(entities)
            logger.info("  → %d entities", len(entities))
            time.sleep(REQUEST_DELAY)

    logger.info("Extraction done: %d raw entities", len(all_raw))
    return all_raw


# ──────────────────────────────────────────────────────────────────────────────
# Phase 3：合并去重（send all names to DeepSeek）
# ──────────────────────────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    return name.strip().lower()


def _validate_anchor(anchor_id: str) -> str:
    VALID_ANCHORS = {
        "epoch_titan", "epoch_xianzhou_founding", "event_jimu", "event_buliren",
        "event_yinyue", "event_belo_isolation", "era_kakavasha",
        "arc_main_110", "arc_main_belobog", "arc_main_luofu", "arc_main_penacony",
        "arc_main_amphoreus", "arc_main_paradise", "arc_post_main", "unknown",
    }
    return anchor_id if anchor_id in VALID_ANCHORS else "unknown"


def deduplicate_entities(raw_entities: list[dict]) -> list[dict]:
    """
    合并同名实体（canonical 名相同的合并 aliases / context_aliases / relations），
    按 mention_count 排序。
    """
    merged: dict[str, dict] = {}

    for raw in raw_entities:
        if not isinstance(raw, dict):
            continue
        canonical = str(raw.get("canonical", "")).strip()
        if not canonical:
            continue
        key = _normalize(canonical)

        if key not in merged:
            e = {
                "canonical": canonical,
                "type": raw.get("type", "concept"),
                "description": raw.get("description", "").strip(),
                "attributes": raw.get("attributes") or {},
                "aliases": [],
                "context_aliases": [],
                "known_relations": [],
                "source_hint": raw.get("source_hint", "").strip(),
                "mention_count": 0,
                "disambiguation_note": "",
            }
            merged[key] = e
        else:
            e = merged[key]

        e["mention_count"] += 1

        # description（取第一个非空）
        if not e["description"] and raw.get("description"):
            e["description"] = raw["description"].strip()

        # attributes（填空字段）
        for attr_key, attr_val in (raw.get("attributes") or {}).items():
            if attr_val and not e["attributes"].get(attr_key):
                e["attributes"][attr_key] = attr_val

        # aliases（全局唯一，去重）
        existing_aliases = set(e["aliases"])
        for alias in raw.get("aliases", []):
            alias = alias.strip()
            if alias and alias != canonical and alias not in existing_aliases:
                e["aliases"].append(alias)
                existing_aliases.add(alias)

        # context_aliases（去重）
        existing_ctx = {a["text"] for a in e["context_aliases"]}
        for ca in raw.get("context_aliases", []):
            if isinstance(ca, dict) and ca.get("text") not in existing_ctx:
                e["context_aliases"].append(ca)
                existing_ctx.add(ca["text"])

        # known_relations（去重）
        existing_rels = {(r["target"], r["relation"]) for r in e["known_relations"]}
        for rel in raw.get("relations", []):
            if not isinstance(rel, dict):
                continue
            target = str(rel.get("target", "")).strip()
            relation = str(rel.get("relation", "")).strip()
            if not target or not relation:
                continue
            if (target, relation) in existing_rels:
                continue
            anchor = _validate_anchor(rel.get("temporal_anchor", "unknown"))
            position = rel.get("temporal_position", "during")
            if position not in ("before", "during", "after", "spanning"):
                position = "during"
            e["known_relations"].append({
                "target": target,
                "relation": relation,
                "temporal": {"anchor": anchor, "position": position},
                "note": str(rel.get("note", "")).strip(),
            })
            existing_rels.add((target, relation))

    result = sorted(merged.values(), key=lambda x: -x["mention_count"])
    logger.info("Deduplicated: %d unique entities", len(result))
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Phase 4：序列化输出
# ──────────────────────────────────────────────────────────────────────────────

def save_entities(entities: list[dict], path: Path = ENTITIES_PATH) -> None:
    from starrail_rag.tools.temporal_anchors import TEMPORAL_ANCHORS

    by_type: dict[str, int] = {}
    for e in entities:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1

    total_relations = sum(len(e["known_relations"]) for e in entities)
    with_description = sum(1 for e in entities if e.get("description"))

    output = {
        "version": "3.1",
        "description": "崩坏：星穹铁道领域实体词表（优化管线 v2）",
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
    logger.info("Saved %d entities to %s", len(entities), path)


# ──────────────────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────────────────

def run_pipeline(
    doc_paths: list[Path] | None = None,
    phases: set[int] | None = None,
    model: str = "deepseek-chat",
    resume: bool = True,
) -> list[dict]:
    """
    运行实体生成管线。

    phases:
      1 = 提取游戏属性表（属性上下文）
      2 = DeepSeek 批量提取（需要 HSR_DEEPSEEK_API_KEY）
      3 = 合并去重
      4 = 序列化输出

    默认运行全部阶段。
    """
    if phases is None:
        phases = {1, 2, 3, 4}

    if doc_paths is None:
        doc_paths = [
            OUTPUT_DIR / "lore" / "books.jsonl",
            OUTPUT_DIR / "lore" / "relic_sets.jsonl",
            OUTPUT_DIR / "lore" / "character_stories.jsonl",
            OUTPUT_DIR / "lore" / "light_cones.jsonl",
            OUTPUT_DIR / "lore" / "item_lore.jsonl",
        ]

    # Phase 1：提取属性上下文
    game_attributes = ""
    if 1 in phases:
        logger.info("=== Phase 1: Extracting game attributes ===")
        game_attributes = extract_game_attributes(DATA_ROOT)

    # Phase 2：DeepSeek 提取
    raw_entities: list[dict] = []
    if 2 in phases:
        logger.info("=== Phase 2: DeepSeek extraction ===")
        raw_entities = run_deepseek_extraction(
            doc_paths, game_attributes, model=model, resume=resume
        )
    elif RAW_EXTRACTIONS_PATH.exists():
        with open(RAW_EXTRACTIONS_PATH, encoding="utf-8") as f:
            for line in f:
                raw_entities.extend(json.loads(line.strip()).get("entities", []))

    # Phase 3：合并去重
    entities: list[dict] = []
    if 3 in phases:
        logger.info("=== Phase 3: Deduplication ===")
        entities = deduplicate_entities(raw_entities)

    # Phase 4：输出
    if 4 in phases and entities:
        logger.info("=== Phase 4: Saving ===")
        save_entities(entities)

    return entities


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="实体生成管线（优化版 v2）")
    parser.add_argument("--phases", default="1,2,3,4")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--model", default="deepseek-chat")
    args = parser.parse_args()

    phases = set(int(p) for p in args.phases.split(","))
    entities = run_pipeline(phases=phases, model=args.model, resume=not args.no_resume)

    print(f"\n实体生成完成：{len(entities)} 个")
    by_type: dict[str, int] = {}
    for e in entities:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {n}")
