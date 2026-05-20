"""
统一查询引擎（W12 + W13）。

架构：
  QueryEngine.query(text)
    ├── 路由分类（规则 → LLM 确认）
    ├── SIMPLE  → HybridRetriever → deepseek-chat 生成
    ├── COMPLEX → LightRAG local  → deepseek-reasoner 生成（Hard 题）
    └── GLOBAL  → LightRAG global → deepseek-reasoner 生成

设计原则：
  - VectorStore 抽象层：换 embedding 不改下游
  - LightRAG 可选：未构建时自动 fallback 到 HybridRetriever
  - 生成模型分层：Easy/Medium 用 chat，Hard 用 reasoner
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from starrail_rag.retrieval.router import QueryMode, classify_query_by_rules

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# 系统 Prompt
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """你是一位崩坏：星穹铁道世界观的专业分析师。
请基于提供的参考资料回答问题。

回答规范：
- 只使用参考资料中的信息；如果资料不足，明确说明
- 区分「确定的事实」和「可能的推断」
- 对于跨文本的隐性关联，说明你的推理依据
- 回答用中文，风格简洁清晰
"""


# ──────────────────────────────────────────────────────────────────────────────
# 数据类
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class QueryResult:
    query:       str
    answer:      str
    mode:        QueryMode
    sources:     list[dict] = field(default_factory=list)
    llm_model:   str = ""
    error:       str = ""


# ──────────────────────────────────────────────────────────────────────────────
# LLM 生成辅助
# ──────────────────────────────────────────────────────────────────────────────

async def _generate(
    prompt: str,
    context: str,
    model: str,
    api_key: str,
) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    user_msg = f"参考资料：\n{context}\n\n问题：{prompt}"
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=2000,
        temperature=0.3,
    )
    return resp.choices[0].message.content or ""


# ──────────────────────────────────────────────────────────────────────────────
# 查询引擎
# ──────────────────────────────────────────────────────────────────────────────

class QueryEngine:
    """
    统一查询入口。

    参数
    ----
    chroma_dir   : Chroma 向量库目录
    bm25_path    : BM25 索引文件
    lightrag_dir : LightRAG 工作目录（None = 只用 Hybrid）
    embed_fn     : embedding 函数（None = 使用 DashScope）
    deepseek_key : DeepSeek API key
    chat_model   : Easy/Medium 题 LLM
    reasoner_model: Hard 题 LLM
    use_llm_routing: 是否用 LLM 辅助路由（更准确但有成本）
    """

    def __init__(
        self,
        chroma_dir:       str | Path = "/workspace/output/chroma_db",
        bm25_path:        str | Path = "/workspace/output/bm25_index.pkl",
        lightrag_dir:     str | Path | None = "/workspace/output/lightrag_db",
        embed_fn=None,
        deepseek_key:     str | None = None,
        ali_key:          str | None = None,
        chat_model:       str = "deepseek-chat",
        reasoner_model:   str = "deepseek-reasoner",
        use_llm_routing:  bool = False,
    ) -> None:
        self._deepseek_key = deepseek_key or os.environ.get("HSR_DEEPSEEK_API_KEY", "")
        self._ali_key = ali_key or os.environ.get("ALI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", "")
        self._chat_model = chat_model
        self._reasoner_model = reasoner_model
        self._use_llm_routing = use_llm_routing

        # 混合检索器（Dense + BM25）
        from starrail_rag.indexing.retriever import HybridRetriever
        self._hybrid = HybridRetriever(
            chroma_dir=chroma_dir,
            bm25_path=bm25_path,
            embed_fn=embed_fn,
            n_dense=20,
            n_sparse=20,
            n_final=10,
        )

        # LightRAG（可选）
        self._rag = None
        self._lightrag_dir = Path(lightrag_dir) if lightrag_dir else None

    async def _get_lightrag(self):
        """延迟加载 LightRAG（避免启动时 import 开销）。"""
        if self._rag is not None:
            return self._rag
        if self._lightrag_dir is None or not self._lightrag_dir.exists():
            logger.warning("LightRAG dir not found, falling back to HybridRetriever")
            return None
        try:
            from starrail_rag.lightrag_builder import build_graph
            self._rag = await build_graph(
                work_dir=self._lightrag_dir,
                llm_model=self._chat_model,
            )
            return self._rag
        except Exception as e:
            logger.error("Failed to load LightRAG: %s", e)
            return None

    async def query(
        self,
        text: str,
        force_mode: QueryMode | None = None,
        n_results: int = 10,
    ) -> QueryResult:
        """
        主查询入口。

        参数
        ----
        text        : 用户问题
        force_mode  : 强制指定模式（调试用）
        n_results   : Hybrid 检索返回数量
        """
        # ── 路由决策
        if force_mode:
            mode = force_mode
        else:
            mode = classify_query_by_rules(text)
            if self._use_llm_routing and mode == QueryMode.COMPLEX:
                # 用 LLM 二次确认复杂查询
                try:
                    from starrail_rag.retrieval.router import classify_query_by_llm
                    mode = await classify_query_by_llm(text, self._deepseek_key)
                except Exception:
                    pass  # fallback to rule-based result

        logger.info("Query mode: %s | query: %s", mode.value, text[:50])

        # ── 根据模式选择检索 + 生成
        try:
            if mode == QueryMode.SIMPLE:
                return await self._hybrid_query(text, mode, n_results)

            elif mode in (QueryMode.COMPLEX, QueryMode.GLOBAL):
                rag = await self._get_lightrag()
                if rag is not None:
                    return await self._lightrag_query(text, mode, rag)
                else:
                    # Fallback to hybrid
                    logger.info("LightRAG unavailable, using HybridRetriever")
                    return await self._hybrid_query(text, mode, n_results)
            else:
                return await self._hybrid_query(text, mode, n_results)

        except Exception as e:
            logger.error("Query failed: %s", e)
            return QueryResult(query=text, answer="", mode=mode, error=str(e))

    async def _hybrid_query(self, text: str, mode: QueryMode, n: int) -> QueryResult:
        """HybridRetriever → deepseek-chat 生成。"""
        results = self._hybrid.query(text, n_final=n)
        if not results:
            return QueryResult(query=text, answer="未找到相关内容。", mode=mode)

        context = "\n\n---\n\n".join(
            f"[来源: {r.get('metadata', {}).get('mission_title') or r.get('metadata', {}).get('lore_title', '未知')}]\n{r['text']}"
            for r in results[:8]
        )
        answer = await _generate(text, context, self._chat_model, self._deepseek_key)
        return QueryResult(
            query=text,
            answer=answer,
            mode=mode,
            sources=results[:8],
            llm_model=self._chat_model,
        )

    async def _lightrag_query(self, text: str, mode: QueryMode, rag) -> QueryResult:
        """LightRAG → deepseek-reasoner 生成（Hard 题）。失败时 fallback 到 Hybrid。"""
        from lightrag import QueryParam
        lightrag_mode = "local" if mode == QueryMode.COMPLEX else "global"
        try:
            answer = await rag.aquery(
                text,
                param=QueryParam(mode=lightrag_mode),
            )
        except Exception as e:
            logger.warning("LightRAG query failed (%s), falling back to HybridRetriever", e)
            return await self._hybrid_query(text, mode, 10)

        if not answer:
            logger.warning("LightRAG returned empty answer, falling back to HybridRetriever")
            return await self._hybrid_query(text, mode, 10)

        return QueryResult(
            query=text,
            answer=answer,
            mode=mode,
            llm_model=self._chat_model,
        )
