"""
跨章节前后呼应关系构建器。

「隐秘联系」的核心：识别早期章节的谜题实体/未解事件，与后续章节的揭示内容之间的连接。

策略：
1. 扫描 entities.json，找出以下类型的"待解谜题实体"：
   - deliberately_ambiguous=true 的实体
   - current_status=unknown 的重要实体
   - 关系 confidence=speculative 的重要事实
2. 用 DeepSeek 分析这些谜题实体，在全部 entities.json 中寻找潜在的揭示节点
3. 输出结构化的前后呼应关系（需人工审核）

运行：
    python3 -m starrail_rag.tools.cross_reference_builder

输出：
    output/cross_references.json（待人工审核后作为 RAG 额外知识层）
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_ROOT  = Path("/workspace")
OUTPUT_DIR = DATA_ROOT / "output"

CROSS_REF_SCHEMA = {
    "id": "xref_XXX",
    "hint": {
        "chapter":      "ch01",
        "entity":       "六相冰",
        "hint_type":    "unexplained_object",
        "hint_content": "三月七被从不明来源的六相冰中打捞，制造者和目的未知"
    },
    "revelation": {
        "chapter":            "ch07+",
        "entity":             "浮黎（记忆星神）",
        "revelation_content": "记忆命途可以完美保存存在，六相冰是记忆命途的具象化产物"
    },
    "connection_type": "foreshadowing",
    "confidence":      "probable",
    "requires_hops":   2,
    "manually_verified": False,
}

PROMPT = """你是崩坏：星穹铁道世界观的专业分析师。
请分析以下「谜题实体」列表，找出在星铁世界观中可能与之相连的「揭示节点」。

谜题实体（来自早期章节，来源/目的未明）：
{puzzle_entities}

全部实体名称（供参考，找揭示节点时从中选择）：
{all_entities}

对每个谜题实体，找出1-3个最可能的前后呼应关系。
输出 JSON 数组：
[
  {{
    "puzzle_entity": "谜题实体名称",
    "puzzle_hint": "谜题内容（一句话描述）",
    "puzzle_chapter": "ch01",
    "revelation_entity": "揭示节点实体名称",
    "revelation_content": "揭示内容（一句话描述）",
    "revelation_chapter": "ch07",
    "connection_type": "foreshadowing|identity_reveal|callback|retcon",
    "confidence": "confirmed|probable|speculative",
    "reasoning": "为什么认为这两者有关联（1-2句）"
  }}
]

只输出有实质依据的连接，不要强行联系。JSON 数组："""


def _find_puzzle_entities(entities: list[dict]) -> list[dict]:
    """找出可能是「谜题实体」的实体。"""
    puzzles = []

    for e in entities:
        if e.get("deliberately_ambiguous"):
            puzzles.append({
                "canonical":  e["canonical"],
                "type":       e.get("type", ""),
                "description": e.get("description", ""),
                "hint_type":  "deliberately_ambiguous",
            })
            continue

        if e.get("current_status") in ("unknown", "missing"):
            puzzles.append({
                "canonical":  e["canonical"],
                "type":       e.get("type", ""),
                "description": e.get("description", ""),
                "hint_type":  f"unknown_status_{e.get('current_status')}",
            })
            continue

        # 有 speculative confidence 的关系
        speculative_rels = [
            r for r in e.get("known_relations", [])
            if r.get("confidence") == "speculative"
        ]
        if speculative_rels:
            puzzles.append({
                "canonical":  e["canonical"],
                "type":       e.get("type", ""),
                "description": e.get("description", ""),
                "hint_type":  "speculative_relations",
                "speculative_count": len(speculative_rels),
            })

    return puzzles


def build_cross_references(
    entities_path: Path = OUTPUT_DIR / "entities.json",
    output_path:   Path = OUTPUT_DIR / "cross_references.json",
    model: str = "deepseek-chat",
    batch_size: int = 15,
) -> list[dict]:
    """
    主函数：构建跨章节前后呼应关系。
    输出需要人工审核后才能使用。
    """
    from openai import OpenAI

    api_key = os.environ.get("HSR_DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("HSR_DEEPSEEK_API_KEY 未设置")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    data = json.load(open(entities_path))
    entities = data["entities"]
    all_names = [f"{e['canonical']} ({e.get('type','')})" for e in entities]

    puzzles = _find_puzzle_entities(entities)
    logger.info("找到 %d 个谜题实体", len(puzzles))

    all_xrefs = []

    # 若已有部分结果，继续追加
    existing = []
    if output_path.exists():
        try:
            existing = json.load(open(output_path)).get("cross_references", [])
            logger.info("已有 %d 个前后呼应关系，继续追加", len(existing))
        except Exception:
            pass

    existing_puzzles = {x["hint"]["entity"] for x in existing}
    new_puzzles = [p for p in puzzles if p["canonical"] not in existing_puzzles]
    logger.info("需要处理的新谜题实体: %d", len(new_puzzles))

    all_xrefs.extend(existing)

    for i in range(0, len(new_puzzles), batch_size):
        batch = new_puzzles[i:i+batch_size]
        puzzle_text = "\n".join(
            f"- {p['canonical']} [{p['type']}]: {p['description']} (hint_type={p['hint_type']})"
            for p in batch
        )
        all_names_sample = "\n".join(all_names[:300])  # 限制长度

        prompt = PROMPT.format(
            puzzle_entities=puzzle_text,
            all_entities=all_names_sample,
        )

        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000,
                temperature=0.2,
            )
            content = resp.choices[0].message.content or ""
            start, end = content.find("["), content.rfind("]") + 1
            if start == -1 or end == 0:
                continue
            raw_xrefs = json.loads(content[start:end])

            for xref in raw_xrefs:
                all_xrefs.append({
                    "id": f"xref_{len(all_xrefs):04d}",
                    "hint": {
                        "chapter":      xref.get("puzzle_chapter", "unknown"),
                        "entity":       xref.get("puzzle_entity", ""),
                        "hint_type":    "auto_detected",
                        "hint_content": xref.get("puzzle_hint", ""),
                    },
                    "revelation": {
                        "chapter":            xref.get("revelation_chapter", "unknown"),
                        "entity":             xref.get("revelation_entity", ""),
                        "revelation_content": xref.get("revelation_content", ""),
                    },
                    "connection_type":    xref.get("connection_type", "foreshadowing"),
                    "confidence":         xref.get("confidence", "speculative"),
                    "reasoning":          xref.get("reasoning", ""),
                    "requires_hops":      2,
                    "manually_verified":  False,
                })

            logger.info("批次 %d/%d: +%d 个前后呼应关系",
                        i // batch_size + 1, (len(new_puzzles) + batch_size - 1) // batch_size,
                        len(raw_xrefs))
            time.sleep(1.5)

        except Exception as e:
            logger.warning("批次 %d 失败: %s", i // batch_size + 1, e)
            time.sleep(3)

    # 保存
    output = {
        "version": "1.0",
        "description": "跨章节前后呼应关系（DeepSeek 自动识别，需人工审核）",
        "total": len(all_xrefs),
        "verified": sum(1 for x in all_xrefs if x.get("manually_verified")),
        "cross_references": all_xrefs,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(output, open(output_path, "w"), ensure_ascii=False, indent=2)
    logger.info("✓ %d 个前后呼应关系保存到 %s（请人工审核后使用）", len(all_xrefs), output_path)
    return all_xrefs


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build_cross_references()
