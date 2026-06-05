"""
Indexer — 将所有 Chunk 编码并写入 ChromaStore。

支持的 Embedding 后端（通过 --backend 指定）：
  dashscope  — 阿里云 text-embedding-v4（推荐，中文优化，8192 token）
  openai     — OpenAI text-embedding-3-small（备选）
  bge        — 本地 BGE-M3（原定计划，需 GPU 或接受慢速 CPU）

环境变量：
  DASHSCOPE_API_KEY   — 阿里云 DashScope key
  OPENAI_API_KEY      — OpenAI key

用法：
    python -m starrail_rag.indexing.indexer --backend dashscope [--reset]
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

DATA_ROOT   = Path("/workspace")
OUTPUT_ROOT = DATA_ROOT / "output"
CHROMA_DIR  = OUTPUT_ROOT / "chroma_db"
COLLECTION  = "starrail_lore"


# ──────────────────────────────────────────────────────────────────────────────
# Embedding 后端工厂
# ──────────────────────────────────────────────────────────────────────────────

def _make_dashscope_encoder(batch_size: int = 10) -> Callable[[list[str]], list[list[float]]]:
    """DashScope text-embedding-v4（支持国际版/中国大陆版）。"""
    import dashscope
    from dashscope import TextEmbedding

    api_key = os.environ.get("ALI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("请设置 ALI_API_KEY 或 DASHSCOPE_API_KEY 环境变量")

    dashscope.api_key = api_key
    # 国际版（新加坡等）使用 dashscope-intl 端点
    dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"

    def encode(texts: list[str]) -> list[list[float]]:
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = TextEmbedding.call(
                model="text-embedding-v4",
                input=batch,
                dimension=1024,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"DashScope error {resp.status_code}: {resp.message}")
            embeddings.extend([e["embedding"] for e in resp.output["embeddings"]])
            if i + batch_size < len(texts):
                time.sleep(0.05)
        return embeddings

    return encode


def _make_openai_encoder(batch_size: int = 100) -> Callable[[list[str]], list[list[float]]]:
    """OpenAI text-embedding-3-small（备选）。"""
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 未设置")
    client = OpenAI(api_key=api_key)

    def encode(texts: list[str]) -> list[list[float]]:
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = client.embeddings.create(
                model="text-embedding-3-small",
                input=batch,
            )
            embeddings.extend([d.embedding for d in resp.data])
        return embeddings

    return encode


def _make_bge_encoder(batch_size: int = 16) -> Callable[[list[str]], list[list[float]]]:
    """本地 BGE-M3（原定计划，CPU 上约 5 chunk/min）。"""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("BAAI/bge-m3")

    def encode(texts: list[str]) -> list[list[float]]:
        return model.encode(
            texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False
        ).tolist()

    return encode


BACKEND_FACTORIES = {
    "dashscope": _make_dashscope_encoder,
    "openai":    _make_openai_encoder,
    "bge":       _make_bge_encoder,
}

BACKEND_CHUNK_SIZES = {
    "dashscope": 10,    # DashScope API 单批上限 10 条
    "openai":    100,
    "bge":       16,
}


# ──────────────────────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────────────────────

def run_indexing(
    backend: str = "dashscope",
    reset: bool = False,
    output_root: Path = OUTPUT_ROOT,
    chroma_dir: Path = CHROMA_DIR,
) -> None:
    from starrail_rag.indexing.chunker import ChunkBuilder
    from starrail_rag.indexing.vector_store import ChromaStore

    batch_size = BACKEND_CHUNK_SIZES[backend]
    logger.info("Initializing %s encoder (batch_size=%d)…", backend, batch_size)
    encode = BACKEND_FACTORIES[backend](batch_size)

    store = ChromaStore(persist_dir=chroma_dir, collection=COLLECTION)
    if reset:
        logger.info("Resetting collection…")
        store.reset()

    already = store.count()
    logger.info("Already indexed: %d chunks", already)

    logger.info("Building chunks…")
    builder = ChunkBuilder(output_root=output_root)
    all_chunks = builder.build_all()
    total = len(all_chunks)

    if reset:
        chunks = all_chunks
    elif already > 0:
        # 断点续传：跳过已索引的 chunk_id
        logger.info("Resuming — fetching existing IDs…")
        existing_ids = set(store._col.get(include=[])["ids"])
        chunks = [c for c in all_chunks if c.chunk_id not in existing_ids]
        logger.info("Remaining: %d / %d chunks", len(chunks), total)
    else:
        chunks = all_chunks

    if not chunks:
        logger.info("Nothing to index.")
        return

    logger.info("Indexing %d chunks…", len(chunks))

    indexed = 0
    t_start = time.perf_counter()

    for i in range(0, total, batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c.text for c in batch]
        embeddings = encode(texts)
        store.add(batch, embeddings)
        indexed += len(batch)
        elapsed = time.perf_counter() - t_start
        speed = indexed / elapsed if elapsed > 0 else 0
        remaining = (total - indexed) / speed if speed > 0 else 0
        logger.info(
            "Indexed %d/%d  (%.1f/s, ~%.0fs remaining)",
            indexed, total, speed, remaining,
        )

    elapsed = time.perf_counter() - t_start
    logger.info("Done: %d chunks in %.1fs (%.1f/s)", total, elapsed, total / elapsed)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="dashscope",
                        choices=["dashscope", "openai", "bge"],
                        help="Embedding backend (default: dashscope)")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    run_indexing(backend=args.backend, reset=args.reset)
