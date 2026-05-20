# 数据处理工作流文档（目标版本）

> 最后更新：2026-05-15
> 阶段：**检索层完成（W07-W13 ✅）**，LightRAG 建图进行中（75%），待评估（W15）

本文档描述**目标工作流**——经过讨论优化后的理想流程，用于未来重建时参考。
当前实际执行过程及历史优化记录见 `WORKFLOW_OPTIMIZATION_LOG.md`。

---

## 1. 语料数据结构

### 1.1 输入数据目录

```
output/
├── main_story/                    # 开拓主线，按章节分 24 个文件
│   ├── 01_今天是昨天的明天.jsonl
│   ├── 07_喧哗与骚动.jsonl        # 匹诺康尼
│   ├── 13_落木逐火英雄纪.jsonl    # 翁法罗斯
│   ├── 21_欢迎来到乐园.jsonl      # 二相乐园
│   └── ...（共 24 个）
├── companion/                     # 同行任务，按角色分文件（共 21 个）
├── continuance/                   # 开拓续闻，按星球分文件（共 4 个）
├── adventure/                     # 冒险任务，按星球分文件（共 6 个）
├── activity/                      # 活动任务，按大版本分文件（共 5 个）
└── lore/                          # 静态 lore
    ├── books.jsonl
    ├── character_stories.jsonl
    ├── relic_sets.jsonl
    ├── light_cones.jsonl
    └── item_lore.jsonl
```

### 1.2 场景文档结构

每条文档代表一个**场景**（wiki `===小节===` 级别），是最小的语义完整单元：

```python
{
  "doc_id":    str,   # "main_mission_scene_{mission_id}_{scene_idx:03d}"
  "doc_type":  str,   # "main_mission_scene" | "companion_scene" | ...
  "title":     str,   # 场景标题（来自 wiki === 标题 ===）
  "dialogues": [
    {"sentence_id": int, "speaker": str, "text": str}
  ],
  "metadata": {
    "source": "wiki", "category": str, "mission_title": str,
    "chapter_name": str, "scene_title": str, "scene_index": int,
    "wiki_url": str, "sentence_count": int
  }
}
```

---

## 2. 数据清洗（语料准备）

**顺序**：先清洗，再生成实体。

### 2.1 wiki 内容去重

同名任务按 `wiki_url` 去重，保留 `mission_id` 最小的条目（同一 wiki 页面对应多个 mission_id 的情况）。

### 2.2 文本清洗管线（`CleaningPipeline`）

`starrail_rag/core/cleaner.py`，应用顺序：

| 规则 | 处理 |
|------|------|
| `nickname` | `{NICKNAME}` → `开拓者` |
| `layout_tags` | `{LAYOUT_X#文字}` → `文字` |
| `unbreak_tags` | `<unbreak>N</unbreak>` → `N` |
| `ruby_annotations` | `{RUBY_B#...}文字{RUBY_E}` → `文字` |
| `gender_tags` | `{F#少女}{M#少年}` → `少女`（保留 F# 形式）|
| `rich_text_tags` | `<size=N>` `<align=>` `<br/>→换行` 等 |
| `wiki_markup` | `'''加粗'''` `''斜体''` |
| `remaining_xml` | 残余 XML/HTML 标签 |
| `curly_placeholders` | 残余 `{...}` 占位符 |
| `normalise_whitespace` | 折叠多余空白 |

### 2.3 分支对话展开规则

- 所有分支 NPC 响应相同 → `开拓者：选项A / 选项B` + 单份 NPC 响应
- 各分支响应不同 → 每个分支完整保留

---

## 3. 实体知识图谱生成管线

**入口**：`starrail_rag/tools/entity_pipeline.py`

### 阶段设计

```
Phase 1  上下文准备
  从游戏结构化数据提取角色/星神/命途的技术属性表
  （命途、元素、稀有度等）
  → 作为背景知识注入 Phase 2 的 prompt 上下文
  → 不生成独立实体，仅提供属性补全依据

Phase 2  DeepSeek 一体化提取
  输入：lore 文本（按批次）+ Phase 1 属性表（背景上下文）
  输出：实体列表，每个实体包含：
    - canonical（规范名）
    - type
    - description（20-50字）
    - attributes（从属性表补全）
    - aliases（已分类：全局唯一 vs 上下文相关，由 DeepSeek 直接判断）
    - relations（带时间锚点）

Phase 3  序列化
  → entities.json（含时间锚点表）
```

### Phase 2 DeepSeek Prompt 契约

**System Prompt**（完整版见 `WORKFLOW_OPTIMIZATION_LOG.md` 历史版本）：

```
实体类型：character | aeon | path | faction | location | event | concept

时间锚点（必须使用以下 id 之一）：
  epoch_titan, epoch_xianzhou_founding, event_jimu, event_buliren,
  event_yinyue, event_belo_isolation, era_kakavasha,
  arc_main_110, arc_main_belobog, arc_main_luofu, arc_main_penacony,
  arc_main_amphoreus, arc_main_paradise, arc_post_main, unknown

别称分类规则（由 DeepSeek 直接判断）：
  aliases        → 全局唯一，任何地方出现都指向此实体
  context_aliases → 上下文相关（代词、泛化词等）
```

**输出 Schema**：

```json
{
  "canonical": "规范名称",
  "type": "类型",
  "description": "20-50字描述",
  "attributes": {"path": "...", "element": "...", "rarity": "..."},
  "aliases": ["全局唯一别称"],
  "context_aliases": [{"text": "别称", "context": "适用场景"}],
  "relations": [
    {
      "target": "目标实体",
      "relation": "动词",
      "temporal_anchor": "锚点id",
      "temporal_position": "before|during|after|spanning",
      "note": "说明"
    }
  ]
}
```

**调用参数**：`model=deepseek-chat, temperature=0.1, max_tokens=2000, batch=6docs/批`

---

## 4. 实体数据结构

**文件**：`output/entities.json`

```json
{
  "version": "3.x",
  "temporal_anchors": [...],
  "entities": [
    {
      "canonical":          str,
      "type":               "character|aeon|path|faction|location|event|concept",
      "description":        str,
      "attributes":         {"path": str, "element": str, "rarity": str},
      "aliases":            [str],
      "context_aliases":    [{"text": str, "context": str}],
      "known_relations":    [{"target": str, "relation": str,
                              "temporal": {"anchor": str, "position": str},
                              "note": str}],
      "source_hint":        str,
      "mention_count":      int,
      "disambiguation_note": str
    }
  ]
}
```

时间锚点定义见 `starrail_rag/tools/temporal_anchors.py`。

---

## 5. 实体清理

### 5.1 系列文档自动归并

识别 `其一/其二/上/下/卷N/第N章` 等模式，将系列子实体内容归并到父实体：

```
《帝弓迹躔歌》注疏 其一~五  →  《帝弓迹躔歌》注疏
科员们的留言便条 其一~六     →  科员们的留言便条
```

### 5.2 实体去重

**名称层（DeepSeek 直接处理）**

将所有实体名称列表一次性发给 DeepSeek（~13k tokens，一次调用），
直接识别可合并的名称对（标点差异、全名/简称、同名变体等）。
无需启发式规则预筛选。

Prompt：
```
你是崩坏：星穹铁道专家。请找出可以合并的实体对（标点差异/全名简称/同人不同称谓）。
输出 JSON：[{"keep": "保留名", "merge": ["合并名"], "reason": "原因"}]
```

**语义层（BGE-M3 + DeepSeek，与向量化阶段合并执行）**

1. BGE-M3 对所有实体 description 生成嵌入
2. 余弦相似度筛选候选对（600 万对 → 数百对）
3. DeepSeek 逐对验证

### 5.3 关系动词规范化

将自由动词映射到 18 个规范动词组（见 `output/normalization_map.json`）。

Prompt：
```
Group these knowledge graph verbs by semantics.
Output JSON: [{"canonical": "verb", "variants": ["v1", "v2"]}]
```

---

## 6. 待完成工作

| 工作项 | ID | 状态 | 依赖 |
|--------|-----|------|------|
| BM25 Sparse 索引 + HybridRetriever | — | ✅ 完成 | W08 ✅ |
| LightRAG 建图 | W10/W11 | 🔄 75%（1,669节点/2,368边）| W07 ✅, W08 ✅ |
| 混合检索路由 | W12 | ✅ 完成 | — |
| LLM 生成层 | W13 | ✅ 完成 | W12 ✅ |
| 端到端评估 | W15 | ⬜ 待执行 | W02 ✅（评估集）, LightRAG 完成 |

## 7. 向量化管线（W07/W08）

### 7.1 Chunk Builder

**入口**：`starrail_rag/indexing/chunker.py`，`ChunkBuilder` 类

各文档类型的切分策略（基于 8192 token 上限）：

| 文档类型 | 策略 | 说明 |
|---------|------|------|
| 对话场景（main_story / companion 等）| 场景整体为一个 chunk | 已是最小语义单元，平均 235 字符 |
| `lore/books.jsonl` | 按 `\n\n` 段落切，overlap 1 段 | 部分书籍超 3000 字，需切分 |
| `lore/character_stories.jsonl` | 按段落（`\n\n`）切 | 每段独立叙事 |
| `lore/relic_sets.jsonl` | 整套一个 chunk | 已足够小 |
| `lore/light_cones.jsonl` | 整条一个 chunk | |
| `lore/item_lore.jsonl` | 整条一个 chunk（1-3 句）| |

Chunk 数据结构：
```python
Chunk(
    chunk_id  = "chunk_{doc_id}_{index}",
    doc_id    = str,
    doc_type  = str,
    text      = str,   # 实际用于 embedding 的文本
    metadata  = dict,  # doc_type, chapter_name, mission_title 等，用于过滤
)
```

### 7.2 Dense 向量索引（Chroma + DashScope）

**入口**：`python -m starrail_rag.indexing.indexer --backend dashscope`

| 参数 | 值 |
|------|-----|
| Embedding 模型 | `text-embedding-v4`（阿里云 DashScope）|
| 向量维度 | 1024 |
| 相似度函数 | 余弦相似度 |
| 向量库 | Chroma（本地持久化，`output/chroma_db/`）|
| 批次大小 | 10 条/批（DashScope API 上限）|
| 端点 | `dashscope-intl.aliyuncs.com`（国际版/新加坡）|
| 环境变量 | `ALI_API_KEY` 或 `DASHSCOPE_API_KEY` |
| 总 chunk 数 | 7,819 |

**重建命令**：
```bash
# 全量重建（清空后重建）
python -m starrail_rag.indexing.indexer --backend dashscope --reset

# 断点续传（从中断处继续）
python -m starrail_rag.indexing.indexer --backend dashscope

# 切换到其他 backend
python -m starrail_rag.indexing.indexer --backend openai    # OpenAI text-embedding-3-small
python -m starrail_rag.indexing.indexer --backend bge       # 本地 BGE-M3（需 GPU）
```

### 7.3 Sparse 索引（BM25，待实现）

Dense 检索存在**专有名词语义漂移**问题：查询「帝弓司命」时可能因语义泛化返回所有「星神」相关内容，而不是精确包含「帝弓司命」的 chunk。

解决方案：并行建 BM25 Sparse 索引，用 **Reciprocal Rank Fusion（RRF）** 合并两路结果。

```
Dense 召回（语义）+ BM25 召回（关键词精确匹配）
            ↓ RRF 融合
        最终召回结果
```

**分词策略**：字符 bigram（无需分词器，天然覆盖所有游戏专有名词）
- `帝弓司命` → `{帝弓, 弓司, 司命}` bigram token 集合
- 无 OOV 问题，永远能正确处理新出现的专有名词

**与 ColBERT 的关系**：ColBERT（BGE-M3 第三种检索模式）需要本地运行 BGE-M3，当前因 CPU 性能限制暂不引入。Dense + BM25 混合已覆盖 ColBERT 90% 的场景价值。

### 7.4 向量化相关文件

| 文件 | 说明 |
|------|------|
| `starrail_rag/indexing/chunk.py` | Chunk 数据模型 |
| `starrail_rag/indexing/chunker.py` | Chunk Builder（切分逻辑）|
| `starrail_rag/indexing/vector_store.py` | VectorStore 接口 + ChromaStore 实现 |
| `starrail_rag/indexing/indexer.py` | 编排：切分→embedding→写入 Chroma |
| `output/chroma_db/` | Chroma 持久化数据（不提交 git，可重建）|

| 工作项 | ID | 依赖 |
|--------|-----|------|
| 语义层实体去重（BGE-M3） | Step2 | W08 向量化 |
| Chunk Builder 设计与实现 | W07 | 无 |
| 向量库索引 | W08 | W07 |
| LightRAG 建图 | W10/W11 | W07, W08 |
| 混合检索路由 | W12 | W10 |
| 生成层接入 | W13 | W12 |
| 端到端评估 | W15 | W02（评估集），W13 |

---

## 8. LightRAG 知识图谱（W10/W11）

**入口**：`python -m starrail_rag.lightrag_builder`
**工作目录**：`output/lightrag_db/`（不提交 git，可重建）

### 8.1 设计决策

| 决策 | 说明 |
|------|------|
| 处理文档 | 仅对话场景（4,444 chunks），lore 已由 entities.json 覆盖 |
| Entity hints | 将 3,428 个实体的规范名 + 别称注入 extraction system prompt |
| LLM | deepseek-chat（实体抽取）|
| Embedding | DashScope text-embedding-v4（与 Chroma 一致）|
| LLM cache | 开启，相同 chunk 不重复调用 |

### 8.2 Entity Hints 注入格式

每个实体以一行格式注入 system prompt（最多 4 个别称）：
```
卡芙卡（雷电妖姬/戴墨镜的女人）: character
岚（巡猎星神）（帝弓司命/巡猎之眼）: aeon
仙舟「罗浮」（仙舟罗浮/罗浮）: location
```

### 8.3 查询模式

| 模式 | 适用场景 | LightRAG 参数 |
|------|---------|--------------|
| `local` | 多跳推理、关系分析 | `QueryParam(mode="local")` |
| `global` | 主题综合、全局摘要 | `QueryParam(mode="global")` |

### 8.4 重建命令

```bash
python -m starrail_rag.lightrag_builder
```

---

## 9. 混合检索路由（W12）+ LLM 生成层（W13）

**入口**：`starrail_rag/retrieval/`

### 9.1 查询路由

```
用户查询
    ↓ 规则分类（无 API 成本）
    ├── SIMPLE  → HybridRetriever（Dense + BM25 RRF）→ deepseek-chat
    ├── COMPLEX → LightRAG local search               → deepseek-chat
    └── GLOBAL  → LightRAG global search              → deepseek-reasoner

SIMPLE:  短查询（≤30字）+ 无复杂关键词
COMPLEX: 含「为什么/原因/历史/关系变化/隐秘」等 13 个模式
GLOBAL:  含「总结/概述/综合/整体/全部」等
Fallback: LightRAG 不可用时自动使用 HybridRetriever
```

### 9.2 使用方式

```bash
# 交互式
python3 -m starrail_rag.retrieval.cli

# 单次查询
python3 -m starrail_rag.retrieval.cli -q "帝弓司命是谁" --verbose

# 强制模式
python3 -m starrail_rag.retrieval.cli -q "贝洛伯格封闭的原因" -m complex
```

Python API：

```python
from starrail_rag.retrieval.query_engine import QueryEngine
import asyncio

engine = QueryEngine()
result = asyncio.run(engine.query("帝弓司命是谁"))
print(result.answer)
# result.mode, result.sources, result.llm_model 也可访问
```

### 9.3 关键文件

| 文件 | 说明 |
|------|------|
| `starrail_rag/retrieval/router.py` | 查询分类规则 |
| `starrail_rag/retrieval/query_engine.py` | 统一查询入口 |
| `starrail_rag/retrieval/cli.py` | CLI 入口 |
| `starrail_rag/lightrag_builder.py` | LightRAG 初始化 + 文档插入 |

| 文件 | 说明 |
|------|------|
| `starrail_rag/core/cleaner.py` | 文本清洗管线 |
| `starrail_rag/core/models.py` | 数据模型 |
| `starrail_rag/extractors/wiki_scene.py` | 主线场景级爬取 |
| `starrail_rag/extractors/wiki_category_scene.py` | 分类任务场景级爬取 |
| `starrail_rag/tools/entity_pipeline.py` | 实体生成管线 |
| `starrail_rag/tools/temporal_anchors.py` | 时间锚点定义 |
| `output/entities.json` | 实体知识图谱 |
| `output/normalization_map.json` | 关系动词规范化映射 |
| `output/deepseek_merge_suggestions.json` | 名称层去重建议 |
| `starrail_rag/eval_set.json` | 30 题评估集 |
| `PENDING_ISSUES.md` | 待解决问题清单 |
| `WORKFLOW_OPTIMIZATION_LOG.md` | 工作流演进历史 |
| `RAG_BOOK_OF_WORK.md` | 项目工作项追踪 |
