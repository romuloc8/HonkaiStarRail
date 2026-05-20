"""
LightRAG 知识图谱构建器 — v2（并行插入优化版）

与 v1 的关键差异：
  1. 并行插入：asyncio.Semaphore 控制并发数，不再等每批处理完才提交下一批
  2. max_async 从 2 提升到 16，充分利用 DeepSeek API 并发限制
  3. 智能 chunk_token_size：降到 600（减少每次合并代价）
  4. DeepSeek keyword_extraction 兼容修复（json_object 代替 beta.parse）
  5. 失败自动重试（单文档级，3 次）
  6. 进度持久化：每 50 文档写一次 checkpoint 文件

预期性能提升：
  v1：~5 天/1000 文档（max_async=2，串行批次）
  v2：~8-12 小时/4444 文档（max_async=16，并行提交）

运行（等 v1 进程结束后再执行）：
    python -m starrail_rag.lightrag_builder_v2

环境变量：
    HSR_DEEPSEEK_API_KEY   — DeepSeek API key
    ALI_API_KEY            — DashScope API key
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

import numpy as np
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache
from lightrag.utils import EmbeddingFunc

logger = logging.getLogger(__name__)

WORK_DIR    = Path("/workspace/output/lightrag_db")
OUTPUT_ROOT = Path("/workspace/output")
CHECKPOINT  = Path("/workspace/output/lightrag_v2_checkpoint.json")


# ──────────────────────────────────────────────────────────────────────────────
# LLM（DeepSeek，兼容 keyword_extraction 结构化输出）
# ──────────────────────────────────────────────────────────────────────────────

def _make_deepseek_llm(model: str = "deepseek-chat"):
    api_key = os.environ.get("HSR_DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("HSR_DEEPSEEK_API_KEY 未设置")

    async def llm_func(prompt, system_prompt=None, history_messages=None, **kwargs):
        return await openai_complete_if_cache(
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            history_messages=history_messages or [],
            base_url="https://api.deepseek.com",
            api_key=api_key,
            **kwargs,
        )
    return llm_func


# ──────────────────────────────────────────────────────────────────────────────
# Embedding（DashScope text-embedding-v4）
# ──────────────────────────────────────────────────────────────────────────────

def _make_dashscope_embedding():
    import dashscope
    from dashscope import TextEmbedding

    api_key = os.environ.get("ALI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("ALI_API_KEY 未设置")

    dashscope.api_key = api_key
    dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"

    async def embed_func(texts: list[str]) -> np.ndarray:
        all_embeddings = []
        for i in range(0, len(texts), 10):
            batch = texts[i:i+10]
            resp = TextEmbedding.call(
                model="text-embedding-v4",
                input=batch,
                dimension=1024,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"DashScope embedding error: {resp.message}")
            all_embeddings.extend([e["embedding"] for e in resp.output["embeddings"]])
        return np.array(all_embeddings, dtype=np.float32)

    return EmbeddingFunc(
        embedding_dim=1024,
        max_token_size=8192,
        func=embed_func,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Entity hints
# ──────────────────────────────────────────────────────────────────────────────

def _build_entity_hints(entities_path: Path) -> str:
    with open(entities_path, encoding="utf-8") as f:
        data = json.load(f)
    lines = []
    for e in data["entities"]:
        canonical = e["canonical"]
        aliases = e.get("aliases", [])
        etype = e.get("type", "concept")
        if aliases:
            lines.append(f"{canonical}（{'/'.join(aliases[:3])}）: {etype}")
        else:
            lines.append(f"{canonical}: {etype}")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# 对话文档加载（全量）
# ──────────────────────────────────────────────────────────────────────────────

def _load_dialogue_texts(output_root: Path) -> list[str]:
    dirs = ["main_story", "companion", "continuance", "adventure", "activity"]
    texts: list[str] = []

    for subdir in dirs:
        dir_path = output_root / subdir
        if not dir_path.exists():
            continue
        for jsonl_file in sorted(dir_path.glob("*.jsonl")):
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    doc = json.loads(line.strip())
                    dialogues = doc.get("dialogues", [])
                    if not dialogues:
                        continue
                    meta = doc.get("metadata", {})
                    chapter = meta.get("chapter_name", "")
                    mission = meta.get("mission_title", doc.get("title", ""))
                    scene   = meta.get("scene_title", "")
                    header  = f"【{chapter}·{mission}·{scene}】\n" if (chapter or mission) else ""
                    body    = "\n".join(
                        f"{d['speaker']}：{d['text']}" if d.get("speaker") else d["text"]
                        for d in dialogues
                    )
                    texts.append(header + body)

    logger.info("总对话文档数: %d", len(texts))
    return texts


# ──────────────────────────────────────────────────────────────────────────────
# 检查点（resume）
# ──────────────────────────────────────────────────────────────────────────────

def _load_checkpoint() -> set[int]:
    if CHECKPOINT.exists():
        data = json.load(open(CHECKPOINT))
        done = set(data.get("done_indices", []))
        logger.info("从检查点恢复：已完成 %d 个文档", len(done))
        return done
    return set()


def _save_checkpoint(done_indices: set[int]):
    CHECKPOINT.write_text(
        json.dumps({"done_indices": sorted(done_indices)}, indent=2)
    )


# ──────────────────────────────────────────────────────────────────────────────
# 主构建流程
# ──────────────────────────────────────────────────────────────────────────────

async def build_graph(
    work_dir:    Path = WORK_DIR,
    output_root: Path = OUTPUT_ROOT,
    llm_model:   str  = "deepseek-chat",
    max_async:   int  = 16,   # v1=2 → v2=16
) -> LightRAG:
    work_dir.mkdir(parents=True, exist_ok=True)

    entity_hints = _build_entity_hints(output_root / "entities.json")
    system_prompt_with_hints = (
        "你是崩坏：星穹铁道世界观的专业分析师，负责从游戏文本中提取实体和关系。\n"
        "以下是已知的核心实体（请使用这些规范名称，不要重复创建）：\n\n"
        f"{entity_hints}\n\n"
        "请严格按照要求的 JSON 格式输出，不要输出其他内容。"
    )

    llm_func = _make_deepseek_llm(model=llm_model)
    embed_func = _make_dashscope_embedding()
    api_key = os.environ.get("HSR_DEEPSEEK_API_KEY")

    async def llm_with_hints(prompt, system_prompt=None, keyword_extraction=False, **kwargs):
        # ── keyword_extraction：DeepSeek 不支持 Pydantic beta.parse()，改用 json_object
        if keyword_extraction:
            import json as _json
            from lightrag.types import GPTKeywordExtractionFormat
            from openai import AsyncOpenAI
            _client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            msgs = []
            if system_prompt:
                msgs.append({"role": "system", "content": system_prompt})
            msgs.append({"role": "user", "content": prompt})
            _resp = await _client.chat.completions.create(
                model=llm_model, messages=msgs,
                response_format={"type": "json_object"},
                max_tokens=512, temperature=0,
            )
            raw = _resp.choices[0].message.content or "{}"
            try:
                data = _json.loads(raw)
            except Exception:
                data = {}
            return GPTKeywordExtractionFormat(
                high_level_keywords=data.get("high_level_keywords", []),
                low_level_keywords=data.get("low_level_keywords", []),
            )

        # ── 普通调用：注入 entity hints
        merged = system_prompt_with_hints
        if system_prompt:
            merged = system_prompt_with_hints + "\n\n" + system_prompt
        return await llm_func(prompt, system_prompt=merged, **kwargs)

    rag = LightRAG(
        working_dir=str(work_dir),
        llm_model_func=llm_with_hints,
        llm_model_name=llm_model,
        embedding_func=embed_func,
        embedding_batch_num=10,
        llm_model_max_async=max_async,          # 关键提升：16 并发
        chunk_token_size=600,                   # 关键提升：更小 chunk = 更小合并代价
        chunk_overlap_token_size=50,
        max_extract_input_tokens=12000,
        entity_extract_max_gleaning=1,
        enable_llm_cache=True,
        enable_llm_cache_for_entity_extract=True,
    )

    await rag.initialize_storages()
    logger.info("LightRAG v2 初始化完成（max_async=%d, chunk_size=600）", max_async)
    return rag


async def insert_documents_parallel(
    rag:          LightRAG,
    output_root:  Path = OUTPUT_ROOT,
    max_parallel: int  = 8,    # 同时进行 insert 的文档数
    retry:        int  = 3,
) -> None:
    """
    并行插入对话文档。
    
    与 v1 的关键差异：
    - v1：await ainsert(batch_of_20) → 等待整批完成 → 下一批（纯串行）
    - v2：所有文档同时提交，Semaphore 限制最大并发数，各自独立处理
    
    每个 ainsert([single_text]) 调用在 LightRAG 内部异步处理：
    - 独立的实体提取（不阻塞其他文档）
    - 合并阶段使用 LightRAG 内部的 entity_lock（自动防止写冲突）
    """
    texts      = _load_dialogue_texts(output_root)
    done_set   = _load_checkpoint()
    total      = len(texts)
    remaining  = [i for i in range(total) if i not in done_set]
    sem        = asyncio.Semaphore(max_parallel)
    lock       = asyncio.Lock()
    counter    = {"done": len(done_set), "failed": 0}

    logger.info("待插入: %d / %d（已从检查点跳过 %d）", len(remaining), total, len(done_set))

    async def insert_one(idx: int) -> None:
        async with sem:
            for attempt in range(1, retry + 1):
                try:
                    await rag.ainsert(texts[idx])
                    async with lock:
                        done_set.add(idx)
                        counter["done"] += 1
                        if counter["done"] % 50 == 0:
                            _save_checkpoint(done_set)
                            logger.info(
                                "进度: %d/%d (%.1f%%) — 失败: %d",
                                counter["done"], total,
                                counter["done"] / total * 100,
                                counter["failed"],
                            )
                    return
                except Exception as e:
                    if attempt == retry:
                        logger.warning("文档 %d 最终失败: %s", idx, e)
                        async with lock:
                            counter["failed"] += 1
                    else:
                        await asyncio.sleep(2 ** attempt)  # 指数退避

    tasks = [insert_one(i) for i in remaining]
    await asyncio.gather(*tasks)
    _save_checkpoint(done_set)
    logger.info(
        "插入完成：成功 %d / 失败 %d / 总计 %d",
        counter["done"] - counter["failed"],
        counter["failed"],
        total,
    )


# ──────────────────────────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────────────────────────

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    rag = await build_graph()
    await insert_documents_parallel(rag, max_parallel=8)
    logger.info("LightRAG v2 建图完成！")

    result = await rag.aquery("卡芙卡和银狼的关系是什么", param=QueryParam(mode="local"))
    print("\n=== 测试查询结果 ===")
    print(result[:500] if result else "(空)")


if __name__ == "__main__":
    asyncio.run(main())
