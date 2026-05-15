"""
向量索引验证脚本：检查 Chroma + BM25 是否就绪。

用法：
    python3 -m starrail_rag.scripts.verify_index
"""
from pathlib import Path


def main():
    CHROMA_DIR = Path("output/chroma_db")
    BM25_PATH  = Path("output/bm25_index.pkl")

    print("=== 向量索引状态 ===")

    if CHROMA_DIR.exists():
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        col = client.get_collection("starrail_lore")
        print(f"✓ Chroma Dense:  {col.count():,} chunks")
    else:
        print("✗ Chroma Dense:  未建立（运行 indexer --backend dashscope --reset）")

    if BM25_PATH.exists():
        from starrail_rag.indexing.sparse_store import BM25Store
        store = BM25Store()
        store.load()
        print(f"✓ BM25 Sparse:   {store.count:,} chunks")
    else:
        print("✗ BM25 Sparse:   未建立（运行 build_sparse_index）")


if __name__ == "__main__":
    main()
