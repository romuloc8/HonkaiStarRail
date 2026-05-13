"""
Indexer — 将所有 Chunk 用 BGE-M3 编码并写入 ChromaStore。

用法：
    python -m starrail_rag.indexing.indexer [--reset] [--batch-size 64]
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_ROOT   = Path("/workspace")
OUTPUT_ROOT = DATA_ROOT / "output"
CHROMA_DIR  = OUTPUT_ROOT / "chroma_db"
COLLECTION  = "starrail_lore"
BGE_MODEL   = "BAAI/bge-m3"


def run_indexing(
    reset: bool = False,
    batch_size: int = 64,
    output_root: Path = OUTPUT_ROOT,
    chroma_dir: Path = CHROMA_DIR,
) -> None:
    from sentence_transformers import SentenceTransformer
    from starrail_rag.indexing.chunker import ChunkBuilder
    from starrail_rag.indexing.vector_store import ChromaStore

    # ── 1. 加载 BGE-M3
    logger.info("Loading BGE-M3 (%s)…", BGE_MODEL)
    t0 = time.perf_counter()
    model = SentenceTransformer(BGE_MODEL)
    logger.info("BGE-M3 loaded in %.1fs", time.perf_counter() - t0)

    # ── 2. 初始化向量库
    store = ChromaStore(persist_dir=chroma_dir, collection=COLLECTION)
    if reset:
        logger.info("Resetting collection…")
        store.reset()

    already = store.count()
    logger.info("Current index size: %d chunks", already)
    if already > 0 and not reset:
        logger.info("Index already populated. Use --reset to rebuild.")
        return

    # ── 3. 构建 Chunks
    logger.info("Building chunks from %s…", output_root)
    builder = ChunkBuilder(output_root=output_root)
    chunks = builder.build_all()
    logger.info("Total chunks to index: %d", len(chunks))

    # ── 4. 批量编码 + 写入
    total = len(chunks)
    indexed = 0
    t_start = time.perf_counter()

    for i in range(0, total, batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.text for c in batch]

        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

        store.add(batch, embeddings)
        indexed += len(batch)

        elapsed = time.perf_counter() - t_start
        speed = indexed / elapsed
        remaining = (total - indexed) / speed if speed > 0 else 0
        logger.info(
            "Indexed %d/%d  (%.0f/s, ~%.0fs remaining)",
            indexed, total, speed, remaining,
        )

    elapsed = time.perf_counter() - t_start
    logger.info(
        "Indexing done: %d chunks in %.1fs (%.0f chunks/s)",
        total, elapsed, total / elapsed,
    )
    logger.info("Chroma DB persisted at: %s", chroma_dir)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Build vector index with BGE-M3 + Chroma")
    parser.add_argument("--reset", action="store_true", help="Clear and rebuild index")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    run_indexing(reset=args.reset, batch_size=args.batch_size)
