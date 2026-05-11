# 星穹铁道世界观 RAG — Book of Work

> 最后更新：2026-05-11
> 状态：设计阶段 · 未开始实现

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

### ADR-004 数据范围
**决策**：不全量处理，只处理高 lore 密度的核心表。详见「数据分级」章节。

---

## 数据分级

### 核心（必须处理）

| 文件 | 内容 | 优先级 |
|------|------|--------|
| `TextMap/TextMapCHS.json` | 所有中文字符串，Hash → 文本的源头 | P0，前置依赖 |
| `ExcelOutput/AvatarStoryConfig.json` | 角色故事，世界观密度最高 | P1 |
| `ExcelOutput/TalkSentenceConfig.json` | 全量对话（~189 万行，需筛选） | P1 |
| `ExcelOutput/EquipmentConfig.json` | 光锥描述，每个光锥含完整小故事 | P1 |
| `ExcelOutput/RelicSetConfig.json` | 遗器套装描述，历史/星神/文明碎片密度极高 | P1 |
| `ExcelOutput/ItemConfig.json`（仅 `ItemBGDesc`） | 道具背景描述，散落大量世界观线索 | P1 |
| `ExcelOutput/BookSeriesConfig.json` | 游戏内书籍/档案，最主动创作的世界观文本 | P1 |
| `ExcelOutput/MainMissionConfig.json` | 主线任务结构，提供叙事骨架 | P2 |
| `ExcelOutput/SubMissionConfig.json` | 支线任务描述 | P2 |
| `ExcelOutput/NpcConfig.json` | NPC 身份，用于对话 speaker 关联 | P2 |
| `ExcelOutput/MissionChapterConfig.json` | 章节结构，任务分组 | P2 |

### 次要（选择性处理）

| 文件 | 原因 |
|------|------|
| `ExcelOutput/MonsterConfig.json` | 少量 lore，主要是战斗属性 |
| `ExcelOutput/MazeBuffConfig.json` | 模拟宇宙祝福描述，有趣味 lore 但量大质杂 |
| `ExcelOutput/AvatarConfig.json` | 角色基础属性，辅助实体识别用 |

### 可忽略

| 范围 | 原因 |
|------|------|
| `Config/` 目录整体 | 音效路径、Shader、UI 布局、动画触发——纯技术运行时配置 |
| `Story/Mission/*.json` | 执行图（PlayTimeline 等），文本通过 TalkSentenceConfig 索引 |
| `Config/Level/Talk/` | 触发器配置（TriggerPerformance），无实际文本 |
| 所有数值计算表 | 升级曲线、掉落概率、技能倍率等 |
| `ExcelOutput/Tutorial*` | 游戏教程，纯机制说明 |
| `ExcelOutput/Activity*` | 限时活动机制，大量过期内容 |

---

## 已知技术难点

| # | 难点 | 风险等级 | 备注 |
|---|------|----------|------|
| T1 | **领域术语误识别**：「虚无」「命途」「开拓」等词在通用语料中含义不同 | 高 | 需构建领域词表注入 entity extraction prompt |
| T2 | **实体消歧（Entity Resolution）**：同一事件在不同文本里的称谓不同 | 高 | 目前无完美方案，需迭代调试 |
| T3 | **Hash Join 前置**：所有文本藏在 Hash 后，必须先建完整查找表 | 中（明确可解） | 阻塞所有后续工作 |
| T4 | **语料规模 vs 成本**：TalkSentenceConfig 近百万条，全量建图成本爆炸 | 中 | 需前置过滤层，只索引叙事性对话 |
| T5 | **文本清洗**：Layout markup tag 需清洗，条件性内容需决策处理方式 | 低 | 规则可枚举 |
| T6 | **评估困难**：无公开 benchmark，需手动构建测试集 | 中 | 必须在建系统前构建，否则无法衡量进展 |
| T7 | **Chunking 策略**：对话文本极短，角色故事极长，统一 chunk size 损失质量 | 中 | 按文本类型用不同策略 |

---

## 工作项（Book of Work）

### 阶段 0：前置条件 ✅

| ID | 工作项 | 状态 | 说明 |
|----|--------|------|------|
| W01 | **Hash Join 管线** | ✅ 完成 | `starrail_rag/core/textmap.py` — TextMapResolver，支持 uint64 hash、signed int64 fallback、xxhash 逻辑键三种解析路径 |
| W02 | **构建评估集** | ⬜ 未开始 | 手动整理 20–30 个分级问题（简单/中等/困难），含参考答案 |

### 阶段 1：数据工程（进行中）

| ID | 工作项 | 状态 | 说明 |
|----|--------|------|------|
| W03 | **开拓任务剧情提取** | ✅ 完成 | `starrail_rag/extractors/main_mission.py` — 332 个任务，196 个含对话，5698 条对话行，输出 `output/main_mission.jsonl` |
| W04 | **文本清洗层** | ✅ 完成 | `starrail_rag/core/cleaner.py` — 清洗 layout tag、unbreak、ruby、gender 条件、XML 残留标签 |
| W05 | **数据范围精确化** | ⬜ 未开始 | 继续提取：角色故事、光锥描述、遗器套装、书籍/档案 |
| W06 | **领域词表构建** | ⬜ 未开始 | 半自动提取星神名、命途名、阵营名、重要历史事件名；人工审核 |
| W07 | **文档/Chunk 数据结构定义** | ⬜ 未开始 | 确定向量库 chunk 的 metadata schema 和 chunk size 策略 |
| W08 | **Layer 1 细粒度文档构建** | ⬜ 未开始 | 按方案 B 生成带 metadata 的原始片段，写入向量库 |
| W09 | **Layer 2 实体聚合文档构建** | ⬜ 未开始 | 按方案 A 生成角色/地点/阵营的聚合文档，作为 LightRAG 建图输入 |

### 阶段 2：图构建

| ID | 工作项 | 状态 | 说明 |
|----|--------|------|------|
| W10 | **LightRAG 环境搭建** | ⬜ 未开始 | 安装配置 LightRAG，确定 embedding 模型（BGE-M3 或 OpenAI）和向量库 |
| W11 | **LightRAG 建图（核心表）** | ⬜ 未开始 | 将 Layer 2 文档注入 LightRAG，领域词表注入 extraction prompt |
| W12 | **图质量初检** | ⬜ 未开始 | 检查关键实体（主要角色、星神、阵营）是否正确识别 |

### 阶段 3：检索层

| ID | 工作项 | 状态 | 说明 |
|----|--------|------|------|
| W13 | **混合检索路由** | ⬜ 未开始 | 简单查询走向量检索；多跳/关联问题走图遍历 |
| W14 | **生成层接入** | ⬜ 未开始 | 接入 LLM（GPT-4o 或本地 Qwen），注入星铁世界观背景 |
| W15 | **端到端评估（对比 W02）** | ⬜ 未开始 | 用评估集测试，记录三级问题通过率 |

### 阶段 4：迭代优化（待定）

| ID | 工作项 | 状态 | 说明 |
|----|--------|------|------|
| W16 | **Entity Resolution 优化** | ⬜ 待定 | 针对实体消歧问题做专项优化 |
| W17 | **扩大数据范围** | ⬜ 待定 | 核心表验证通过后，考虑加入次要数据 |
| W18 | **升级至 MS GraphRAG** | ⬜ 待定 | 如需更强全局查询能力且成本可接受 |

---

## 技术栈（候选，待确认）

| 组件 | 候选方案 | 说明 |
|------|----------|------|
| GraphRAG 框架 | LightRAG | 低成本起点，ADR-003 |
| Embedding 模型 | BGE-M3 | 多语言，中文效果好，可本地运行 |
| 向量库 | Chroma（本地）或 Qdrant | Side project 优先选本地 |
| LLM（生成） | GPT-4o 或 Qwen2.5-72B | 待定 |
| 开发语言 | Python | |
| 图数据库 | LightRAG 内置（或后期迁移 Neo4j） | |

---

## 讨论记录

| 日期 | 议题 | 结论 |
|------|------|------|
| 2026-05-11 | 项目初步设计 | 明确目标为「发掘隐秘联系」，普通 RAG 不够用，需 GraphRAG |
| 2026-05-11 | 数据分级 | Config/ 和 Story/ 执行图为次要数据；遗器/光锥/书籍 lore 密度最高 |
| 2026-05-11 | 方案 A vs B | 两者各有局限，采用分层混合策略（ADR-002） |
| 2026-05-11 | 架构选型 | LightRAG 为起点（ADR-003） |
| 2026-05-11 | 优先级排序 | W01（Hash Join）和 W02（评估集）是真正的阻塞项，必须先做 |
| 2026-05-11 | 开拓任务提取实现 | W01+W03+W04 完成；TextMap 逻辑键需要 xxhash 二次解析（非直接查表）；TalkSentenceConfig 223k 条正常 json.load 约 2s；332 个 Main 任务中 196 个含对话，5698 条对话行 |
