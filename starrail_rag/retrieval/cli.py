"""
查询 CLI — 交互式测试入口。

用法：
    python -m starrail_rag.retrieval.cli
    python -m starrail_rag.retrieval.cli --query "卡芙卡的命途是什么"
    python -m starrail_rag.retrieval.cli --mode complex --query "饮月之乱的经过"
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os

from starrail_rag.retrieval.router import QueryMode
from starrail_rag.retrieval.query_engine import QueryEngine


async def run_query(query: str, mode: str | None = None, verbose: bool = False):
    engine = QueryEngine(
        deepseek_key=os.environ.get("HSR_DEEPSEEK_API_KEY"),
        ali_key=os.environ.get("ALI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY"),
    )

    force_mode = QueryMode(mode) if mode else None
    result = await engine.query(query, force_mode=force_mode)

    print(f"\n{'='*60}")
    print(f"查询: {result.query}")
    print(f"模式: {result.mode.value}  |  模型: {result.llm_model}")
    print(f"{'='*60}")
    print(result.answer)

    if verbose and result.sources:
        print(f"\n--- 检索来源 ({len(result.sources)} 条) ---")
        for i, s in enumerate(result.sources[:5], 1):
            meta = s.get("metadata", {})
            src = meta.get("mission_title") or meta.get("lore_title", "")
            score = s.get("rrf_score", s.get("score", 0))
            print(f"  {i}. [{score:.4f}] {src}: {s['text'][:80]}…")

    if result.error:
        print(f"\n[ERROR] {result.error}")


async def interactive_loop():
    print("崩坏：星穹铁道 RAG 系统")
    print("输入问题查询，输入 'exit' 退出")
    print("前缀 /simple /complex /global 可强制指定模式\n")

    engine = QueryEngine(
        deepseek_key=os.environ.get("HSR_DEEPSEEK_API_KEY"),
        ali_key=os.environ.get("ALI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY"),
    )

    while True:
        try:
            raw = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw or raw.lower() == "exit":
            break

        force_mode = None
        query = raw
        for prefix, mode in [("/simple", QueryMode.SIMPLE), ("/complex", QueryMode.COMPLEX), ("/global", QueryMode.GLOBAL)]:
            if raw.startswith(prefix):
                force_mode = mode
                query = raw[len(prefix):].strip()
                break

        if not query:
            continue

        result = await engine.query(query, force_mode=force_mode)
        print(f"\n[{result.mode.value}] {result.llm_model}")
        print(result.answer)


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", "-q", type=str, default=None)
    parser.add_argument("--mode",  "-m", type=str, default=None, choices=["simple", "complex", "global"])
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.query:
        asyncio.run(run_query(args.query, mode=args.mode, verbose=args.verbose))
    else:
        asyncio.run(interactive_loop())
