"""
BM25 Sparse 索引构建脚本。

用法：
    python3 -m starrail_rag.scripts.build_sparse_index
"""
from starrail_rag.indexing.chunker import ChunkBuilder
from starrail_rag.indexing.sparse_store import BM25Store
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")

chunks = ChunkBuilder().build_all()
BM25Store().build(chunks)
print("✓ BM25 Sparse 索引构建完成")
