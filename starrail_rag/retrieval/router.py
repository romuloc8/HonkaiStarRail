"""
查询路由器：判断查询应走哪条检索路径。

路由策略：
  简单查询（单跳事实查询）→ HybridRetriever（Dense + BM25，速度快）
  复杂查询（多跳推理/关系变化/历史事件）→ LightRAG（图遍历，深度推理）

路由方式：
  1. 规则预筛（低成本，高速）：匹配复杂查询关键词
  2. LLM 分类（高准确，有成本）：用 deepseek-chat 做快速判断
"""
from __future__ import annotations

import re
from enum import Enum

# 触发 LightRAG 路径的关键词模式
_COMPLEX_PATTERNS = [
    re.compile(p) for p in [
        r'关系.*变化|变化.*关系',
        r'为什么|原因|导致|影响',
        r'历史|过去|曾经|从前|之前|之后',
        r'隐藏|隐秘|秘密|背后|真相',
        r'联系|关联|连接|相关',
        r'如何.*演变|怎么.*变成',
        r'哪些.*都|所有.*共同',
        r'比较|对比|区别|不同.*相同',
        r'推测|猜测|可能|也许',
        r'第.*次轮回|循环|轮回',
        r'来龙去脉|始末|经过',
        r'的.*原因|原因.*是',   # 「X 的原因」「原因是什么」
        r'怎么|如何.*发生|为何',
    ]
]

_SIMPLE_PATTERNS = [
    re.compile(p) for p in [
        r'^.{0,20}是谁$|^.{0,20}是什么$',
        r'^.{0,20}的命途是',
        r'^.{0,20}属于哪个',
        r'^.{0,20}叫什么',
    ]
]


class QueryMode(str, Enum):
    SIMPLE   = "simple"   # → HybridRetriever
    COMPLEX  = "complex"  # → LightRAG local search
    GLOBAL   = "global"   # → LightRAG global search（主题综合类）


def classify_query_by_rules(query: str) -> QueryMode:
    """
    基于规则的快速分类（无 API 调用）。
    返回 SIMPLE / COMPLEX / GLOBAL。
    """
    # 全局综合类（关键词：「总结」「概述」「所有」「整体」）
    if re.search(r'总结|概述|综合|全部|整体|有哪些.*都', query):
        return QueryMode.GLOBAL

    # 简单事实
    for pat in _SIMPLE_PATTERNS:
        if pat.search(query):
            return QueryMode.SIMPLE

    # 复杂推理
    for pat in _COMPLEX_PATTERNS:
        if pat.search(query):
            return QueryMode.COMPLEX

    # 默认：根据长度判断
    if len(query) > 30:
        return QueryMode.COMPLEX
    return QueryMode.SIMPLE


async def classify_query_by_llm(query: str, api_key: str) -> QueryMode:
    """
    用 deepseek-chat 做精确分类（有 API 成本，用于规则不确定的情况）。
    """
    from openai import AsyncOpenAI
    import json as _json

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )
    resp = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": (
                    "你是一个查询分类器。判断以下问题属于哪类：\n"
                    "simple：单一事实查询（某角色的属性、某地点的描述）\n"
                    "complex：需要多跳推理、关系分析、历史事件、因果推断\n"
                    "global：需要综合多个来源、总结主题、对比分析\n"
                    "只输出 simple / complex / global 三个词之一，不要其他内容。"
                ),
            },
            {"role": "user", "content": query},
        ],
        max_tokens=10,
        temperature=0.0,
    )
    label = resp.choices[0].message.content.strip().lower()
    return QueryMode(label) if label in QueryMode._value2member_map_ else QueryMode.COMPLEX
