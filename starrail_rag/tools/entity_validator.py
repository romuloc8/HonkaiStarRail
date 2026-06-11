"""
实体数据验证器 (Entity Validator)

两阶段验证：
  Step 1 — 规则验证（0 API 成本）：schema 合规性 + 内部一致性
  Step 2 — DeepSeek 批判性审查：事实准确性 + 重大遗漏

运行：
    python3 -m starrail_rag.tools.entity_validator [--step 1|2|all] [--resume]

输出：
    output/validation_issues.json      — 所有发现的问题
    output/validation_report.md        — 可读报告
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

DATA_ROOT    = Path("/workspace")
OUTPUT_DIR   = DATA_ROOT / "output"
ENTITIES_IN  = OUTPUT_DIR / "entities_v4.json"
ISSUES_OUT   = OUTPUT_DIR / "validation_issues.json"
REPORT_OUT   = OUTPUT_DIR / "validation_report.md"
LOG_FILE     = OUTPUT_DIR / "validation_log.jsonl"


# ──────────────────────────────────────────────────────────────────────────────
# Step 1：规则验证
# ──────────────────────────────────────────────────────────────────────────────

# 合法枚举值
VALID_ENUMS = {
    "type": {"character", "aeon", "path", "faction", "location",
             "event", "item", "concept", "object"},
    "current_status": {"alive", "deceased", "transformed", "missing",
                       "incapacitated", "unknown", None},
    "species": {"人类", "长生种", "持明族", "机械生命", "令使", "骸星之人",
                "幻造种", "无名客", "星神宿主", "岁阳", "步离人",
                "未知", None},
    "memory_state": {"complete", "partial", "amnesiac", "modified", "unknown", None},
    "body_state": {"standard", "cybernetic", "spectral", "reincarnated",
                   "transformed", "occupied", "unknown", None},
    "narrative_importance": {"major", "supporting", "minor", "background",
                             "unknown", None},
    "cosmological_layer": {"material", "simulated", "dream",
                           "amphorean_scepter", "other", None},
    "location_type": {"planet", "space_station", "city", "region", "country",
                      "dimension", "simulation", "dream", "void", "other", None},
    "faction_type": {"government", "military", "religion", "corporation",
                     "research", "criminal", "travelers", "cult",
                     "alliance", "secret_society", "other", None},
    "alignment": {"protagonist_ally", "protagonist_antagonist", "neutral",
                  "complex", "neutral_opportunistic", None},
    "scale": {"personal", "regional", "local", "multi_planetary", "planetary",
              "cosmic", "world_changing", "unknown", None},
    "concept_type": {"phenomenon", "creature", "item", "ability", "culture",
                     "currency", "technology", "cosmological",
                     "in_game_fiction", "other", None},
    "cosmic_role": {"arbiter", "sacrosanct", "author_of_calamity", "unknown", None},
    "event_type": {"war", "disaster", "political", "personal", "cosmic",
                   "social", "discovery", None},
    "mystery_level": {"low", "medium", "high", "unknown", None},
    "danger_level": {"none", "low", "moderate", "high", "catastrophic", "unknown", None},
}


def step1_rule_validation(entities: list[dict]) -> list[dict]:
    """规则验证：schema 合规性 + 内部一致性检查。"""
    issues: list[dict] = []
    entity_index = {e["canonical"]: e for e in entities}

    # 构建令使反向索引
    emanators: dict[str, list[str]] = defaultdict(list)
    for e in entities:
        aeon = e.get("emanator_of")
        if e.get("is_emanator") and aeon:
            emanators[aeon].append(e["canonical"])

    for e in entities:
        canonical = e["canonical"]
        etype = e.get("type", "")

        # 1. 枚举值合规性
        for field, valid_set in VALID_ENUMS.items():
            val = e.get(field)
            if val is not None and valid_set and val not in valid_set:
                issues.append({
                    "entity":          canonical,
                    "entity_type":     etype,
                    "field":           field,
                    "current_value":   val,
                    "suggested_value": None,
                    "issue_type":      "invalid_enum",
                    "severity":        "error",
                    "evidence":        f"'{val}' 不在合法枚举集合 {sorted(v for v in valid_set if v)} 中",
                    "step":            1,
                    "verified":        False,
                    "apply_fix":       False,
                })

        # 2. 令使一致性：is_emanator=True 但 emanator_of 为空
        if e.get("is_emanator") and not e.get("emanator_of"):
            issues.append({
                "entity":       canonical,
                "entity_type":  etype,
                "field":        "emanator_of",
                "current_value": None,
                "suggested_value": None,
                "issue_type":   "missing_required_field",
                "severity":     "warning",
                "evidence":     "is_emanator=True 但 emanator_of 为空",
                "step":         1,
                "verified":     False,
                "apply_fix":    False,
            })

        # 3. Aeon 实体的 known_emanators 与 is_emanator 反向关系
        if etype == "aeon":
            declared_emanators = e.get("known_emanators", [])
            actual_emanators = emanators.get(canonical, [])
            missing = [x for x in actual_emanators if x not in declared_emanators]
            if missing:
                issues.append({
                    "entity":       canonical,
                    "entity_type":  etype,
                    "field":        "known_emanators",
                    "current_value": declared_emanators,
                    "suggested_value": declared_emanators + missing,
                    "issue_type":   "incomplete_emanator_list",
                    "severity":     "warning",
                    "evidence":     f"以下实体声明了 is_emanator=True/emanator_of={canonical}，但未在此 Aeon 的 known_emanators 中：{missing}",
                    "step":         1,
                    "verified":     True,   # 这是逻辑推断，可直接应用
                    "apply_fix":    True,
                })

        # 4. 概念实体 is_in_game_fiction=True 但 concept_type != 'in_game_fiction'
        if etype == "concept":
            if e.get("is_in_game_fiction") and e.get("concept_type") != "in_game_fiction":
                issues.append({
                    "entity":       canonical,
                    "entity_type":  etype,
                    "field":        "concept_type",
                    "current_value": e.get("concept_type"),
                    "suggested_value": "in_game_fiction",
                    "issue_type":   "inconsistent_fields",
                    "severity":     "warning",
                    "evidence":     "is_in_game_fiction=True 但 concept_type 不是 in_game_fiction",
                    "step":         1,
                    "verified":     True,
                    "apply_fix":    True,
                })

        # 5. 描述为空但有大量关系（重要实体描述缺失）
        if not e.get("description") and len(e.get("known_relations", [])) >= 5:
            issues.append({
                "entity":       canonical,
                "entity_type":  etype,
                "field":        "description",
                "current_value": "",
                "suggested_value": None,
                "issue_type":   "missing_description",
                "severity":     "info",
                "evidence":     f"有 {len(e.get('known_relations', []))} 条关系但 description 为空",
                "step":         1,
                "verified":     False,
                "apply_fix":    False,
            })

        # 6. Path 实体的 exists_independently 应为 True
        if etype == "path" and not e.get("exists_independently"):
            issues.append({
                "entity":       canonical,
                "entity_type":  etype,
                "field":        "exists_independently",
                "current_value": e.get("exists_independently"),
                "suggested_value": True,
                "issue_type":   "missing_required_field",
                "severity":     "warning",
                "evidence":     "命途（Path）独立于星神存在，exists_independently 应为 True",
                "step":         1,
                "verified":     True,
                "apply_fix":    True,
            })

    logger.info(
        "Step 1 规则验证完成：%d 个问题（%d error / %d warning / %d info）",
        len(issues),
        sum(1 for x in issues if x["severity"] == "error"),
        sum(1 for x in issues if x["severity"] == "warning"),
        sum(1 for x in issues if x["severity"] == "info"),
    )
    return issues


# ──────────────────────────────────────────────────────────────────────────────
# Step 2：DeepSeek 批判性审查
# ──────────────────────────────────────────────────────────────────────────────

VALIDATOR_SYSTEM = """你是崩坏：星穹铁道世界观的严格审查员。
你的任务是找出以下实体数据中的错误、不准确、重大遗漏或不一致。

重要原则：
1. 只报告你有高度把握的问题（置信度 >= 0.75）
2. 每条问题必须附上游戏文本依据（哪个故事/哪个设定）
3. 不要修改你不确定的内容——不确定时不报告
4. 关注：属性值是否错误、重要关系是否缺失、描述是否与实际设定矛盾

输出格式（JSON 数组）：
[
  {
    "entity": "实体规范名称",
    "field": "有问题的字段名",
    "current_value": "当前值",
    "suggested_value": "建议值（或 null 表示应删除）",
    "issue_type": "factual_error|incomplete|inconsistent|wrong_classification",
    "severity": "error|warning|info",
    "confidence": 0.0-1.0,
    "evidence": "依据（引用游戏文本或世界观设定）"
  }
]

如果这批实体数据都没有问题，返回空数组 []。"""


def _load_lore_context(entity_type: str) -> str:
    """为特定实体类型加载 lore 上下文。"""
    ctx_map = {
        "aeon":      ["output/lore/aeon_stories.jsonl"],
        "faction":   ["output/lore/fandom_databank.jsonl"],
        "character": ["output/lore/voice_atlas.jsonl"],
        "concept":   ["output/lore/rogue_miracles.jsonl"],
        "event":     ["output/lore/aeon_stories.jsonl"],
        "location":  ["output/lore/fandom_databank.jsonl"],
    }
    paths = ctx_map.get(entity_type, [])
    parts = []
    total = 0
    for path_str in paths:
        p = DATA_ROOT / path_str
        if not p.exists():
            continue
        for line in open(p, encoding="utf-8"):
            doc = json.loads(line)
            body = doc.get("body", "")[:1500]
            if body and total + len(body) < 6000:
                parts.append(body)
                total += len(body)
    return "\n\n---\n\n".join(parts)


def _entity_full_summary(e: dict) -> str:
    """生成包含所有字段的实体摘要，供验证使用。"""
    lines = [f"【{e['canonical']}】（{e['type']}）"]
    for field in ["description", "species", "current_status", "memory_state",
                  "body_state", "is_emanator", "emanator_of", "primum_mobile",
                  "cosmic_role", "known_emanators", "status",
                  "location_type", "cosmological_layer", "aeon_affiliated",
                  "faction_type", "primary_aeon", "alignment", "ideology_summary",
                  "event_type", "scale", "direct_causes", "immediate_outcomes", "is_resolved",
                  "concept_type", "is_in_game_fiction", "danger_level", "world_of_origin",
                  "narrative_importance"]:
        val = e.get(field)
        if val is not None and val != "" and val != [] and val != {}:
            lines.append(f"{field}: {val}")
    rels = e.get("known_relations", [])
    if rels:
        rel_strs = [f"{r.get('relation','')}→{r.get('target','')}" for r in rels[:5]]
        lines.append(f"主要关系: {'; '.join(rel_strs)}")
    return "\n".join(lines)


def _call_validator(
    client: OpenAI,
    entities_batch: list[dict],
    lore_context: str,
    entity_type: str,
    model: str = "deepseek-chat",
) -> list[dict]:
    """调用 DeepSeek 进行批判性审查，返回问题列表。"""
    entities_block = "\n\n".join(_entity_full_summary(e) for e in entities_batch)

    user_msg = f"【lore 参考上下文（供审查依据参考）】\n{lore_context[:4000]}\n\n" \
               f"---\n\n【待审查的实体数据（{entity_type} 类型）】\n\n{entities_block}\n\n" \
               f"请审查以上 {len(entities_batch)} 个实体数据，找出其中的错误或重大遗漏。"

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": VALIDATOR_SYSTEM},
                    {"role": "user",   "content": user_msg},
                ],
                max_tokens=3000,
                temperature=0.0,  # 最低温度，最大一致性
            )
            content = resp.choices[0].message.content or ""
            start = content.find("[")
            end   = content.rfind("]") + 1
            if start == -1 or end == 0:
                return []
            return json.loads(content[start:end])
        except Exception as exc:
            wait = 2 ** attempt
            logger.warning("验证 API 错误（attempt %d）: %s", attempt + 1, exc)
            time.sleep(wait)
    return []


def step2_deepseek_validation(
    entities: list[dict],
    resume: bool = True,
    model: str = "deepseek-chat",
) -> list[dict]:
    """DeepSeek 批判性审查，重点实体优先。"""
    api_key = os.environ.get("HSR_DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("HSR_DEEPSEEK_API_KEY 未设置")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    # 已完成的批次
    completed: set[str] = set()
    all_issues: list[dict] = []
    if resume and LOG_FILE.exists():
        with open(LOG_FILE, encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("step") == 2 and rec.get("status") == "ok":
                    completed.add(rec["batch_key"])
                    all_issues.extend(rec.get("issues", []))
        logger.info("恢复：已完成 %d 个验证批次", len(completed))

    # 验证批次定义
    def make_batches(filter_fn, key_prefix, batch_size):
        filtered = [e for e in entities if filter_fn(e)]
        return [
            (f"{key_prefix}_{i}", filtered[i:i+batch_size])
            for i in range(0, len(filtered), batch_size)
        ]

    validation_plan = [
        # (批次键前缀, 筛选函数, 批次大小, lore上下文类型)
        make_batches(lambda e: e["type"] == "aeon",  "v2_aeon",     5, ),
        make_batches(lambda e: e["type"] == "path",  "v2_path",     13),
        make_batches(
            lambda e: e["type"] == "character" and e.get("narrative_importance") == "major",
            "v2_char_major", 15
        ),
        make_batches(
            lambda e: e["type"] == "faction" and e.get("narrative_importance") in ("major", "supporting"),
            "v2_faction_major", 15
        ),
        make_batches(lambda e: e["type"] == "event",   "v2_event",    10),
        make_batches(
            lambda e: e["type"] == "concept" and e.get("is_in_game_fiction"),
            "v2_concept_fiction", 15
        ),
        make_batches(
            lambda e: e["type"] == "location" and e.get("narrative_importance") == "major",
            "v2_loc_major", 15
        ),
    ]

    # 拍平批次列表
    flat_batches: list[tuple[str, list[dict], str]] = []
    for group in validation_plan:
        if not group:
            continue
        # 推断 entity_type 和 lore_type
        if group:
            first_key = group[0][0]
            if "aeon" in first_key or "path" in first_key:
                lore_type = "aeon"
            elif "char" in first_key:
                lore_type = "character"
            elif "faction" in first_key:
                lore_type = "faction"
            elif "event" in first_key:
                lore_type = "event"
            elif "concept" in first_key:
                lore_type = "concept"
            else:
                lore_type = "location"
            lore_ctx = _load_lore_context(lore_type)
            for batch_key, batch in group:
                flat_batches.append((batch_key, batch, lore_ctx))

    total = len(flat_batches)
    logger.info("验证计划：%d 批次（含 major 角色/Aeon/事件/虚构概念等）", total)

    with open(LOG_FILE, "a", encoding="utf-8") as log_f:
        for i, (batch_key, batch, lore_ctx) in enumerate(flat_batches):
            if batch_key in completed:
                logger.debug("跳过已完成: %s", batch_key)
                continue

            entity_type = batch[0]["type"] if batch else "unknown"
            logger.info(
                "验证批次 %s (%d/%d, %s %d个)...",
                batch_key, i + 1, total, entity_type, len(batch)
            )

            issues = _call_validator(client, batch, lore_ctx, entity_type, model)
            # 标注来源
            for issue in issues:
                issue["step"] = 2
                issue["verified"] = False
                issue["apply_fix"] = False

            log_f.write(json.dumps({
                "batch_key":   batch_key,
                "entity_type": entity_type,
                "batch_size":  len(batch),
                "step":        2,
                "status":      "ok",
                "issues":      issues,
            }, ensure_ascii=False) + "\n")
            log_f.flush()

            all_issues.extend(issues)
            logger.info("    → %d 个问题", len(issues))
            time.sleep(1.0)

    logger.info("Step 2 完成：共发现 %d 个问题", len(all_issues))
    return all_issues


# ──────────────────────────────────────────────────────────────────────────────
# 报告生成
# ──────────────────────────────────────────────────────────────────────────────

def generate_report(all_issues: list[dict], entities: list[dict]) -> str:
    from collections import Counter

    by_severity = defaultdict(list)
    by_type     = defaultdict(list)
    by_field    = defaultdict(list)

    for issue in all_issues:
        by_severity[issue["severity"]].append(issue)
        by_type[issue.get("entity_type", "unknown")].append(issue)
        by_field[issue.get("field", "unknown")].append(issue)

    auto_fixable = [x for x in all_issues if x.get("apply_fix")]

    lines = [
        "# 实体验证报告",
        "",
        f"> 验证时间：{__import__('time').strftime('%Y-%m-%d %H:%M UTC')}",
        f"> 总实体数：{len(entities)}",
        f"> 发现问题：{len(all_issues)} 个",
        f"> 可自动修复：{len(auto_fixable)} 个",
        "",
        "---",
        "",
        "## 问题统计",
        "",
        "| 严重度 | 数量 | 说明 |",
        "|-------|------|------|",
        f"| ❌ error   | {len(by_severity.get('error',[]))} | 明确错误，需修正 |",
        f"| ⚠️ warning | {len(by_severity.get('warning',[]))} | 可能有问题，需人工确认 |",
        f"| ℹ️ info    | {len(by_severity.get('info',[]))} | 补充信息，供参考 |",
        "",
        "### 按实体类型分布",
        "",
        "| 类型 | 问题数 |",
        "|------|--------|",
    ]
    for etype, issues_list in sorted(by_type.items(), key=lambda x: -len(x[1])):
        lines.append(f"| {etype} | {len(issues_list)} |")

    lines += [
        "",
        "### 按字段分布（Top 10）",
        "",
        "| 字段 | 问题数 |",
        "|------|--------|",
    ]
    for field, issues_list in sorted(by_field.items(), key=lambda x: -len(x[1]))[:10]:
        lines.append(f"| {field} | {len(issues_list)} |")

    lines += [
        "",
        "---",
        "",
        "## ❌ Error 级问题（需要修正）",
        "",
    ]
    for issue in by_severity.get("error", [])[:50]:
        lines.append(f"### `{issue['entity']}` — {issue['field']}")
        lines.append(f"- 当前值: `{issue['current_value']}`")
        lines.append(f"- 建议值: `{issue['suggested_value']}`")
        lines.append(f"- 依据: {issue['evidence']}")
        if issue.get("confidence"):
            lines.append(f"- 置信度: {issue['confidence']:.0%}")
        lines.append("")

    lines += [
        "",
        "---",
        "",
        "## ⚠️ Warning 级问题（需人工确认）",
        "",
    ]
    for issue in by_severity.get("warning", [])[:30]:
        lines.append(f"- **{issue['entity']}** (`{issue['field']}`): {issue['evidence']}")

    lines += [
        "",
        "---",
        "",
        f"## ✅ 可自动修复的问题（{len(auto_fixable)} 个）",
        "",
        "以下问题由规则推断确认，可直接应用 patch：",
        "",
    ]
    for issue in auto_fixable:
        lines.append(
            f"- `{issue['entity']}`.{issue['field']}: "
            f"`{issue['current_value']}` → `{issue['suggested_value']}`"
        )

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Patch 应用
# ──────────────────────────────────────────────────────────────────────────────

def apply_auto_fixes(entities: list[dict], issues: list[dict]) -> int:
    """将 apply_fix=True 的问题自动应用到实体列表。"""
    entity_map = {e["canonical"]: i for i, e in enumerate(entities)}
    applied = 0
    for issue in issues:
        if not issue.get("apply_fix"):
            continue
        canonical = issue.get("entity")
        field = issue.get("field")
        new_val = issue.get("suggested_value")
        if canonical not in entity_map or field is None:
            continue
        idx = entity_map[canonical]
        entities[idx][field] = new_val
        applied += 1
    logger.info("自动修复应用：%d 处", applied)
    return applied


# ──────────────────────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────────────────────

def run_validation(
    steps: list[int] | None = None,
    resume: bool = True,
    model: str = "deepseek-chat",
    apply_fixes: bool = True,
) -> None:
    steps = steps or [1, 2]

    data = json.load(open(ENTITIES_IN))
    entities = data["entities"]
    logger.info("加载 %d 个实体", len(entities))

    all_issues: list[dict] = []

    # 加载已有问题（断点续跑）
    if resume and ISSUES_OUT.exists():
        try:
            existing = json.load(open(ISSUES_OUT))
            all_issues = existing.get("issues", [])
            logger.info("从已有结果恢复：%d 个问题", len(all_issues))
        except Exception:
            pass

    if 1 in steps:
        logger.info("=== Step 1：规则验证 ===")
        step1_issues = step1_rule_validation(entities)
        # 合并（去重）
        existing_keys = {(x["entity"], x["field"], x["issue_type"]) for x in all_issues}
        for issue in step1_issues:
            key = (issue["entity"], issue["field"], issue["issue_type"])
            if key not in existing_keys:
                all_issues.append(issue)
                existing_keys.add(key)

    if 2 in steps:
        logger.info("=== Step 2：DeepSeek 批判性审查 ===")
        step2_issues = step2_deepseek_validation(entities, resume=resume, model=model)
        existing_keys = {(x["entity"], x["field"], x["issue_type"]) for x in all_issues}
        for issue in step2_issues:
            key = (issue["entity"], issue.get("field",""), issue.get("issue_type",""))
            if key not in existing_keys:
                all_issues.append(issue)
                existing_keys.add(key)

    # 自动应用 apply_fix=True 的修复
    if apply_fixes:
        applied = apply_auto_fixes(entities, all_issues)
        if applied > 0:
            data["entities"] = entities
            data["version"] = "4.1"
            data["description"] = "崩坏：星穹铁道领域实体词表（v4.1 — 验证后自动修复版）"
            with open(ENTITIES_IN, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("✓ 已将自动修复写回 %s", ENTITIES_IN)

    # 保存问题列表
    output = {
        "validated_at": __import__("time").strftime("%Y-%m-%d %H:%M UTC"),
        "total_entities": len(entities),
        "total_issues": len(all_issues),
        "auto_fixed": sum(1 for x in all_issues if x.get("apply_fix")),
        "by_severity": {
            "error":   sum(1 for x in all_issues if x.get("severity") == "error"),
            "warning": sum(1 for x in all_issues if x.get("severity") == "warning"),
            "info":    sum(1 for x in all_issues if x.get("severity") == "info"),
        },
        "issues": all_issues,
    }
    with open(ISSUES_OUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    logger.info("✓ 问题列表保存到 %s", ISSUES_OUT)

    # 生成报告
    report = generate_report(all_issues, entities)
    REPORT_OUT.write_text(report, encoding="utf-8")
    logger.info("✓ 报告保存到 %s", REPORT_OUT)

    # 终端摘要
    e_cnt = sum(1 for x in all_issues if x.get("severity") == "error")
    w_cnt = sum(1 for x in all_issues if x.get("severity") == "warning")
    i_cnt = sum(1 for x in all_issues if x.get("severity") == "info")
    logger.info(
        "\n=== 验证完成 ===\n"
        "  ❌ error:   %d\n"
        "  ⚠️ warning: %d\n"
        "  ℹ️ info:    %d\n"
        "  总计:       %d",
        e_cnt, w_cnt, i_cnt, len(all_issues),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps",    default="1,2",
                        help="执行哪些步骤（默认 1,2）")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--no-fix",    action="store_true",
                        help="不自动应用修复")
    parser.add_argument("--model",    default="deepseek-chat")
    args = parser.parse_args()

    steps = [int(s) for s in args.steps.split(",")]
    run_validation(
        steps=steps,
        resume=not args.no_resume,
        model=args.model,
        apply_fixes=not args.no_fix,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    main()
