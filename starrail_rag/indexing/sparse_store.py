"""
BM25 Sparse 索引。

使用字符 bigram 分词（无需外部分词器），天然覆盖星铁所有专有名词。
「帝弓司命」→ bigrams: {帝弓, 弓司, 司命} + unigrams: {帝, 弓, 司, 命}
"""
from __future__ import annotations

import logging
import pickle
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from starrail_rag.indexing.chunk import Chunk

logger = logging.getLogger(__name__)

BM25_PATH = Path("/workspace/output/bm25_index.pkl")


def _tokenize(text: str) -> list[str]:
    """
    字符 bigram + unigram 分词。
    中文：每个字作为 unigram，每两个相邻字作为 bigram。
    英文/数字：整词保留。
    """
    tokens: list[str] = []
    # 提取中文字符序列
    zh_segments = re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+', text)
    for seg in zh_segments:
        # unigram
        tokens.extend(seg)
        # bigram
        tokens.extend(seg[i:i+2] for i in range(len(seg) - 1))
        # trigram（提高长专有名词的匹配精度）
        tokens.extend(seg[i:i+3] for i in range(len(seg) - 2))
    # 英文/数字词
    en_words = re.findall(r'[a-zA-Z0-9Ⅰ-Ⅹ]+', text)
    tokens.extend(w.lower() for w in en_words if len(w) >= 2)
    return tokens


class BM25Store:
    """
    BM25 Sparse 索引，与 ChromaStore 配合使用。
    持久化到 pickle 文件，加载速度快（秒级）。
    """

    def __init__(self, index_path: Path = BM25_PATH) -> None:
        self._path = index_path
        self._bm25: BM25Okapi | None = None
        self._chunks: list[Chunk] = []

    def build(self, chunks: list[Chunk]) -> None:
        """从 chunk 列表构建 BM25 索引并持久化。"""
        logger.info("Building BM25 index from %d chunks…", len(chunks))
        self._chunks = chunks
        tokenized = [_tokenize(c.text) for c in chunks]
        self._bm25 = BM25Okapi(tokenized)

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "wb") as f:
            pickle.dump({"chunks": self._chunks, "bm25": self._bm25}, f)
        logger.info("BM25 index saved to %s", self._path)

    def load(self) -> None:
        """从磁盘加载已有索引。"""
        if not self._path.exists():
            raise FileNotFoundError(f"BM25 index not found: {self._path}")
        with open(self._path, "rb") as f:
            data = pickle.load(f)
        self._chunks = data["chunks"]
        self._bm25 = data["bm25"]
        logger.info("BM25 index loaded: %d chunks", len(self._chunks))

    def ensure_loaded(self) -> None:
        if self._bm25 is None:
            self.load()

    def query(self, text: str, n_results: int = 10) -> list[dict]:
        """返回 BM25 分数最高的 n 个 chunk。"""
        self.ensure_loaded()
        tokens = _tokenize(text)
        scores = self._bm25.get_scores(tokens)

        # 取 top-n
        top_indices = sorted(range(len(scores)), key=lambda i: -scores[i])[:n_results]
        return [
            {
                "chunk_id": self._chunks[i].chunk_id,
                "doc_id":   self._chunks[i].doc_id,
                "doc_type": self._chunks[i].doc_type,
                "text":     self._chunks[i].text,
                "metadata": self._chunks[i].metadata,
                "bm25_score": float(scores[i]),
                "rank":     rank + 1,
            }
            for rank, i in enumerate(top_indices)
            if scores[i] > 0  # 过滤掉分数为 0 的（完全无关）
        ]

    @property
    def count(self) -> int:
        self.ensure_loaded()
        return len(self._chunks)
