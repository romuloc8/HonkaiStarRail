# 星穹铁道世界观 RAG — Book of Work

> 最后更新：2026-05-11
> 状态：数据工程阶段完成，准备进入向量化与建图阶段

---

## 项目目标

基于本仓库（Honkai: Star Rail 游戏元数据）构建一个**星穹铁道世界观 RAG 系统**，核心能力不是简单问答，而是：

- **连接零散文本**，在不同来源的碎片之间发现隐性关联
- **发掘隐秘信息**，找到单独看不出意义、但联系起来有价值的线索
- 支持中文查询与中文输出（语料以 `TextMapCHS` 为准）

非目标：商业化、实时性、多语言。这是一个 side project。

---

## 架构决策记录（ADR）

### ADR-001 语言策略
**决策**：仅使用简体中文（`TextMapCHS.json`）。  
**原因**：游戏原文为中文，英文翻译有信息损失，中文 embedding 模型（如 BGE-M3）现已成熟。

### ADR-002 存储层策略（双层）
**决策**：分层混合方案。

| 层 | 内容 | 用途 |
|----|------|------|
| Layer 1（细粒度） | 方案 B：原始叙事片段 + metadata | 精确检索、来源引用 |
| Layer 2（粗粒度） | 方案 A：实体聚合文档 | GraphRAG 建图输入、社区摘要 |
| Layer 3（图层） | 知识图谱 | 多跳推理、隐性关联发现 |

**原因**：方案 A 单独用时跨实体关系失效；方案 B 单独用时孤立碎片丢失上下文。两者互补，图层解决它们共同的盲区。

### ADR-003 GraphRAG 框架选型
**决策**：以 **LightRAG** 为起点。  
**原因**：语料静态（版本更新才变化），索引成本是一次性的。LightRAG 在同等语料下成本约为 Microsoft GraphRAG 的 1/100，质量达到 70–90%，增量更新简单。后期如需全局查询能力可升级至 MS GraphRAG。

### ADR-005 剧情数据来源
**决策**：游戏数据仅用于静态 lore（角色故事、光锥、遗器、书籍、道具）；剧情对话全部从 **BiliWiki** 抓取。  
**原因**：游戏 dump 中 CG 场景台词存储在 `.playable` Unity Timeline 二进制文件中，不在 JSON dump 里；wiki 已有完整转录，且包含所有分支选项文本。

### ADR-006 数据清洗规范
**决策**：统一清洗规则如下：
- `{NICKNAME}` → `开拓者`
- 性别条件 `{F#...}{M#...}` → 保留女性（F#）表述（少女/她）
- 分支对话：响应相同则合并选项；响应不同则平行保留所有分支
- 移除所有标签：layout、unbreak、ruby、rich-text、wiki markup、XML 残留

### ADR-007 实体消歧策略
**决策**：两步走——第一步手工+半自动建领域词表；第二步（待定）用 DeepSeek 发现隐喻性别称。  
**不修改原始文本**，在 LightRAG entity extraction prompt 中注入词表，图层天然归一化。

---

## 已提取数据总览

| 文件 | 类型 | 文档数 | 对话行数 | 来源 |
|------|------|--------|---------|------|
| `output/wiki_mission.jsonl` | 开拓主线剧情 | 299 | 69,537 | BiliWiki |
| `output/wiki_category.jsonl` | 同行/续闻/冒险/活动任务 | 280 | 24,764 | BiliWiki |
| `output/character_story.jsonl` | 角色故事 | 82 | — | 游戏数据 |
| `output/light_cone.jsonl` | 光锥描述 | 161 | — | 游戏数据 |
| `output/relic_set.jsonl` | 遗器套装描述 | 56 | — | 游戏数据 |
| `output/book.jsonl` | 游戏内书籍/档案 | 1,018 | — | 游戏数据 |
| `output/item_lore.jsonl` | 道具背景描述 | 2,058 | — | 游戏数据 |
| `output/domain_lexicon.json` | 领域词表 | 126 实体 | — | 半自动+手工 |
| **合计** | | **3,954 文档** | **94,301 对话行** | |

---

## 已知技术难点

| # | 难点 | 风险等级 | 当前状态 |
|---|------|----------|---------|
| T1 | **领域术语误识别**：「虚无」「命途」「开拓」等词含义多义 | 高 | ✅ 领域词表已构建，待注入 extraction prompt |
| T2 | **实体消歧（Entity Resolution）**：同一实体有多种称谓 | 高 | 🔄 词表第一步完成，DeepSeek 扩展待定 |
| T3 | **Hash Join 前置** | 中 | ✅ 已解决 |
| T4 | **语料规模 vs 成本** | 中 | ✅ 已通过 wiki 抓取绕过此问题 |
| T5 | **文本清洗** | 低 | ✅ 已实现完整清洗管线 |
| T6 | **评估困难**：无公开 benchmark | 中 | ⬜ 待构建评估集 |
| T7 | **Chunking 策略** | 中 | ⬜ 待设计 |

---

## 工作项（Book of Work）

### 阶段 0：前置条件 ✅

| ID | 工作项 | 状态 | 说明 |
|----|--------|------|------|
| W01 | **Hash Join 管线** | ✅ 完成 | `starrail_rag/core/textmap.py` — 三种 hash 解析路径 |
| W02 | **构建评估集** | ⬜ 未开始 | 需用户手动整理 20–30 个分级问题（简单/中等/困难）含参考答案 |

### 阶段 1：数据工程 ✅

| ID | 工作项 | 状态 | 说明 |
|----|--------|------|------|
| W03 | **开拓主线剧情提取（wiki 场景级）** | ✅ 完成 | 2,564 场景，75,495 行，24 章，`output/main_story/` |
| W04 | **文本清洗层** | ✅ 完成 | `starrail_rag/core/cleaner.py` |
| W05 | **静态 lore 数据提取** | ✅ 完成 | 角色故事、光锥、遗器、书籍、道具，`output/lore/` |
| W05b | **更多任务类型提取（wiki 场景级）** | ✅ 完成 | 同行/续闻/冒险/活动，`output/companion/` 等 |
| W06 | **实体知识图谱生成** | ✅ 完成 | `entity_pipeline.py`（优化版 v2），3,428 实体，7,320 关系 |
| W07 | **Chunk Builder** | ✅ 完成 | `starrail_rag/indexing/chunker.py`，7,819 chunks |
| W08 | **向量库索引（Dense + Sparse）** | ✅ 完成 | Chroma + BM25，DashScope text-embedding-v4 |

### 阶段 2：图构建

| ID | 工作项 | 状态 | 说明 |
|----|--------|------|------|
| W10 | **LightRAG 环境搭建** | ✅ 完成 | lightrag-hku 1.4.16，`starrail_rag/lightrag_builder.py` |
| W11 | **LightRAG 建图** | 🔄 75%（1,669节点/2,368边）| 对话 chunk 注入，entities.json 作 entity hints |
| W12 | **混合检索路由** | ✅ 完成 | `starrail_rag/retrieval/router.py`，SIMPLE/COMPLEX/GLOBAL |

### 阶段 3：检索层

| ID | 工作项 | 状态 | 说明 |
|----|--------|------|------|
| W13 | **LLM 生成层** | ✅ 完成 | `starrail_rag/retrieval/query_engine.py`，deepseek-chat/reasoner |
| W15 | **端到端评估** | ⬜ 待执行 | 30 题评估集，等 LightRAG 完成后运行 |

### 阶段 4：迭代优化（待定）

| ID | 工作项 | 状态 | 说明 |
|----|--------|------|------|
| W16 | **语义层实体去重（BGE-M3）** | ⬜ 待定 | 与下次向量化合并执行 |
| W17 | **时间建模精度提升** | ⬜ 待定 | reliability + raw_evidence 字段，见 PENDING_ISSUES.md |
| W18 | **Sparse 召回改善（BM25 已有）** | ⬜ 待定 | 如需 ColBERT，需 GPU 运行 BGE-M3 |

---

## 技术栈

| 组件 | 选型 | 状态 |
|------|------|------|
| 数据提取框架 | `starrail_rag`（自建） | ✅ |
| GraphRAG 框架 | LightRAG（lightrag-hku 1.4.16） | ✅ 建图中 75% |
| Embedding 模型 | DashScope text-embedding-v4（dense）+ BM25 bigram（sparse）| ✅ |
| 向量库 | Chroma（本地，7,819 chunks）| ✅ |
| LLM（生成） | DeepSeek-chat（简单/提取）+ DeepSeek-reasoner（复杂推理）| ✅ |
| 实体知识图谱 | `output/entities.json`（3,428 实体，temporal anchors）| ✅ |
| 开发语言 | Python 3.12 | ✅ |

---

## 讨论记录

| 日期 | 议题 | 结论 |
|------|------|------|
| 2026-05-11 | 项目初步设计 | 明确目标为「发掘隐秘联系」，普通 RAG 不够用，需 GraphRAG |
| 2026-05-11 | 数据分级 | Config/ 和 Story/ 执行图为次要数据；遗器/光锥/书籍 lore 密度最高 |
| 2026-05-11 | 方案 A vs B | 两者各有局限，采用分层混合策略（ADR-002） |
| 2026-05-11 | 架构选型 | LightRAG 为起点（ADR-003） |
| 2026-05-11 | 游戏数据对话不完整 | 改用 wiki 作为对话来源（ADR-005） |
| 2026-05-11 | 数据清洗规范 | {NICKNAME}→开拓者；分支对话按响应是否一致决定合并或平行展示（ADR-006） |
| 2026-05-11 | 实体消歧策略 | 不修改原文；建领域词表注入 LightRAG prompt；DeepSeek 扩展（ADR-007） |
| 2026-05-12 | Embedding 模型选型 | DashScope text-embedding-v4；8192 token，优化中文，BGE-M3 CPU 太慢放弃 |
| 2026-05-12 | Sparse 检索 | BM25 字符 bigram，用 RRF 与 Dense 融合，作为 ColBERT 替代 |
| 2026-05-13 | 实体管线优化（v2） | 游戏属性作 DeepSeek 提取上下文；DeepSeek 直接分类 alias 类型 |
| 2026-05-13 | 时间建模粒度 | 当前 15 named anchors 已够用；future：reliability + raw_evidence 字段 |
| 2026-05-13 | LightRAG 策略 | entities.json 注入作 hints；LightRAG 自建对话关系图；不重复提取 lore |
| 2026-05-14 | HybridRetriever + QueryEngine | SIMPLE→Chroma+BM25；COMPLEX/GLOBAL→LightRAG；生成层接 deepseek-chat/reasoner |
| 2026-05-15 | 脚本模块化修复 | scripts/__init__.py 不再自动导入各脚本，改用按需运行，避免 import 时触发 API 调用 |
