"""
LightRAG 知识图谱构建器。

工作流：
  1. 准备 entity hints：从 entities.json 提取 canonical + aliases → 注入 extraction prompt
  2. 配置 LightRAG：
       LLM       = deepseek-chat（entity extraction）
       Embedding = DashScope text-embedding-v4（与 Chroma 一致）
  3. 插入对话场景文档（4,444 chunks，补充 lore 未覆盖的剧情关系）
  4. 查询时 deepseek-reasoner 用于 Hard 题生成

运行：
    python -m starrail_rag.lightrag_builder

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
from functools import partial

import numpy as np
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache
from lightrag.utils import EmbeddingFunc

logger = logging.getLogger(__name__)

WORK_DIR   = Path("/workspace/output/lightrag_db")
DATA_ROOT  = Path("/workspace")
OUTPUT_ROOT = DATA_ROOT / "output"


# ──────────────────────────────────────────────────────────────────────────────
# LLM 函数（DeepSeek，OpenAI 兼容接口）
# ──────────────────────────────────────────────────────────────────────────────

def _make_deepseek_llm(model: str = "deepseek-chat"):
    """返回 LightRAG 兼容的 async LLM 函数。"""
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
# Embedding 函数（DashScope text-embedding-v4）
# ──────────────────────────────────────────────────────────────────────────────

def _make_dashscope_embedding():
    """返回 LightRAG 兼容的 async embedding 函数。"""
    import dashscope
    from dashscope import TextEmbedding

    api_key = os.environ.get("ALI_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("ALI_API_KEY 未设置")

    dashscope.api_key = api_key
    dashscope.base_http_api_url = "https://dashscope-intl.aliyuncs.com/api/v1"

    async def embed_func(texts: list[str]) -> np.ndarray:
        # DashScope 批次上限 10
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
# Entity hints 提取（从 entities.json）
# ──────────────────────────────────────────────────────────────────────────────

def _build_entity_hints(entities_path: Path) -> str:
    """
    从 entities.json 提取规范名称 + 别称，生成注入 extraction prompt 的提示文本。
    格式：每行「规范名（别称1/别称2）: 类型」
    """
    with open(entities_path, encoding="utf-8") as f:
        data = json.load(f)

    lines = []
    for e in data["entities"]:
        canonical = e["canonical"]
        aliases = e.get("aliases", [])
        etype = e.get("type", "concept")
        if aliases:
            alias_str = "/".join(aliases[:4])  # 最多4个别称，避免 prompt 太长
            lines.append(f"{canonical}（{alias_str}）: {etype}")
        else:
            lines.append(f"{canonical}: {etype}")

    hint_text = "\n".join(lines)
    logger.info("Entity hints: %d entities", len(lines))
    return hint_text


# ──────────────────────────────────────────────────────────────────────────────
# 准备对话文档（只处理对话 chunk，lore 已有 entities.json）
# ──────────────────────────────────────────────────────────────────────────────

def _load_dialogue_chunks(output_root: Path) -> list[str]:
    """
    加载对话场景文档文本。
    只处理 main_story / companion / continuance / adventure / activity，
    不处理 lore（已通过 entities.json 覆盖）。
    每个 chunk 的文本拼接任务标题 + 对话内容，方便 LightRAG 识别上下文。
    """
    dialogue_dirs = ["main_story", "companion", "continuance", "adventure", "activity"]
    texts: list[str] = []

    for subdir in dialogue_dirs:
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
                    scene = meta.get("scene_title", "")

                    header = f"【{chapter}·{mission}·{scene}】\n" if (chapter or mission) else ""
                    body = "\n".join(
                        f"{d['speaker']}：{d['text']}" if d.get("speaker")
                        else d["text"]
                        for d in dialogues
                    )
                    texts.append(header + body)

    logger.info("Dialogue texts to insert: %d", len(texts))
    return texts


# ──────────────────────────────────────────────────────────────────────────────
# 主构建流程
# ──────────────────────────────────────────────────────────────────────────────

async def build_graph(
    work_dir: Path = WORK_DIR,
    output_root: Path = OUTPUT_ROOT,
    llm_model: str = "deepseek-chat",
    max_parallel: int = 2,
    resume: bool = True,
) -> LightRAG:
    work_dir.mkdir(parents=True, exist_ok=True)

    # Entity hints
    entities_path = output_root / "entities.json"
    entity_hints = _build_entity_hints(entities_path)

    # LLM：在 system prompt 里注入 entity hints
    system_prompt_with_hints = (
        "你是崩坏：星穹铁道世界观的专业分析师，负责从游戏文本中提取实体和关系。\n"
        "以下是已知的核心实体（请使用这些规范名称，不要重复创建）：\n\n"
        f"{entity_hints}\n\n"
        "请严格按照要求的 JSON 格式输出，不要输出其他内容。"
    )

    llm_func = _make_deepseek_llm(model=llm_model)
    embed_func = _make_dashscope_embedding()

    async def llm_with_hints(prompt, system_prompt=None, keyword_extraction=False, **kwargs):
        # ── 关键词提取模式：LightRAG 1.4.x 使用 Pydantic beta.parse()，DeepSeek 不支持。
        #    改用 json_object 模式并手动构造返回对象。
        if keyword_extraction:
            import json as _json
            from lightrag.types import GPTKeywordExtractionFormat
            from openai import AsyncOpenAI
            _client = AsyncOpenAI(
                api_key=os.environ.get("HSR_DEEPSEEK_API_KEY"),
                base_url="https://api.deepseek.com",
            )
            msgs = []
            if system_prompt:
                msgs.append({"role": "system", "content": system_prompt})
            msgs.append({"role": "user", "content": prompt})
            _resp = await _client.chat.completions.create(
                model=llm_model,
                messages=msgs,
                response_format={"type": "json_object"},
                max_tokens=512,
                temperature=0,
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

        # ── 普通调用：注入 entity hints 到 system prompt
        merged_system = system_prompt_with_hints
        if system_prompt:
            merged_system = system_prompt_with_hints + "\n\n" + system_prompt
        return await llm_func(prompt, system_prompt=merged_system, **kwargs)

    rag = LightRAG(
        working_dir=str(work_dir),
        llm_model_func=llm_with_hints,
        llm_model_name=llm_model,
        embedding_func=embed_func,
        embedding_batch_num=10,
        llm_model_max_async=max_parallel,
        chunk_token_size=1200,
        chunk_overlap_token_size=100,
        max_extract_input_tokens=16000,
        entity_extract_max_gleaning=1,
        enable_llm_cache=True,
        enable_llm_cache_for_entity_extract=True,
    )

    await rag.initialize_storages()

    logger.info("LightRAG initialized at %s", work_dir)
    return rag


async def insert_documents(
    rag: LightRAG,
    output_root: Path = OUTPUT_ROOT,
    batch_size: int = 20,
) -> None:
    """将对话 chunk 批量插入 LightRAG。"""
    texts = _load_dialogue_chunks(output_root)
    total = len(texts)
    logger.info("Inserting %d dialogue texts into LightRAG…", total)

    for i in range(0, total, batch_size):
        batch = texts[i:i+batch_size]
        await rag.ainsert(batch)
        logger.info("Inserted %d/%d", min(i+batch_size, total), total)


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
    await insert_documents(rag)
    logger.info("LightRAG graph build complete!")

    # 快速验证
    test_query = "卡芙卡和银狼的关系是什么"
    logger.info("Test query: %s", test_query)
    result = await rag.aquery(test_query, param=QueryParam(mode="local"))
    print("\n=== 测试查询结果 ===")
    print(result[:500])


if __name__ == "__main__":
    asyncio.run(main())
