"""
实体属性补全器 (Entity Attribute Enricher)

使用 DeepSeek API 对 entities.json 中各类型实体进行属性补全，
不重新处理原始文档，而是利用已有的 description + known_relations + 新增 lore 上下文。

处理顺序（按信息密度和依赖关系）：
  1. aeon      — 最重要，补全令使列表/第一因/状态（用 aeon_stories 作上下文）
  2. path      — 命途/星神解耦
  3. faction   — 阵营类型/主要星神/意识形态
  4. character — 种族/记忆状态/叙事重要性
  5. location  — 地点类型/宇宙层级/关联星神
  6. event     — 事件结构（因果链/参与者）
  7. concept   — 概念类型/世界归属/是否世界内虚构
  8. item      — 物品类型/来源

运行：
    python3 -m starrail_rag.tools.entity_attribute_enricher [--types aeon,path] [--resume]

输出：
    output/entities_v4.json
    output/entity_enrichment_log.jsonl  （每批记录，用于断点续跑）
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from collections import defaultdict
from pathlib import Path

from openai import OpenAI

logger = logging.getLogger(__name__)

DATA_ROOT     = Path("/workspace")
OUTPUT_DIR    = DATA_ROOT / "output"
ENTITIES_IN   = OUTPUT_DIR / "entities.json"
ENTITIES_OUT  = OUTPUT_DIR / "entities_v4.json"
ENRICHMENT_LOG = OUTPUT_DIR / "entity_enrichment_log.jsonl"


# ──────────────────────────────────────────────────────────────────────────────
# 上下文加载（为各类型的 DeepSeek 调用提供 lore 背景）
# ──────────────────────────────────────────────────────────────────────────────

def _load_context_docs(paths: list[str], max_chars: int = 8000) -> str:
    """加载多个 JSONL 文件中的 body 文本，拼接为 lore 上下文。"""
    parts = []
    total = 0
    for path_str in paths:
        path = Path(path_str)
        if not path.exists():
            continue
        for line in open(path, encoding="utf-8"):
            doc = json.loads(line)
            body = doc.get("body", "") or doc.get("title", "")
            if body and total + len(body) < max_chars:
                parts.append(body[:2000])
                total += len(body)
    return "\n\n---\n\n".join(parts)


def _entity_summary(e: dict) -> str:
    """为单个实体生成简洁摘要，供 DeepSeek 判断。"""
    lines = [f"【{e['canonical']}】（{e['type']}）"]
    if e.get("description"):
        lines.append(f"描述：{e['description']}")
    if e.get("aliases"):
        lines.append(f"别称：{', '.join(e['aliases'][:4])}")
    rels = e.get("known_relations", [])
    if rels:
        rel_strs = [
            f"{r.get('relation','')}→{r.get('target','')}"
            for r in rels[:6]
        ]
        lines.append(f"关系：{'; '.join(rel_strs)}")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# 各类型的 DeepSeek 补全 Prompt
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_BASE = """你是崩坏：星穹铁道世界观专家。
请基于已知实体信息（描述/别称/关系）和提供的 lore 上下文，准确填写缺失的属性字段。

重要规则：
- 只基于文本证据填写，不确定时填 null 或 unknown
- 不要推测没有依据的内容
- 严格按照提供的枚举值填写（不要发明新值）
- 输出纯 JSON，不要加任何解释"""


# ── Aeon ──────────────────────────────────────────────────────────────────────

AEON_PROMPT = """以下是天才俱乐部关于这些星神的研究笔记（高质量 lore 上下文）：

{lore_context}

---

以下是需要补全属性的星神实体列表：

{entities_block}

---

对每个星神，填写以下 JSON 字段：
{{
  "canonical": "星神规范名称（用于识别，不修改）",
  "status": "alive|deceased|missing|unknown",
  "primum_mobile": "祂无法违抗的根本驱动力，一句话（如：不停筑墙隔绝威胁）",
  "known_emanators": ["已知令使名称列表，无则为空数组"],
  "cosmic_role": "arbiter|sacrosanct|author_of_calamity|unknown",
  "philosophical_stance": "对宇宙/命途的核心哲学立场，20字以内",
  "antagonist_aeons": ["已知对立星神名称列表"],
  "mystery_level": "low|medium|high|unknown"
}}

输出 JSON 数组（每个元素对应一个星神）："""


# ── Path ──────────────────────────────────────────────────────────────────────

PATH_PROMPT = """以下是需要补全属性的命途（Path）实体列表：

{entities_block}

---

重要背景：命途是独立存在的宇宙法则，不属于星神；星神是命途的「当前执掌者」，星神陨落后命途仍然存在。

对每个命途，填写以下 JSON 字段：
{{
  "canonical": "命途规范名称（不修改）",
  "exists_independently": true,
  "current_patron_aeon": "当前执掌此命途的星神规范名称（已陨落则填 null）",
  "former_patron_aeons": ["曾执掌但已陨落的星神列表"],
  "core_concept": "这条命途代表的核心哲学概念，15字以内",
  "associated_behaviors": ["走上这条命途的行为表现，3-5个关键词"],
  "incompatible_paths": ["与此命途存在本质冲突的命途名称"]
}}

输出 JSON 数组："""


# ── Faction ────────────────────────────────────────────────────────────────────

FACTION_PROMPT = """以下是需要补全属性的阵营（Faction）实体列表：

{entities_block}

---

对每个阵营，填写以下 JSON 字段：
{{
  "canonical": "阵营规范名称（不修改）",
  "faction_type": "government|military|religion|corporation|research|criminal|travelers|cult|alliance|secret_society|other",
  "primary_aeon": "该阵营主要信奉/依托的星神规范名称（无则 null）",
  "scale": "cosmic|multi_planetary|planetary|regional|local",
  "alignment": "protagonist_ally|protagonist_antagonist|neutral|complex|neutral_opportunistic",
  "ideology_summary": "核心意识形态，20字以内",
  "active_regions": ["主要活跃的星球/区域列表，最多3个"]
}}

输出 JSON 数组："""


# ── Character ─────────────────────────────────────────────────────────────────

CHARACTER_PROMPT = """以下是需要补全属性的角色实体列表：

{entities_block}

---

对每个角色，填写以下 JSON 字段：
{{
  "canonical": "角色规范名称（不修改）",
  "species": "人类|长生种|持明族|机械生命|令使|骸星之人|幻造种|无名客|星神宿主|未知",
  "gender": "male|female|unknown|non_binary",
  "memory_state": "complete|partial|amnesiac|modified|unknown",
  "body_state": "standard|cybernetic|spectral|reincarnated|transformed|occupied|unknown",
  "home_world": "原籍星球/世界名称（不确定填 null）",
  "is_emanator": true|false,
  "emanator_of": "效忠的星神规范名称（非令使则 null）",
  "narrative_importance": "major|supporting|minor|background",
  "power_source": "path|genetic|training|technology|blessing|unknown"
}}

填写依据：
- species: 从描述/关系/别称判断种族/类别
- memory_state: 三月七=amnesiac，开拓者=partial，被记忆改写的角色=modified，其余一般=complete
- is_emanator: 是否是某星神的「令使」（享有星神直接授权的强大个体）

输出 JSON 数组："""


# ── Location ──────────────────────────────────────────────────────────────────

LOCATION_PROMPT = """以下是需要补全属性的地点（Location）实体列表：

{entities_block}

---

对每个地点，填写以下 JSON 字段：
{{
  "canonical": "地点规范名称（不修改）",
  "location_type": "planet|space_station|city|region|dimension|simulation|dream|void|other",
  "cosmological_layer": "material|simulated|dream|amphorean_scepter",
  "parent_location": "所属上级地点名称（如城市→星球，null表示顶级）",
  "controlled_by": "当前控制/管辖该地的阵营或角色（null表示不明）",
  "aeon_affiliated": "与该地点文化/历史关联最紧密的星神（null表示无）",
  "accessibility": "open|invitation_required|restricted|inaccessible|unknown",
  "lore_significance": "该地点的叙事重要性，20字以内"
}}

cosmological_layer 说明：
- material: 物质宇宙中的真实地点（绝大多数地点）
- simulated: 模拟宇宙内部的地点
- dream: 匹诺康尼忆质梦境内的地点（流梦礁、盛会之星内部等）
- amphorean_scepter: 帝皇权杖内部的翁法罗斯世界

输出 JSON 数组："""


# ── Event ─────────────────────────────────────────────────────────────────────

EVENT_PROMPT = """以下是需要补全属性的事件（Event）实体列表（含已知关系信息）：

{entities_block}

---

对每个事件，填写以下 JSON 字段：
{{
  "canonical": "事件规范名称（不修改）",
  "event_type": "war|disaster|political|personal|cosmic|social|discovery",
  "scale": "personal|regional|planetary|cosmic|world_changing",
  "temporal_span": "single_event|ongoing|recurring|cyclical",
  "initiator": ["发起者/主要原因（实体名称列表）"],
  "direct_causes": ["直接导致此事件的因素，1-3条"],
  "immediate_outcomes": ["此事件的直接后果，1-3条"],
  "long_term_consequences": ["深远影响，1-3条（无则空数组）"],
  "primary_location": "事件主要发生地（null表示不明）",
  "is_resolved": true|false|null
}}

输出 JSON 数组："""


# ── Concept ───────────────────────────────────────────────────────────────────

CONCEPT_PROMPT = """以下是需要补全属性的概念（Concept）实体列表：

{entities_block}

---

对每个概念，填写以下 JSON 字段：
{{
  "canonical": "概念规范名称（不修改）",
  "concept_type": "phenomenon|creature|item|ability|culture|currency|technology|cosmological|in_game_fiction|other",
  "world_of_origin": "该概念属于哪个星球/世界的文化或自然环境（null表示跨宇宙或不明）",
  "is_in_game_fiction": true|false,
  "associated_aeon_or_path": "与该概念关联最紧密的星神或命途（null表示无）",
  "danger_level": "none|low|moderate|high|catastrophic"
}}

concept_type 定义：
- phenomenon: 自然/宇宙现象、灾害（黑潮、裂界、寰宇蝗灾）
- creature: 生物、物种（岁阳、长生孽物、呜呜伯）
- item: 物品、工具、设备（星核、六相冰）
- ability: 技能、法术、能力（化龙妙法、言灵术）
- culture: 文化习俗、节日、游戏、食物（煦日节、帝垣琼玉牌）
- currency: 货币（冬城盾）
- technology: 技术、系统、工程（模拟宇宙技术、幸福手术）
- cosmological: 宇宙法则、哲学概念（命途、法则、虚空）
- in_game_fiction: 游戏世界观内的虚构作品（《钟表小子》、以太战线游戏）

is_in_game_fiction = true 的条件：该概念本身就是星铁世界观内的「虚构作品」，
  如动画片、书籍、游戏等。注意：描述虚构作品内容的不算，只有「作品本身」才算。

输出 JSON 数组："""


# ── Item ──────────────────────────────────────────────────────────────────────

ITEM_PROMPT = """以下是需要补全属性的物品（Item）实体列表：

{entities_block}

---

对每个物品，填写以下 JSON 字段：
{{
  "canonical": "物品规范名称（不修改）",
  "item_type": "weapon|relic|consumable|key_item|currency|device|unknown",
  "world_of_origin": "物品来源的星球/世界（null表示不明）",
  "associated_character": "与该物品关联最紧密的角色（null表示无）",
  "rarity": "common|rare|unique|legendary|unknown",
  "narrative_importance": "major|supporting|minor|background"
}}

输出 JSON 数组："""


PROMPTS: dict[str, str] = {
    "aeon":      AEON_PROMPT,
    "path":      PATH_PROMPT,
    "faction":   FACTION_PROMPT,
    "character": CHARACTER_PROMPT,
    "location":  LOCATION_PROMPT,
    "event":     EVENT_PROMPT,
    "concept":   CONCEPT_PROMPT,
    "item":      ITEM_PROMPT,
}

# 各类型的 lore 上下文文件
CONTEXT_FILES: dict[str, list[str]] = {
    "aeon":      ["output/lore/aeon_stories.jsonl", "output/lore/fandom_databank.jsonl"],
    "path":      ["output/lore/aeon_stories.jsonl", "output/lore/loading_descs.jsonl"],
    "faction":   ["output/lore/fandom_databank.jsonl", "output/lore/aeon_stories.jsonl"],
    "character": ["output/lore/voice_atlas.jsonl", "output/lore/loading_descs.jsonl"],
    "location":  ["output/lore/fandom_databank.jsonl"],
    "event":     ["output/lore/aeon_stories.jsonl"],
    "concept":   ["output/lore/rogue_miracles.jsonl", "output/lore/loading_descs.jsonl"],
    "item":      ["output/lore/rogue_miracles.jsonl"],
}

# 批次大小（每次 API 调用处理的实体数）
BATCH_SIZES: dict[str, int] = {
    "aeon":      5,    # 少量，每个有大量关系需要分析
    "path":      13,   # 全部 13 个一起
    "faction":   15,
    "character": 20,
    "location":  25,
    "event":     10,   # 需要因果分析，小批次
    "concept":   30,
    "item":      20,
}


# ──────────────────────────────────────────────────────────────────────────────
# DeepSeek 调用
# ──────────────────────────────────────────────────────────────────────────────

def _call_deepseek(
    client: OpenAI,
    entity_type: str,
    entities_batch: list[dict],
    lore_context: str,
    model: str = "deepseek-chat",
) -> list[dict] | None:
    """调用 DeepSeek 补全一批实体的属性，返回属性字典列表。"""
    prompt_template = PROMPTS[entity_type]
    entities_block = "\n\n".join(_entity_summary(e) for e in entities_batch)

    if "{lore_context}" in prompt_template:
        user_prompt = prompt_template.format(
            lore_context=lore_context[:6000],
            entities_block=entities_block,
        )
    else:
        user_prompt = prompt_template.format(entities_block=entities_block)

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_BASE},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens=4000,
                temperature=0.1,
            )
            content = resp.choices[0].message.content or ""
            # 提取 JSON 数组
            start = content.find("[")
            end   = content.rfind("]") + 1
            if start == -1 or end == 0:
                logger.warning("批次未返回 JSON 数组（attempt %d）", attempt + 1)
                if attempt == 2:
                    return None
                time.sleep(2 ** attempt)
                continue
            return json.loads(content[start:end])
        except Exception as exc:
            wait = 2 ** attempt
            logger.warning("API 错误（attempt %d）: %s，%ds 后重试", attempt + 1, exc, wait)
            time.sleep(wait)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# 属性合并：把 DeepSeek 返回的属性写入实体
# ──────────────────────────────────────────────────────────────────────────────

def _merge_attributes(entity: dict, new_attrs: dict) -> dict:
    """
    将 DeepSeek 返回的新属性合并进实体字典。
    - 已有非空值的字段：不覆盖（保留原始数据）
    - 新字段或原来为 null/空：写入
    """
    # 跳过用于识别的 canonical 字段
    skip = {"canonical", "type"}

    for key, value in new_attrs.items():
        if key in skip:
            continue
        if value is None or value == "":
            continue
        # 如果是列表，合并去重
        if isinstance(value, list):
            existing = entity.get(key, [])
            if not existing:
                entity[key] = value
            else:
                # 追加新项
                existing_set = set(str(v) for v in existing)
                merged = list(existing)
                for v in value:
                    if str(v) not in existing_set:
                        merged.append(v)
                        existing_set.add(str(v))
                entity[key] = merged
        elif isinstance(value, dict):
            existing = entity.get(key, {})
            if not existing:
                entity[key] = value
            else:
                for k, v in value.items():
                    if k not in existing or existing[k] is None:
                        existing[k] = v
                entity[key] = existing
        else:
            # 标量：只写入空值位置
            if key not in entity or entity[key] is None or entity[key] == "" or entity[key] == "unknown":
                entity[key] = value

    return entity


# ──────────────────────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────────────────────

def enrich_entities(
    entity_types: list[str] | None = None,
    resume: bool = True,
    model: str = "deepseek-chat",
) -> dict:
    api_key = os.environ.get("HSR_DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("HSR_DEEPSEEK_API_KEY 未设置")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # 加载实体
    data = json.load(open(ENTITIES_IN))
    entities_list = data["entities"]
    # 构建规范名称映射（含模糊匹配）
    entity_map = {e["canonical"]: i for i, e in enumerate(entities_list)}
    # 额外建一个「短名 → 索引」映射（处理 DeepSeek 返回简短名称的情况）
    short_name_map: dict[str, int] = {}
    for i, e in enumerate(entities_list):
        full = e["canonical"]
        # 去掉括号内容：「Ⅸ（虚无星神）」→「Ⅸ」
        import re as _re
        short = _re.sub(r'[（(][^）)]*[）)]', '', full).strip()
        if short and short not in entity_map:
            short_name_map[short] = i
        # 也收录别称
        for alias in e.get("aliases", []):
            if alias and alias not in entity_map and alias not in short_name_map:
                short_name_map[alias] = i
    logger.info("加载 %d 个实体", len(entities_list))

    # 确定处理顺序
    all_types = ["aeon", "path", "faction", "character", "location", "event", "concept", "item"]
    types_to_process = entity_types or all_types

    # 加载已有的补全日志（断点续跑）
    completed_batches: set[str] = set()
    if resume and ENRICHMENT_LOG.exists():
        with open(ENRICHMENT_LOG, encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                batch_key = record.get("batch_key", "")
                if record.get("status") == "ok" and batch_key:
                    completed_batches.add(batch_key)
                    # 重新应用已完成批次的结果（支持模糊匹配）
                    for attrs in record.get("results", []):
                        canonical = attrs.get("canonical")
                        if not canonical:
                            continue
                        idx = entity_map.get(canonical)
                        if idx is None:
                            import re as _re
                            short = _re.sub(r'[（(][^）)]*[）)]', '', canonical).strip()
                            idx = entity_map.get(short)
                        if idx is not None:
                            entities_list[idx] = _merge_attributes(entities_list[idx], attrs)
        logger.info("从日志恢复：%d 个已完成批次", len(completed_batches))

    # 统计
    total_batches = 0
    processed_batches = 0
    failed_batches = 0

    with open(ENRICHMENT_LOG, "a", encoding="utf-8") as log_f:
        for entity_type in types_to_process:
            # 过滤该类型实体
            type_entities = [e for e in entities_list if e["type"] == entity_type]
            if not type_entities:
                continue

            # 加载 lore 上下文
            ctx_paths = [str(DATA_ROOT / p) for p in CONTEXT_FILES.get(entity_type, [])]
            lore_context = _load_context_docs(ctx_paths)
            batch_size = BATCH_SIZES.get(entity_type, 20)

            logger.info(
                "处理 %s (%d 个, 批次大小=%d, 上下文=%d字)...",
                entity_type, len(type_entities), batch_size, len(lore_context),
            )

            for batch_start in range(0, len(type_entities), batch_size):
                batch = type_entities[batch_start:batch_start + batch_size]
                batch_key = f"{entity_type}_{batch_start}"
                total_batches += 1

                if batch_key in completed_batches:
                    logger.debug("  跳过已完成批次: %s", batch_key)
                    continue

                logger.info(
                    "  批次 %s (%d~%d / %d)...",
                    batch_key, batch_start + 1,
                    min(batch_start + batch_size, len(type_entities)),
                    len(type_entities),
                )

                results = _call_deepseek(client, entity_type, batch, lore_context, model)

                if results is None:
                    logger.warning("  批次 %s 失败", batch_key)
                    failed_batches += 1
                    log_f.write(json.dumps({
                        "batch_key": batch_key,
                        "entity_type": entity_type,
                        "status": "failed",
                        "results": [],
                    }, ensure_ascii=False) + "\n")
                    log_f.flush()
                    continue

                # 合并结果（支持模糊匹配）
                merged_count = 0
                for attrs in results:
                    canonical = attrs.get("canonical")
                    if not canonical:
                        continue
                    idx = entity_map.get(canonical)
                    if idx is None:
                        idx = short_name_map.get(canonical)
                    if idx is not None:
                        entities_list[idx] = _merge_attributes(entities_list[idx], attrs)
                        merged_count += 1
                    else:
                        logger.debug("    找不到实体: '%s'", canonical)

                log_f.write(json.dumps({
                    "batch_key":   batch_key,
                    "entity_type": entity_type,
                    "batch_size":  len(batch),
                    "status":      "ok",
                    "merged":      merged_count,
                    "results":     results,
                }, ensure_ascii=False) + "\n")
                log_f.flush()

                processed_batches += 1
                logger.info("    → %d/%d 实体已补全", merged_count, len(batch))
                time.sleep(1.0)

    # 统计并保存
    logger.info(
        "完成：%d 批次处理（%d 成功 / %d 失败 / %d 已跳过）",
        total_batches, processed_batches, failed_batches,
        total_batches - processed_batches - failed_batches,
    )

    # 计算属性覆盖率
    new_fields = ["species", "concept_type", "cosmological_layer", "primary_aeon",
                  "event_type", "primum_mobile", "known_emanators", "narrative_importance",
                  "faction_type", "location_type", "memory_state", "is_in_game_fiction"]
    field_counts = {f: sum(1 for e in entities_list if e.get(f)) for f in new_fields}
    logger.info("新属性覆盖率：")
    for field, count in sorted(field_counts.items(), key=lambda x: -x[1]):
        pct = count / len(entities_list) * 100
        logger.info("  %-30s: %4d (%5.1f%%)", field, count, pct)

    # 保存输出
    output = {
        "version":    "4.0",
        "description": "崩坏：星穹铁道领域实体词表（v4 — 属性补全版，使用 DeepSeek API）",
        "temporal_anchors": data.get("temporal_anchors", []),
        "stats": {
            "total_entities":    len(entities_list),
            "enrichment_fields": field_counts,
        },
        "entities": entities_list,
    }
    ENTITIES_OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(ENTITIES_OUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info("✓ 已保存到 %s", ENTITIES_OUT)
    return field_counts


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Entity attribute enrichment via DeepSeek")
    parser.add_argument(
        "--types", type=str, default=None,
        help="逗号分隔的实体类型列表，如 aeon,path,faction（默认全部）",
    )
    parser.add_argument("--no-resume", action="store_true", help="不使用断点续跑")
    parser.add_argument("--model", default="deepseek-chat")
    args = parser.parse_args()

    types = [t.strip() for t in args.types.split(",")] if args.types else None
    enrich_entities(
        entity_types=types,
        resume=not args.no_resume,
        model=args.model,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
