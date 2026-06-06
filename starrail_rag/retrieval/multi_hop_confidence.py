"""
多跳推理置信度衰减计算。

问题：当 RAG 系统需要跨多个关系进行推理时（A → B → C → D），
每一跳都引入不确定性，但当前系统对 1-hop 和 4-hop 推理的置信度处理相同。

解决方案：为推理链计算综合置信度分数，并在回答中适当标注不确定性。

用法：
    from starrail_rag.retrieval.multi_hop_confidence import chain_confidence, format_confidence_note

    relations = [
        {"reliability": "confirmed", "confidence": "confirmed"},
        {"reliability": "character_account", "confidence": "probable"},
        {"reliability": "speculation", "confidence": "speculative"},
    ]
    score = chain_confidence(relations)
    note = format_confidence_note(score, len(relations))
"""

from __future__ import annotations

from dataclasses import dataclass

# ──────────────────────────────────────────────────────────────────────────────
# 评分矩阵
# ──────────────────────────────────────────────────────────────────────────────

RELIABILITY_SCORE: dict[str, float] = {
    "confirmed":            1.00,
    "historical_record":    0.85,
    "character_account":    0.65,
    "legend":               0.45,
    "speculation":          0.25,
    "in_character_fiction": 0.10,
    "reconstructed":        0.15,
    "retracted":            0.00,
}

CONFIDENCE_SCORE: dict[str, float] = {
    "confirmed":   1.00,
    "probable":    0.75,
    "speculative": 0.35,
}

HOP_DECAY: float = 0.85  # 每增加一跳，综合置信度乘以 0.85


@dataclass
class ChainConfidenceResult:
    score:       float        # 0.0 – 1.0
    n_hops:      int
    min_reliability: str      # 链中最低可信度级别
    overall_level: str        # "high"|"medium"|"low"|"very_low"
    note: str                 # 人类可读的注释


def chain_confidence(
    relations: list[dict],
    include_hop_decay: bool = True,
) -> ChainConfidenceResult:
    """
    计算多跳推理链的综合置信度。

    参数
    ----
    relations : 推理链中的关系列表，每个 dict 包含 reliability 和 confidence
    include_hop_decay : 是否加入跳数衰减（建议始终 True）

    返回
    ----
    ChainConfidenceResult
    """
    if not relations:
        return ChainConfidenceResult(
            score=1.0, n_hops=0,
            min_reliability="confirmed", overall_level="high",
            note="直接事实，无推理链",
        )

    score = 1.0
    reliabilities = []

    for rel in relations:
        reliability = rel.get("reliability", "confirmed")
        confidence = rel.get("confidence", "confirmed")
        r_score = RELIABILITY_SCORE.get(reliability, 0.5)
        c_score = CONFIDENCE_SCORE.get(confidence, 0.5)
        step_score = r_score * c_score
        score *= step_score
        reliabilities.append(reliability)
        if include_hop_decay:
            score *= HOP_DECAY

    score = round(max(0.0, min(1.0, score)), 3)
    n_hops = len(relations)

    # 找最低可信度
    min_reliability = min(
        reliabilities,
        key=lambda r: RELIABILITY_SCORE.get(r, 0.5),
    )

    # 确定整体级别
    if score >= 0.7:
        level = "high"
    elif score >= 0.4:
        level = "medium"
    elif score >= 0.15:
        level = "low"
    else:
        level = "very_low"

    # 生成注释
    level_notes = {
        "high":     "推理链置信度高，结论较为可靠",
        "medium":   "推理链置信度中等，结论有一定依据但存在不确定性",
        "low":      "推理链置信度较低，结论需谨慎对待，建议寻找更直接的证据",
        "very_low": "推理链置信度很低，结论高度不确定，可能仅是猜测",
    }
    note = (
        f"置信度分数: {score:.2f}（{n_hops}跳推理，"
        f"最低可信来源: {min_reliability}）。{level_notes[level]}"
    )

    return ChainConfidenceResult(
        score=score,
        n_hops=n_hops,
        min_reliability=min_reliability,
        overall_level=level,
        note=note,
    )


def format_confidence_note(result: ChainConfidenceResult) -> str:
    """
    生成适合插入 RAG 回答的置信度说明。
    low/very_low 级别会生成明显的警告。
    """
    if result.overall_level == "high":
        return ""  # 不需要注释
    elif result.overall_level == "medium":
        return f"\n\n*注：以上结论需要{result.n_hops}步推理，{result.note}*"
    elif result.overall_level == "low":
        return f"\n\n⚠️ **注意**：{result.note}"
    else:
        return f"\n\n⚠️ **高度不确定**：{result.note}。建议将以下内容视为推测而非事实。"


def annotate_answer_with_confidence(answer: str, relations: list[dict]) -> str:
    """
    为 RAG 生成的答案添加置信度标注。
    如果置信度高则不修改原文；低置信度则在末尾添加说明。
    """
    if not relations:
        return answer

    result = chain_confidence(relations)
    note = format_confidence_note(result)
    return answer + note
