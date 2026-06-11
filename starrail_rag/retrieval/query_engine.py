"""
Agent Query Engine — ReAct 迭代检索架构

架构决策（2026-06-11）：
  放弃 GraphRAG / LightRAG，改用 ReAct 风格 Agent + 迭代检索。
  原因：GraphRAG 建图成本高、质量问题多、实际评估贡献为零。
  新方案：让 LLM 在查询时推理"缺什么"，主动发起 follow-up 检索。

两种模式：
  SIMPLE  → 单次检索 + 生成（快速，适合事实性问题）
  COMPLEX → ReAct 迭代循环（最多 3 轮，适合多跳推理）

实体上下文注入：
  检测 query 中的命名实体，从 entities_v4.json 注入相关描述，
  提升实体消歧准确性，无需图遍历。
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ENTITIES_PATH = Path("/workspace/output/entities_v4.json")
_DEEPSEEK_BASE = "https://api.deepseek.com"

# ──────────────────────────────────────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ReActStep:
    iteration: int
    thought:   str = ""
    sub_queries: list[str] = field(default_factory=list)
    retrieved_count: int = 0


@dataclass
class QueryResult:
    query:           str
    answer:          str
    mode:            str    # "simple" | "react"
    iterations:      int = 0
    react_trace:     list[ReActStep] = field(default_factory=list)
    chunks_used:     int = 0
    confidence_note: str = ""
    error:           str = ""


# ──────────────────────────────────────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_BASE = """你是崩坏：星穹铁道世界观的专家分析师。
请基于提供的参考资料回答问题。

回答规范：
- 只使用参考资料中的信息；资料不足时明确说明
- 区分「确定的事实」和「可能的推断」
- 对于需要跨文本推理的问题，明确说明推理步骤
- 回答用中文，风格清晰
"""

_THINK_PROMPT = """你正在回答以下问题：
{question}

目前已有的参考资料：
{context}

请分析：
1. 基于现有资料，你能确定回答哪些部分？
2. 还缺少哪些关键信息无法完整回答？

如果现有资料已经足够回答，回复：
{{"sufficient": true, "reason": "为什么足够"}}

如果还需要更多信息，回复：
{{"sufficient": false, "missing": "缺少什么信息（一句话）", "sub_queries": ["查询1", "查询2"]}}

注意：sub_queries 应该是具体的检索查询，最多 2 个，针对最关键的缺失信息。
只输出 JSON，不要其他内容："""

_ANSWER_PROMPT = """请回答以下问题：
{question}

参考资料（已通过 {iterations} 轮检索收集）：
{context}

{entity_context}

请给出完整回答。对于需要推断的内容，说明推理依据。"""


# ──────────────────────────────────────────────────────────────────────────────
# 实体上下文注入
# ──────────────────────────────────────────────────────────────────────────────

def _load_entity_index() -> dict[str, dict]:
    """加载实体索引（规范名+别称 → 实体数据）。"""
    if not _ENTITIES_PATH.exists():
        return {}
    try:
        data = json.load(open(_ENTITIES_PATH))
        index = {}
        for e in data.get("entities", []):
            index[e["canonical"]] = e
            for alias in e.get("aliases", []):
                if alias and alias not in index:
                    index[alias] = e
        return index
    except Exception:
        return {}


_ENTITY_INDEX: dict[str, dict] | None = None


def _get_entity_context(query: str) -> str:
    """在 query 中检测实体名称，返回相关实体描述（上下文注入）。"""
    global _ENTITY_INDEX
    if _ENTITY_INDEX is None:
        _ENTITY_INDEX = _load_entity_index()
    if not _ENTITY_INDEX:
        return ""

    found: list[dict] = []
    seen: set[str] = set()

    for name, entity in _ENTITY_INDEX.items():
        if len(name) < 2:
            continue
        if name in query and entity["canonical"] not in seen:
            found.append(entity)
            seen.add(entity["canonical"])
        if len(found) >= 6:
            break

    if not found:
        return ""

    lines = ["【相关实体背景】"]
    for e in found:
        desc = e.get("description", "")
        if not desc:
            continue
        # 加入关键属性
        extras = []
        if e.get("current_status") == "deceased":
            extras.append("已故")
        elif e.get("current_status") == "missing":
            extras.append("下落不明")
        if e.get("species") and e["species"] not in ("人类", "unknown", None):
            extras.append(e["species"])
        if e.get("is_emanator"):
            aeon = e.get("emanator_of", "")
            if aeon:
                extras.append(f"{aeon}的令使")
        extra_str = f"（{', '.join(extras)}）" if extras else ""
        lines.append(f"· {e['canonical']}{extra_str}：{desc}")

    return "\n".join(lines) if len(lines) > 1 else ""


# ──────────────────────────────────────────────────────────────────────────────
# 格式化检索结果
# ──────────────────────────────────────────────────────────────────────────────

def _format_chunks(chunks: list[dict], max_chars: int = 6000) -> str:
    parts = []
    total = 0
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata", {})
        source = (
            meta.get("mission_title")
            or meta.get("lore_title")
            or meta.get("chapter_name")
            or "未知来源"
        )
        text = chunk.get("text", "").strip()
        if not text:
            continue
        entry = f"[来源 {i}: {source}]\n{text}"
        if total + len(entry) > max_chars:
            break
        parts.append(entry)
        total += len(entry)
    return "\n\n---\n\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# LLM 调用
# ──────────────────────────────────────────────────────────────────────────────

async def _call_llm(
    messages: list[dict],
    model: str,
    api_key: str,
    max_tokens: int = 2000,
    temperature: float = 0.3,
) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key, base_url=_DEEPSEEK_BASE)
    resp = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


# ──────────────────────────────────────────────────────────────────────────────
# 核心：ReAct Agent Loop
# ──────────────────────────────────────────────────────────────────────────────

async def _react_query(
    question: str,
    retrieve_fn,
    deepseek_key: str,
    model_think: str = "deepseek-chat",
    model_answer: str = "deepseek-chat",
    max_iterations: int = 3,
    n_retrieve: int = 8,
) -> QueryResult:
    """ReAct 迭代检索核心逻辑。"""
    all_chunks: list[dict] = []
    seen_texts: set[str] = set()
    react_trace: list[ReActStep] = []

    def _add_chunks(new_chunks: list[dict]) -> int:
        added = 0
        for c in new_chunks:
            key = c.get("text", "")[:100]
            if key not in seen_texts:
                seen_texts.add(key)
                all_chunks.append(c)
                added += 1
        return added

    # 第 0 轮：初始检索
    initial = retrieve_fn(question, n=n_retrieve)
    added = _add_chunks(initial)
    logger.info("初始检索: %d 条新片段", added)

    for iteration in range(1, max_iterations + 1):
        context = _format_chunks(all_chunks)
        step = ReActStep(iteration=iteration)

        # Think：是否足够？
        think_prompt = _THINK_PROMPT.format(question=question, context=context[:4000])
        think_resp = await _call_llm(
            messages=[
                {"role": "system", "content": "你是崩坏：星穹铁道世界观分析师。"},
                {"role": "user",   "content": think_prompt},
            ],
            model=model_think,
            api_key=deepseek_key,
            max_tokens=300,
            temperature=0.1,
        )

        # 解析 think 响应
        try:
            raw = think_resp.strip()
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            think_data = json.loads(raw[start:end]) if start >= 0 else {}
        except Exception:
            think_data = {"sufficient": True}

        step.thought = think_data.get("missing", think_data.get("reason", ""))

        if think_data.get("sufficient", True):
            logger.info("第 %d 轮：资料已足够", iteration)
            react_trace.append(step)
            break

        # Act：执行 follow-up 检索
        sub_queries = think_data.get("sub_queries", [])[:2]
        step.sub_queries = sub_queries

        new_added = 0
        for q in sub_queries:
            if not q.strip():
                continue
            logger.info("  follow-up: %s", q[:50])
            new_chunks = retrieve_fn(q, n=5)
            new_added += _add_chunks(new_chunks)

        step.retrieved_count = new_added
        react_trace.append(step)
        logger.info("第 %d 轮：获取 %d 条新片段", iteration, new_added)

        if new_added == 0:
            break

    # 生成最终答案
    entity_ctx = _get_entity_context(question)
    context = _format_chunks(all_chunks)
    answer_prompt = _ANSWER_PROMPT.format(
        question=question,
        context=context,
        entity_context=entity_ctx if entity_ctx else "",
        iterations=len(react_trace),
    )

    answer = await _call_llm(
        messages=[
            {"role": "system", "content": _SYSTEM_BASE},
            {"role": "user",   "content": answer_prompt},
        ],
        model=model_answer,
        api_key=deepseek_key,
        max_tokens=2000,
        temperature=0.3,
    )

    return QueryResult(
        query=question,
        answer=answer,
        mode="react",
        iterations=len(react_trace),
        react_trace=react_trace,
        chunks_used=len(all_chunks),
    )


# ──────────────────────────────────────────────────────────────────────────────
# 简单模式（单次检索）
# ──────────────────────────────────────────────────────────────────────────────

async def _simple_query(
    question: str,
    retrieve_fn,
    deepseek_key: str,
    model: str = "deepseek-chat",
    n_retrieve: int = 8,
) -> QueryResult:
    chunks = retrieve_fn(question, n=n_retrieve)
    entity_ctx = _get_entity_context(question)
    context = _format_chunks(chunks)

    prompt = (
        f"参考资料：\n{context}\n\n"
        + (f"{entity_ctx}\n\n" if entity_ctx else "")
        + f"问题：{question}"
    )
    answer = await _call_llm(
        messages=[
            {"role": "system", "content": _SYSTEM_BASE},
            {"role": "user",   "content": prompt},
        ],
        model=model,
        api_key=deepseek_key,
        max_tokens=1000,
        temperature=0.3,
    )
    return QueryResult(
        query=question,
        answer=answer,
        mode="simple",
        chunks_used=len(chunks),
    )


# ──────────────────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────────────────

class AgentQueryEngine:
    """
    基于 ReAct 迭代检索的 Agent 查询引擎。

    参数
    ----
    chroma_dir    : Chroma 向量库目录
    bm25_path     : BM25 索引文件
    deepseek_key  : DeepSeek API key
    ali_key       : DashScope（ALI）API key，用于 embedding
    chat_model    : 简单问题使用的模型
    reason_model  : 复杂推理使用的模型
    max_iterations: ReAct 最大迭代轮数
    """

    def __init__(
        self,
        chroma_dir:     str | Path = "/workspace/output/chroma_db",
        bm25_path:      str | Path = "/workspace/output/bm25_index.pkl",
        deepseek_key:   str | None = None,
        ali_key:        str | None = None,
        chat_model:     str = "deepseek-chat",
        reason_model:   str = "deepseek-chat",   # 换成 deepseek-reasoner 可提升 Hard 题
        max_iterations: int = 3,
    ) -> None:
        self._deepseek_key = deepseek_key or os.environ.get("HSR_DEEPSEEK_API_KEY", "")
        self._ali_key = ali_key or os.environ.get("ALI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", "")
        self._chat_model   = chat_model
        self._reason_model = reason_model
        self._max_iter     = max_iterations

        from starrail_rag.indexing.retriever import HybridRetriever
        # 检测 Chroma 是否可用
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(chroma_dir))
            col = client.get_collection("starrail_lore")
            chroma_ok = col.count() > 0
        except Exception:
            chroma_ok = False

        if chroma_ok:
            self._retriever = HybridRetriever(
                chroma_dir=chroma_dir,
                bm25_path=bm25_path,
                n_dense=10, n_sparse=10, n_final=8,
            )
            logger.info("混合检索（Dense + BM25）")
        else:
            # Chroma 为空，仅用 BM25
            logger.warning("Chroma DB 为空，退回到 BM25-only 检索（精度会低于混合模式）")
            from starrail_rag.indexing.sparse_store import BM25Store
            self._bm25_only = BM25Store(index_path=Path(bm25_path))
            self._retriever = None
            self._bm25_store = self._bm25_only

        from starrail_rag.retrieval.router import classify_query_by_rules, QueryMode
        self._classify = classify_query_by_rules
        self._QueryMode = QueryMode

    def _do_retrieve(self, query: str, n: int = 8) -> list[dict]:
        """统一检索接口，自动处理 BM25-only fallback。"""
        if self._retriever is not None:
            return self._retriever.query(query, n_final=n)
        # BM25-only 模式
        results = self._bm25_store.query(query, n_results=n)
        return results

    async def query(
        self,
        question: str,
        force_react: bool = False,
    ) -> QueryResult:
        """
        主查询入口。

        force_react=True  → 强制使用 ReAct（调试用）
        force_react=False → 路由自动判断
        """
        if not self._deepseek_key:
            return QueryResult(query=question, answer="", mode="error",
                               error="HSR_DEEPSEEK_API_KEY 未设置")
        try:
            mode = self._classify(question)
            use_react = force_react or (mode != self._QueryMode.SIMPLE)

            if use_react:
                logger.info("ReAct 模式（query mode: %s）", mode.value)
                return await _react_query(
                    question=question,
                    retrieve_fn=self._do_retrieve,
                    deepseek_key=self._deepseek_key,
                    model_think=self._chat_model,
                    model_answer=self._reason_model,
                    max_iterations=self._max_iter,
                )
            else:
                logger.info("Simple 模式")
                return await _simple_query(
                    question=question,
                    retrieve_fn=self._do_retrieve,
                    deepseek_key=self._deepseek_key,
                    model=self._chat_model,
                )

        except Exception as exc:
            logger.error("Query failed: %s", exc)
            return QueryResult(query=question, answer="", mode="error", error=str(exc))
