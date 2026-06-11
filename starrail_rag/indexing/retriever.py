"""
HybridRetriever — 融合 Dense（Chroma）和 Sparse（BM25）检索结果。

使用 Reciprocal Rank Fusion（RRF）合并两路排名：
  score_rrf = Σ 1 / (k + rank_i)
  k = 60（标准 RRF 参数，平衡高排名和低排名的权重）

优势：
  Dense  捕捉语义相似（「帝弓司命」≈ 「巡猎星神」）
  BM25   精确匹配关键词（「帝弓司命」必须出现在文本中）
  RRF    量纲无关，无需调参
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

RRF_K = 60  # 标准 RRF 参数


def _rrf_score(rank: int, k: int = RRF_K) -> float:
    return 1.0 / (k + rank)


class HybridRetriever:
    """
    混合检索：Dense + Sparse → RRF 融合。

    参数
    ----
    chroma_dir   : Chroma 持久化目录
    bm25_path    : BM25 索引文件路径
    embed_fn     : 文本→向量函数 callable(str) -> list[float]
    n_dense      : Dense 召回数量
    n_sparse     : BM25 召回数量
    n_final      : 最终返回数量
    """

    def __init__(
        self,
        chroma_dir: str | Path = "/workspace/output/chroma_db",
        bm25_path: str | Path = "/workspace/output/bm25_index.pkl",
        embed_fn=None,
        n_dense: int = 20,
        n_sparse: int = 20,
        n_final: int = 10,
    ) -> None:
        from starrail_rag.indexing.vector_store import ChromaStore
        from starrail_rag.indexing.sparse_store import BM25Store

        self._dense = ChromaStore(persist_dir=chroma_dir)
        self._sparse = BM25Store(index_path=Path(bm25_path))
        self._embed_fn = embed_fn
        self.n_dense = n_dense
        self.n_sparse = n_sparse
        self.n_final = n_final

    def _get_embed_fn(self):
        """延迟初始化 embedding 函数（使用 DashScope）。"""
        if self._embed_fn is not None:
            return self._embed_fn
        import dashscope
        from dashscope import TextEmbedding

        api_key = os.environ.get("ALI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
        if not api_key:
            raise RuntimeError("需要设置 ALI_API_KEY 或 DASHSCOPE_API_KEY")
        dashscope.api_key = api_key
        dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"

        def _embed(text: str) -> list[float]:
            resp = TextEmbedding.call(
                model="text-embedding-v4", input=text, dimension=1024
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Embedding error: {resp.message}")
            return resp.output["embeddings"][0]["embedding"]

        self._embed_fn = _embed
        return _embed

    def query(
        self,
        text: str,
        filter: dict | None = None,
        n_final: int | None = None,
    ) -> list[dict]:
        """
        混合检索主入口。

        返回每条结果包含：
          chunk_id, doc_id, doc_type, text, metadata,
          dense_rank, sparse_rank, rrf_score
        """
        n_out = n_final or self.n_final

        # ── Dense 检索
        embed = self._get_embed_fn()
        emb = embed(text)
        dense_results = self._dense.query(emb, n_results=self.n_dense, filter=filter)

        # ── Sparse 检索
        sparse_results = self._sparse.query(text, n_results=self.n_sparse)

        # ── RRF 融合
        rrf_scores: dict[str, dict] = {}

        for rank, r in enumerate(dense_results, start=1):
            cid = r["chunk_id"]
            if cid not in rrf_scores:
                rrf_scores[cid] = {**r, "dense_rank": rank, "sparse_rank": None, "rrf_score": 0.0}
            rrf_scores[cid]["rrf_score"] += _rrf_score(rank)
            rrf_scores[cid]["dense_rank"] = rank

        for rank, r in enumerate(sparse_results, start=1):
            cid = r["chunk_id"]
            if cid not in rrf_scores:
                rrf_scores[cid] = {**r, "dense_rank": None, "sparse_rank": rank, "rrf_score": 0.0}
            rrf_scores[cid]["rrf_score"] += _rrf_score(rank)
            rrf_scores[cid]["sparse_rank"] = rank

        # 按 RRF 分数排序，返回 top-n
        ranked = sorted(rrf_scores.values(), key=lambda x: -x["rrf_score"])
        return ranked[:n_out]

    def stats(self) -> dict:
        return {
            "dense_chunks": self._dense.count(),
            "sparse_chunks": self._sparse.count,
        }
