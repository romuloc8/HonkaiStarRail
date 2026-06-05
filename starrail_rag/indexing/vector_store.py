"""
VectorStore 抽象层 + ChromaDB 实现。

设计原则：下游（检索路由、LLM 层）只依赖 VectorStore 接口，
切换到 Qdrant 等其他后端只需替换实现类。
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from starrail_rag.indexing.chunk import Chunk

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# 抽象接口
# ──────────────────────────────────────────────────────────────────────────────

class VectorStore(ABC):
    @abstractmethod
    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """将 chunks 及其预计算的 embeddings 写入向量库。"""

    @abstractmethod
    def query(self, embedding: list[float], n_results: int = 10,
              filter: dict | None = None) -> list[dict]:
        """
        返回最相似的 chunks。
        每个结果为 dict: {chunk_id, doc_id, doc_type, text, metadata, distance}
        """

    @abstractmethod
    def count(self) -> int:
        """返回已索引的 chunk 数量。"""

    @abstractmethod
    def reset(self) -> None:
        """清空向量库（重建索引用）。"""


# ──────────────────────────────────────────────────────────────────────────────
# ChromaDB 实现
# ──────────────────────────────────────────────────────────────────────────────

class ChromaStore(VectorStore):
    """
    ChromaDB 本地向量库。

    参数
    ----
    persist_dir : 数据持久化目录
    collection  : collection 名称
    """

    def __init__(
        self,
        persist_dir: str | Path = "/workspace/output/chroma_db",
        collection: str = "starrail_lore",
    ) -> None:
        import chromadb

        self._persist_dir = str(persist_dir)
        self._collection_name = collection
        self._client = chromadb.PersistentClient(path=self._persist_dir)
        self._col = self._client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},   # 余弦相似度
        )
        logger.info(
            "ChromaStore: collection '%s' at %s (%d chunks)",
            collection, self._persist_dir, self._col.count(),
        )

    # ------------------------------------------------------------------

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        if not chunks:
            return

        # Chroma 要求 metadata 值为 str / int / float / bool
        def _sanitize(meta: dict) -> dict:
            return {
                k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                for k, v in meta.items()
                if v is not None
            }

        self._col.add(
            ids=[c.chunk_id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[_sanitize({
                **c.metadata,
                "doc_id":   c.doc_id,
                "doc_type": c.doc_type,
            }) for c in chunks],
        )

    def query(self, embedding: list[float], n_results: int = 10,
              filter: dict | None = None) -> list[dict]:
        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": min(n_results, self._col.count() or 1),
            "include": ["documents", "metadatas", "distances"],
        }
        if filter:
            kwargs["where"] = filter

        results = self._col.query(**kwargs)

        output = []
        ids        = results["ids"][0]
        docs       = results["documents"][0]
        metas      = results["metadatas"][0]
        distances  = results["distances"][0]

        for cid, text, meta, dist in zip(ids, docs, metas, distances):
            output.append({
                "chunk_id": cid,
                "doc_id":   meta.get("doc_id", ""),
                "doc_type": meta.get("doc_type", ""),
                "text":     text,
                "metadata": meta,
                "distance": dist,
                "score":    1 - dist,  # cosine distance → similarity
            })
        return output

    def count(self) -> int:
        return self._col.count()

    def reset(self) -> None:
        self._client.delete_collection(self._collection_name)
        self._col = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaStore: collection '%s' reset", self._collection_name)
