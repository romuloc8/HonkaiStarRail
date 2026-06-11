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

【游戏内已知实体属性（请直接使用，不要重复创建）】
{game_attributes}

【任务】
从游戏文本中提取命名实体，为每个实体生成完整的结构化信息。

【来源上下文（影响可信度判断）】
{source_context}

【时间锚点系统（三级，relations 中使用）】
{anchor_hint}

position: before | during | after | spanning

【可信度（reliability）枚举】
- confirmed          → 主线直接叙事，当前发生的可观察事实
- historical_record  → 世界内档案/史书，被接受为历史但经作者视角过滤
- character_account  → 角色第一人称叙述，主观且可能不完整
- legend             → 口耳相传的神话/传说，可能有夸大或失真
- speculation        → 说话者明确表示不确定（含"我认为"/"据说"/"可能"）
- in_character_fiction → 世界观内部虚构作品（《钟表小子》、遗器寓言故事）
- reconstructed      → 穷观阵/忆质/梦境/推演中的记忆重建内容（可信度极低）

【置信度（confidence）枚举】
- confirmed  → 文本明确陈述
- probable   → 有合理证据但未明确陈述
- speculative → 需要推断，不确定

【关键规则】
1. description 必须含时态词（现任/曾任/已故/前往等），不写静态快照
2. event_anchor = 事件实际发生的时间；source_anchor = 从哪段文本得知（两者可不同）
3. 含「我认为」「据说」「传说」「可能是」等词 → reliability=speculation/legend
4. 穷观阵/忆质/梦境/推演场景中的陈述 → reliability=reconstructed
5. 世界内书籍/档案中的陈述 → reliability=historical_record（注意作者立场）
6. 开拓者/玩家选项台词 → 不提取为关系，这些是玩家输入不是世界观事实
7. valid_until_mission 必填：当关系有明确结束时间（职位变更/死亡/离开/揭露）
8. 只提取文本中有明确依据的关系，不推测
9. 命途（Path）是独立存在的，不是星神的属性；星神是命途的当前执掌者
10. 识别同一实体的多重身份（转世/化身/伪装）时使用 identity_layers"""

USER_PROMPT_TEMPLATE = """请从以下【{count}段】崩坏：星穹铁道文本中提取实体信息。

{texts}

---
输出 JSON 数组，每个实体格式：
{{
  "canonical": "规范名称（最常用、最完整的名称）",
  "type": "character|aeon|path|faction|location|event|concept",
  "subtype": "emanator|long_life_species|trailblazer|aeon_vessel|null（角色细分）",
  "current_status": "alive|deceased|transformed|missing|incapacitated|unknown",
  "current_status_since_mission": null,
  "current_status_note": "（如有明确描述）可可利亚在「静静的星河」中身亡",
  "description": "20-60字描述，必须含时态（现任/曾任/已故）",
  "attributes": {{"path": "", "element": "", "rarity": ""}},
  "serves_path": null,
  "serves_aeon": null,
  "exists_independently": false,
  "deliberately_ambiguous": false,
  "aliases": ["全局唯一别称——任何上下文都指向此实体"],
  "context_aliases": [{{"text": "别称", "context": "只在此场景中适用的原因"}}],
  "identity_layers": [
    {{
      "identity": "丹枫",
      "relation_to_canonical": "past_self|alter_ego|incarnation|title|facade",
      "description": "前世/化身的说明",
      "valid_until_mission": null
    }}
  ],
  "known_relations": [
    {{
      "target": "目标实体规范名",
      "relation": "英文动词_下划线（如 holds_title / member_of / caused_event）",
      "temporal": {{
        "event_anchor": "事件实际发生的锚点id（ch01-ch23 或 arc_* 或 epoch_*）",
        "event_position": "before|during|after|spanning",
        "source_anchor": "从哪个章节文本得知此事（同当前文档锚点）",
        "valid_from": null,
        "valid_from_mission": null,
        "valid_from_name": null,
        "valid_until": null,
        "valid_until_mission": null,
        "valid_until_name": "结束时的任务名（如「静静的星河」）",
        "precision": "arc_level|chapter_level|mission_level|approximate|unknown",
        "raw_evidence": "原文中关于时间的表述，若无则留空",
        "duration": null,
        "simulation_context": null,
        "cycle_number": null
      }},
      "reliability": "confirmed|historical_record|character_account|legend|speculation|in_character_fiction|reconstructed",
      "confidence": "confirmed|probable|speculative",
      "perspective": "omniscient|agent|victim|observer",
      "visibility": "public|secret|unknown",
      "is_symmetric": false,
      "note": "说明（可空）"
    }}
  ]
}}

JSON 数组："""

BATCH_TARGET_TOKENS = 1200
BATCH_MAX_DOCS = 6
REQUEST_DELAY = 1.0
MAX_OUTPUT_TOKENS = 4000  # increased for richer schema


def _build_source_context(doc: dict) -> str:
    """从文档元数据生成来源上下文，注入 extraction prompt。"""
    meta = doc.get("metadata", {})
    category = meta.get("category", doc.get("doc_type", ""))
    chapter_name = meta.get("chapter_name", "")
    chapter_anchor = meta.get("chapter_anchor", "unknown")
    narrative_layer = meta.get("narrative_layer", "confirmed")

    # 可信度提示
    reliability_hints = {
        "开拓任务": "主线剧情，reliability 默认 confirmed；角色自述主观内容用 character_account",
        "终末任务": "主线剧情，reliability 默认 confirmed",
        "同行任务": "角色视角叙述，多为 character_account；穷观阵/梦境场景用 reconstructed",
        "开拓续闻": "多为 historical_record 或 character_account",
        "冒险任务": "character_account 为主",
        "活动任务": "character_account 为主",
        "character_story": "角色个人视角，character_account；角色自称不确定时用 speculation",
        "book":            "世界内历史文献，historical_record；神话传说部分用 legend",
        "relic_set":       "遗器描述常含寓言/隐喻，in_character_fiction 或 legend",
        "item_lore":       "historical_record",
        "light_cone":      "historical_record 或 character_account",
        "achievement":     "confirmed（成就描述是官方认可的事实）",
    }
    hint = reliability_hints.get(category, "confirmed（默认）")

    # 已知叙事修正
    corrections_note = ""
    corrections_path = Path("/workspace/output/known_corrections.json")
    if corrections_path.exists():
        try:
            corrections = json.load(open(corrections_path))
            for c in corrections.get("corrections", []):
                if chapter_anchor in c.get("affected_chapters", []):
                    corrections_note = (
                        f"\n⚠️ 已知叙事修正：{c['description']}（{c['corrected_by_mission_name']}揭示）"
                        f"——此章节部分内容可能不可靠，受影响内容请标注 reliability={c['reliability_override']}"
                    )
        except Exception:
            pass

    return (
        f"来源章节: {chapter_name or '未知'}（{chapter_anchor}）\n"
        f"内容类型: {category}\n"
        f"可信度基准: {hint}{corrections_note}\n"
        f"relations 中 source_anchor 填: {chapter_anchor}"
    )


def _build_anchor_hint() -> str:
    """构建注入 prompt 的锚点提示（简化版，避免过长）。"""
    from starrail_rag.tools.temporal_anchors import TEMPORAL_ANCHORS
    lines = []
    for a in sorted(TEMPORAL_ANCHORS, key=lambda x: x["order"]):
        if a["id"] == "unknown":
            continue
        level_mark = {1: "⚡", 2: "🌐", 3: "📖"}.get(a.get("level", 2), "")
        lines.append(f"  {a['id']:35s} {level_mark} {a['label']}")
    return "\n".join(lines)


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
    source_contexts = []
    for i, doc in enumerate(batch, 1):
        text = _doc_to_text(doc)
        if text:
            texts.append(f"[段落{i}·{doc.get('doc_type', '')}·{doc.get('title', '')}]\n{text}")
            source_contexts.append(_build_source_context(doc))
    if not texts:
        return []

    # Inject source context into the user message header
    ctx_summary = "\n---\n".join(set(source_contexts))  # deduplicate identical contexts
    anchor_hint = _build_anchor_hint()

    # Build the final system prompt with anchor hint
    full_system = system_prompt.format(
        source_context=ctx_summary,
        anchor_hint=anchor_hint,
    ) if "{source_context}" in system_prompt else system_prompt

    prompt = USER_PROMPT_TEMPLATE.format(count=len(texts), texts="\n\n".join(texts))

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": full_system},
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

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        game_attributes=game_attributes,
        source_context="{source_context}",   # filled per-batch in _call_deepseek
        anchor_hint="{anchor_hint}",          # filled per-batch in _call_deepseek
    )

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


from starrail_rag.tools.temporal_anchors import ANCHOR_BY_ID

def _validate_anchor(anchor_id: str) -> str:
    """验证时间锚点 ID，接受 epoch/arc/chapter 三级锚点。"""
    return anchor_id if anchor_id in ANCHOR_BY_ID else "unknown"


def deduplicate_entities(raw_entities: list[dict]) -> list[dict]:
    """
    合并同名实体，按 mention_count 排序。
    新 schema 字段全部正确初始化并合并。
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
                # 基础字段
                "canonical":    canonical,
                "type":         raw.get("type", "concept"),
                "subtype":      raw.get("subtype") or None,
                "description":  raw.get("description", "").strip(),
                "attributes":   raw.get("attributes") or {},
                # 实体状态
                "current_status":              raw.get("current_status", "unknown"),
                "current_status_since_mission": raw.get("current_status_since_mission"),
                "current_status_note":          raw.get("current_status_note", ""),
                # Path/Aeon 关系
                "serves_path":          raw.get("serves_path"),
                "serves_aeon":          raw.get("serves_aeon"),
                "exists_independently": raw.get("exists_independently", False),
                # 叙事元数据
                "deliberately_ambiguous": raw.get("deliberately_ambiguous", False),
                # 别称
                "aliases":         [],
                "context_aliases": [],
                # 多重身份
                "identity_layers": [],
                # 关系
                "known_relations": [],
                # 统计
                "source_hint":        raw.get("source_hint", "").strip(),
                "mention_count":      0,
                "disambiguation_note": "",
            }
            merged[key] = e
        else:
            e = merged[key]

        e["mention_count"] += 1

        # description（取第一个非空，优先含时态词的）
        if not e["description"] and raw.get("description"):
            e["description"] = raw["description"].strip()
        elif raw.get("description"):
            new_desc = raw["description"].strip()
            # 优先含时态词的描述
            temporal_words = ("现任", "曾任", "已故", "前往", "前任", "转世")
            if any(w in new_desc for w in temporal_words) and not any(w in e["description"] for w in temporal_words):
                e["description"] = new_desc

        # current_status（取最具体的）
        status_priority = {"deceased": 5, "transformed": 4, "missing": 3,
                           "incapacitated": 2, "alive": 1, "unknown": 0}
        cur_p = status_priority.get(e["current_status"], 0)
        new_p = status_priority.get(raw.get("current_status", "unknown"), 0)
        if new_p > cur_p:
            e["current_status"] = raw["current_status"]
            if raw.get("current_status_since_mission"):
                e["current_status_since_mission"] = raw["current_status_since_mission"]
            if raw.get("current_status_note"):
                e["current_status_note"] = raw["current_status_note"]

        # subtype（取第一个非空）
        if not e["subtype"] and raw.get("subtype"):
            e["subtype"] = raw["subtype"]

        # serves_path / serves_aeon（取第一个非空）
        if not e["serves_path"] and raw.get("serves_path"):
            e["serves_path"] = raw["serves_path"]
        if not e["serves_aeon"] and raw.get("serves_aeon"):
            e["serves_aeon"] = raw["serves_aeon"]

        # deliberately_ambiguous（取 OR）
        if raw.get("deliberately_ambiguous"):
            e["deliberately_ambiguous"] = True

        # attributes（填空字段）
        for attr_key, attr_val in (raw.get("attributes") or {}).items():
            if attr_val and not e["attributes"].get(attr_key):
                e["attributes"][attr_key] = attr_val

        # aliases 去重合并
        existing_aliases = set(_normalize(a) for a in e["aliases"])
        for alias in (raw.get("aliases") or []):
            if isinstance(alias, str) and alias.strip():
                if _normalize(alias) not in existing_aliases and _normalize(alias) != _normalize(canonical):
                    e["aliases"].append(alias.strip())
                    existing_aliases.add(_normalize(alias))

        # context_aliases 去重合并
        existing_ctx = set(
            (_normalize(ca.get("text", "")), ca.get("context", ""))
            for ca in e["context_aliases"]
        )
        for ca in (raw.get("context_aliases") or []):
            if isinstance(ca, dict) and ca.get("text"):
                k = (_normalize(ca["text"]), ca.get("context", ""))
                if k not in existing_ctx:
                    e["context_aliases"].append(ca)
                    existing_ctx.add(k)

        # identity_layers 合并（按 identity 去重）
        existing_identities = {il.get("identity", "") for il in e["identity_layers"]}
        for il in (raw.get("identity_layers") or []):
            if isinstance(il, dict) and il.get("identity") not in existing_identities:
                e["identity_layers"].append(il)
                existing_identities.add(il.get("identity", ""))

        # known_relations — 合并（按 target+relation 去重，保留更完整的 temporal）
        existing_rels = {
            (_normalize(r.get("target", "")), r.get("relation", "")): i
            for i, r in enumerate(e["known_relations"])
        }
        for rel in (raw.get("known_relations") or raw.get("relations") or []):
            if not isinstance(rel, dict):
                continue
            target = rel.get("target", "").strip()
            relation = rel.get("relation", "").strip()
            if not target or not relation:
                continue

            # Normalize temporal (support both old and new schema)
            temporal = rel.get("temporal") or {}
            if not isinstance(temporal, dict):
                temporal = {}

            # Map old schema fields to new schema
            if "temporal_anchor" in rel and "event_anchor" not in temporal:
                temporal["event_anchor"] = _validate_anchor(rel["temporal_anchor"])
            if "temporal_position" in rel and "event_position" not in temporal:
                temporal["event_position"] = rel["temporal_position"]
            if "event_anchor" in temporal:
                temporal["event_anchor"] = _validate_anchor(temporal.get("event_anchor", "unknown"))
            if "source_anchor" in temporal:
                temporal["source_anchor"] = _validate_anchor(temporal.get("source_anchor", "unknown"))

            new_rel = {
                "target":        target,
                "relation":      relation,
                "temporal":      temporal,
                "reliability":   rel.get("reliability", "confirmed"),
                "confidence":    rel.get("confidence", "confirmed"),
                "perspective":   rel.get("perspective", "omniscient"),
                "visibility":    rel.get("visibility", "public"),
                "is_symmetric":  rel.get("is_symmetric", False),
                "note":          rel.get("note", ""),
            }

            rel_key = (_normalize(target), relation)
            if rel_key in existing_rels:
                # Merge: prefer more complete temporal info
                idx = existing_rels[rel_key]
                old_temporal = e["known_relations"][idx].get("temporal", {})
                # Keep whichever has more non-null fields
                if sum(1 for v in temporal.values() if v) > sum(1 for v in old_temporal.values() if v):
                    e["known_relations"][idx]["temporal"] = temporal
                if new_rel["note"] and not e["known_relations"][idx]["note"]:
                    e["known_relations"][idx]["note"] = new_rel["note"]
            else:
                e["known_relations"].append(new_rel)
                existing_rels[rel_key] = len(e["known_relations"]) - 1

    result = sorted(merged.values(), key=lambda x: -x["mention_count"])
    logger.info("Deduplicated to %d entities", len(result))
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
        "version": "4.0",
        "description": "崩坏：星穹铁道领域实体词表（优化管线 v4 — 完整时态/可信度/多重身份 schema）",
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
