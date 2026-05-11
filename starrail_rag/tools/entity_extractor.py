"""
DeepSeek 驱动的实体提取器。

从书籍、角色故事、遗器套装等高密度 lore 文本中提取实体及其别称，
生成比静态词表更准确、更全面的领域词表。

运行：
    python -m starrail_rag.tools.entity_extractor

输出：
    output/entities_raw.jsonl    # 每批次的原始提取结果
    output/entities_merged.json  # 合并去重后的最终词表

环境变量：
    HSR_DEEPSEEK_API_KEY         # DeepSeek API Key
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

DATA_ROOT = Path("/workspace")
RAW_OUTPUT = DATA_ROOT / "output" / "entities_raw.jsonl"
MERGED_OUTPUT = DATA_ROOT / "output" / "entities_merged.json"

# 每批次目标 token 数（文本部分）— 控制 prompt 长度不超过 4k tokens
BATCH_TARGET_TOKENS = 1200
# 每批次最多文档数（防止少量超长文档撑满 token）
BATCH_MAX_DOCS = 6
# 批次间请求延迟（秒）
REQUEST_DELAY = 1.0
# 单次 API 最大输出 token
MAX_OUTPUT_TOKENS = 2000

# -----------------------------------------------------------------------
# 提取 prompt
# -----------------------------------------------------------------------

SYSTEM_PROMPT = """你是一位崩坏：星穹铁道世界观的专业分析师。
你的任务是从游戏文本中识别命名实体及其别称。

实体类型说明：
- character  : 人物（可玩角色、NPC、历史人物、传说人物）
- aeon       : 星神（宇宙级神灵，对应某一命途）
- path       : 命途（星神所代表的哲学/力量方向，如存护、毁灭、巡猎）
- faction    : 阵营/组织（星核猎手、云骑军、地火、天才俱乐部等）
- location   : 地点（星球、城市、区域、建筑）
- event      : 历史事件（灾变、战役、重大历史节点）
- concept    : 重要概念/神器/特殊物品（星核、裂界、逐火之旅等）

别称定义：在文本中出现的、指代同一实体的不同名称，包括：
- 称号、头衔、雅称（如「命运的奴隶」= 艾利欧的组织称号）
- 隐喻表达（如「帝弓司命」= 巡猎星神的别称）
- 简称/全称变体
- 只取文本中实际出现的别称，不要凭空推测"""

USER_PROMPT_TEMPLATE = """请从以下【{count}段】崩坏：星穹铁道游戏文本中提取所有命名实体。

{texts}

---
输出要求：
1. 严格输出 JSON 数组，不要其他内容
2. 每个实体格式：{{"canonical": "规范名", "aliases": ["别称1", "别称2"], "type": "类型", "source_hint": "简短说明实体来源"}}
3. canonical 使用最常见、最正式的名称
4. aliases 只包含文本中真实出现过的其他称谓
5. 不同段落提到的同一实体请合并（取并集别称）
6. 忽略游戏机制性词汇（如「攻击力」「暴击率」）

JSON 数组："""


# -----------------------------------------------------------------------
# 文档加载
# -----------------------------------------------------------------------

def _load_docs(paths: list[Path]) -> list[dict]:
    """从 JSONL 文件加载文档。"""
    docs = []
    for path in paths:
        if not path.exists():
            logger.warning("File not found: %s", path)
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    docs.append(json.loads(line))
    return docs


def _doc_to_text(doc: dict) -> str:
    """将文档转为适合发送给 LLM 的纯文本。"""
    title = doc.get("title", "")
    body = doc.get("body", "")
    dialogues = doc.get("dialogues", [])

    parts = []
    if title:
        parts.append(f"【{title}】")
    if body:
        # 截断过长的正文，保留关键内容
        parts.append(body[:1500])
    elif dialogues:
        # 对话文本：取前20行
        lines = [f"{d['speaker']}：{d['text']}" for d in dialogues[:20] if d.get("text")]
        parts.append("\n".join(lines))

    return "\n".join(parts).strip()


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中文字符 ÷ 1.5，英文 ÷ 4）。"""
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4)


# -----------------------------------------------------------------------
# 批次构建
# -----------------------------------------------------------------------

def _build_batches(
    docs: list[dict],
    target_tokens: int = BATCH_TARGET_TOKENS,
    max_docs: int = BATCH_MAX_DOCS,
) -> list[list[dict]]:
    """按 token 预算和文档数上限把文档分成批次。"""
    batches: list[list[dict]] = []
    current_batch: list[dict] = []
    current_tokens = 0

    for doc in docs:
        text = _doc_to_text(doc)
        tokens = _estimate_tokens(text)
        if not text:
            continue

        # 超过 token 预算或文档数上限时开新批次
        if current_batch and (current_tokens + tokens > target_tokens or len(current_batch) >= max_docs):
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0

        current_batch.append(doc)
        current_tokens += tokens

    if current_batch:
        batches.append(current_batch)

    return batches


# -----------------------------------------------------------------------
# API 调用
# -----------------------------------------------------------------------

def _call_deepseek(
    client: OpenAI, batch: list[dict], model: str = "deepseek-chat"
) -> list[dict]:
    """提取一个批次的实体，返回原始结果列表。"""
    texts = []
    for i, doc in enumerate(batch, 1):
        text = _doc_to_text(doc)
        if text:
            texts.append(f"[段落{i}·{doc.get('doc_type', '')}·{doc.get('title', '')}]\n{text}")

    if not texts:
        return []

    prompt = USER_PROMPT_TEMPLATE.format(
        count=len(texts),
        texts="\n\n".join(texts),
    )

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=MAX_OUTPUT_TOKENS,
                temperature=0.1,  # 低温度保证输出稳定
            )
            content = resp.choices[0].message.content or ""
            # 解析 JSON
            # 找到第一个 [ 和最后一个 ]
            start = content.find("[")
            end = content.rfind("]") + 1
            if start == -1 or end == 0:
                logger.debug("No JSON array in response: %s", content[:200])
                return []
            entities = json.loads(content[start:end])
            return entities if isinstance(entities, list) else []
        except json.JSONDecodeError as e:
            logger.debug("JSON parse error (attempt %d): %s", attempt + 1, e)
            if attempt < 2:
                time.sleep(2 ** attempt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("API error (attempt %d): %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2 ** attempt)

    return []


# -----------------------------------------------------------------------
# 结果合并
# -----------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """规范化名称用于去重比较。"""
    return name.strip().replace("（", "(").replace("）", ")").lower()


def _merge_entities(all_raw: list[dict]) -> list[dict]:
    """
    合并多批次提取的实体：
    - 相同 canonical（规范化后）的实体合并别称
    - 统计出现次数作为置信度参考
    """
    # canonical_normalized → merged entity
    merged: dict[str, dict] = {}

    for raw in all_raw:
        if not isinstance(raw, dict):
            continue
        canonical = str(raw.get("canonical", "")).strip()
        if not canonical:
            continue

        aliases = [str(a).strip() for a in raw.get("aliases", []) if str(a).strip()]
        entity_type = str(raw.get("type", "concept")).strip()
        source_hint = str(raw.get("source_hint", "")).strip()

        key = _normalize_name(canonical)

        if key in merged:
            # 合并别称
            existing_aliases = set(merged[key]["aliases"])
            for alias in aliases:
                if alias != canonical:
                    existing_aliases.add(alias)
            merged[key]["aliases"] = sorted(existing_aliases)
            merged[key]["mention_count"] += 1
            # 保留更具体的 source_hint
            if source_hint and not merged[key].get("source_hint"):
                merged[key]["source_hint"] = source_hint
        else:
            merged[key] = {
                "canonical": canonical,
                "aliases": sorted(set(a for a in aliases if a != canonical)),
                "type": entity_type,
                "source_hint": source_hint,
                "mention_count": 1,
            }

    # 按出现次数排序，高频实体排前面
    result = sorted(merged.values(), key=lambda x: -x["mention_count"])
    return result


# -----------------------------------------------------------------------
# 主流程
# -----------------------------------------------------------------------

def run_extraction(
    doc_paths: list[Path] | None = None,
    model: str = "deepseek-chat",
    resume: bool = True,
) -> list[dict]:
    """
    主提取流程。

    Parameters
    ----------
    doc_paths : 要处理的 JSONL 文件列表，默认处理高密度 lore 文件
    model     : DeepSeek 模型名
    resume    : 是否从上次中断处继续（检查 RAW_OUTPUT 已有批次）
    """
    api_key = os.environ.get("HSR_DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("HSR_DEEPSEEK_API_KEY 环境变量未设置")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    if doc_paths is None:
        doc_paths = [
            DATA_ROOT / "output" / "book.jsonl",
            DATA_ROOT / "output" / "relic_set.jsonl",
            DATA_ROOT / "output" / "character_story.jsonl",
            DATA_ROOT / "output" / "light_cone.jsonl",
            DATA_ROOT / "output" / "item_lore.jsonl",
        ]

    # 加载文档
    docs = _load_docs(doc_paths)
    logger.info("Loaded %d documents from %d files", len(docs), len(doc_paths))

    # 构建批次
    batches = _build_batches(docs)
    logger.info("Built %d batches (target %d tokens/batch)", len(batches), BATCH_TARGET_TOKENS)

    # 断点续传：读取已有结果
    already_done = 0
    raw_results: list[dict] = []
    if resume and RAW_OUTPUT.exists():
        with open(RAW_OUTPUT, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    batch_result = json.loads(line)
                    raw_results.extend(batch_result.get("entities", []))
                    already_done += 1
        logger.info("Resuming from batch %d/%d", already_done, len(batches))

    # 处理剩余批次
    RAW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW_OUTPUT, "a", encoding="utf-8") as raw_f:
        for i, batch in enumerate(batches):
            if i < already_done:
                continue

            logger.info("Processing batch %d/%d (%d docs)...", i + 1, len(batches), len(batch))
            entities = _call_deepseek(client, batch, model=model)

            # 写入原始结果
            record = {
                "batch_idx": i,
                "doc_count": len(batch),
                "entity_count": len(entities),
                "entities": entities,
            }
            raw_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            raw_f.flush()

            raw_results.extend(entities)
            logger.info("  → %d entities extracted", len(entities))
            time.sleep(REQUEST_DELAY)

    logger.info("All batches done. Total raw entities: %d", len(raw_results))

    # 合并去重
    merged = _merge_entities(raw_results)
    logger.info("After merging: %d unique entities", len(merged))

    # 统计
    type_counts: dict[str, int] = {}
    for e in merged:
        t = e.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    output = {
        "version": "2.0",
        "description": "DeepSeek 从语料中提取的星穹铁道实体词表",
        "model": model,
        "stats": {
            "total_entities": len(merged),
            "by_type": type_counts,
            "total_raw_entities": len(raw_results),
            "docs_processed": len(docs),
        },
        "entities": merged,
    }

    with open(MERGED_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info("Merged lexicon written to %s", MERGED_OUTPUT)
    return merged


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    entities = run_extraction()
    print(f"\n提取完成：{len(entities)} 个唯一实体")
    by_type: dict[str, int] = {}
    for e in entities:
        by_type[e.get("type", "?")] = by_type.get(e.get("type", "?"), 0) + 1
    for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {n}")
