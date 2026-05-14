# 待解决问题与解决方案记录

> 最后更新：2026-05-12
> 状态：数据工程完成，向量化准备阶段

---

## 背景

当前完成状态：
- 数据提取全部完成（wiki 剧情、角色故事、光锥、遗器、书籍、道具描述）
- 统一实体生成管线（entity_pipeline.py）正在运行（预计今早完成）
- 关系带有时间锚点（15 个命名锚点，epoch_titan → arc_post_main）

待进入阶段：向量化（W07/W08）→ LightRAG 建图（W10/W11）→ 检索层（W12/W13）

---

## 一、实体数据问题

### 1.1 关系动词不规范（P0 — 必须解决）

**问题描述**  
同一语义的关系被 DeepSeek 用不同英文动词表达，导致图中同类关系被识别为不同类型：
```
member_of / belongs_to / affiliated_with / serves / part_of
located_in / situated_in / resides_in / lives_in / from / originates_from
contains / has_member / includes / comprises
```

**解决方案**  
1. 从 `entities.json` 提取所有唯一的 `{source_type, relation_verb, target_type}` 三元组，附带出现频次
2. 将三元组表发给 DeepSeek，要求按语义分组并为每组给出规范动词
3. 人工审查分组结果（注意：同一动词在不同类型上下文下可能语义不同）
4. 生成 `normalization_map.json`，应用到 `entities.json` → `entities_normalized.json`

**依赖**  entity_pipeline.py 跑完  
**优先级** 进入 LightRAG 建图之前必须完成

---

### 1.2 `attributes` 字段在非种子实体中为空

**问题描述**  
可玩角色（如希儿、景元）的 `attributes.path/element/rarity` 应来自 AvatarConfig，但目前合并逻辑存在 bug（可能因 canonical 名字格式不匹配导致 key miss），导致这些字段为空。

**解决方案**  
管线跑完后，验证具体是否有 bug：
```python
# 检查已知角色的 attributes 是否正确
e = next(x for x in entities if x['canonical'] == '希儿')
assert e['attributes']['path'] == '毁灭'
```
如有问题，修复 merge() 函数的 key 归一化逻辑。

**优先级** P1 — 影响质量但不阻塞向量化  
**注意** LightRAG 从文本 description 工作，不依赖结构化 attributes，影响有限

---

### 1.3 同一事实的多条重复关系

**问题描述**  
同一实体对的同一语义关系，在不同批次被重复提取并用不同动词表达：
```json
// 贝洛伯格实体中，指向阿尔乔姆的关系有 5 条，
// 全部表达「阿尔乔姆来自贝洛伯格」
located_in / member_of / origin_of / from / home_of
```

**解决方案**  
完成 1.1（关系动词规范化）后，自然会合并同类动词；再对 `(source, relation_canonical, target)` 三元组去重。不需要额外步骤。

**优先级** P2 — 1.1 完成后自动解决

---

### 1.4 `source_hint` 字段为空

**问题描述**  
DeepSeek 提取的实体没有继承来源文档信息，`source_hint` 全为空字符串。

**解决方案**  
后续需要溯源时，可通过 `entity_pipeline_raw.jsonl` 中的 `batch_idx` 反查原始文档。暂不修复，优先级低。

**优先级** P2 — 暂不处理

---

## 二、向量化前置问题

### 2.1 Embedding 模型未选定（阻塞向量化）

**问题描述**  
模型选择影响：chunk size 上限、向量维度、检索质量、成本。

**候选方案对比**

| | BGE-M3（本地） | OpenAI text-embedding-3-small |
|--|--|--|
| 最大 token | 512 | 8192 |
| 成本 | 免费 | 付费 |
| 中文质量 | 优秀 | 良好 |
| 需要 GPU | 推荐（CPU 可跑但慢） | 否 |
| 向量维度 | 1024 | 1536 |

**待决策**  ⬜ 需要用户确认  
**影响** 直接决定 chunking 策略的 token 上限

---

### 2.2 Chunking 策略未定义（阻塞向量化）

**问题描述**  
不同文档类型需要不同的切分策略，且依赖 2.1 的模型选择。

**设计方案（待确认）**

| 文档类型 | 策略 | 理由 |
|---------|------|------|
| `wiki_mission.jsonl`（最大489行） | 按 `###` 小节标题切分，overlap 2-3行 | 场景边界是自然切点 |
| `book.jsonl`（50-3000字不等） | 按段落切，超过阈值再切，overlap 1段 | 保留叙事连贯性 |
| `character_story.jsonl`（5-6段） | 每段一个 chunk | 每段独立叙事单元 |
| `relic_set.jsonl`（4-6件描述） | 整套为一个 chunk | 套装描述是整体 |
| `item_lore.jsonl`（1-3句） | 考虑按类别批量合并 | 单独 embed 太短，信号弱 |

**待决策**  ⬜ 需要用户确认 token 上限后设计

---

### 2.3 wiki_mission.jsonl 存在重复内容

**问题描述**  
同名任务（如「漩涡止于中心」1000201-1000204）对应同一 wiki 页面，内容完全相同，向量化后会造成同内容过度召回。

**解决方案**  
向量化前，按 `wiki_url` 去重，保留最小 `mission_id` 的那条：
```python
seen_urls = set()
deduped = []
for doc in wiki_mission_docs:
    url = doc['metadata']['wiki_url']
    if url not in seen_urls:
        seen_urls.add(url)
        deduped.append(doc)
```
预计去重后从 299 条降至约 180-200 条（减少约 30%）。

**优先级** 向量化前完成，工作量小

---

### 2.4 现有 JSONL 未经最新清洗规则处理

**问题描述**  
`wiki_mission.jsonl` 和 `wiki_category.jsonl` 是在新清洗规则添加之前生成的，仍可能含有：
- `{NICKNAME}` 原文占位符（应替换为「开拓者」）
- `'''加粗文字'''` wiki 格式标记
- `{F#少女}{M#少年}` 性别条件标记

**解决方案**  
向量化前对所有 JSONL 重跑清洗层（直接在内存中处理，不需要重新抓取）：
```bash
python3 -m starrail_rag.cli --extractors wiki_mission  # 重新跑（耗时约5分钟）
# 或者：直接对 JSONL 批量应用 CleaningPipeline
```

**优先级** 向量化前完成

---

### 2.5 Entity-chunk 关联元数据

**问题描述**  
向量库的每个 chunk 缺少「哪些实体出现在这段文本里」的元数据，导致：
- 无法做实体过滤查询（「找所有提到银鬃铁卫的段落」）
- LightRAG 图检索和向量检索之间缺少连接维度

**解决方案**  
chunking 时，对每个 chunk 做简单的实体匹配（用 entities.json 的 canonical + aliases 做字符串匹配），将命中的实体 canonical 名加入 metadata：
```python
chunk_metadata = {
    "entities_mentioned": ["银鬃铁卫", "贝洛伯格", "杰帕德"],
    ...
}
```

**优先级** P1 — 影响检索质量，但不阻塞向量化本身

---

## 三、架构决策待确认

### 3.1 向量库选型

**候选**：Chroma（本地）或 Qdrant（更完整）  
**待决策** ⬜ 需要用户确认

### 3.2 Collection 设计

是否按文档类型分 collection，还是所有文档混在一个 collection 用 metadata 过滤？

**倾向**：单一 collection + 丰富 metadata，避免跨 collection 查询复杂性  
**待决策** ⬜

---

## 四、执行顺序

```
当前（管线运行中）
  ↓
① entity_pipeline.py 跑完 → entities.json

② 关系动词规范化（1.1）
   提取三元组 → DeepSeek 分组 → 人工审查 → normalization_map.json
   → entities_normalized.json

③ 向量化前置清理
   - wiki_mission / wiki_category 去重（2.3）
   - 重跑清洗层（2.4）

④ 确认 Embedding 模型（2.1）
   ← 需要用户决策

⑤ 设计并实现 Chunk Builder（2.2）
   ← 依赖 ④

⑥ 向量库索引（W08）

⑦ LightRAG 建图（W10/W11）
   使用 entities_normalized.json 注入 extraction prompt

⑧ 检索层 + 生成层（W12/W13）

⑨ 构建评估集 + 端到端测试（W02/W15）
```

---

## 五、已确定的设计决策

| 决策 | 结论 | 记录日期 |
|------|------|---------|
| 剧情数据来源 | wiki 替代游戏数据（wiki 更完整，含 CG 台词）| 2026-05-11 |
| 关系时间模型 | 命名锚点（15个）+ position (before/during/after/spanning) | 2026-05-11 |
| 关系动词规范化方式 | 提取 {type, verb, type} 三元组集合 → DeepSeek 分组 | 2026-05-12 |
| 实体别称分层 | `aliases`（全局唯一）+ `context_aliases`（上下文相关）| 2026-05-11 |
| 语言 | 仅简体中文（TextMapCHS）| 2026-05-11 |
| GraphRAG 框架 | LightRAG 为起点 | 2026-05-11 |

---

*本文件记录设计讨论中的问题与方案，随项目推进持续更新。*

---

## 未来迭代问题：时间建模精度（暂不解决）

**问题描述**（2026-05-14 讨论）

当前时间锚点（15 个命名锚点 + before/during/after/spanning）颗粒度太粗，存在以下问题：

1. **历法多样性**：不同文明有不同历法（琥珀纪、光历等），相对时间表述（「二十年前」）的参照物不明确
2. **时间框架嵌套**：翁法罗斯在帝皇权杖内的模拟时间与外部时间流速不同，且涉及多次轮回（同一事件在不同循环有不同状态）
3. **精度层级差异**：精确时间点 vs 大致时代 vs 大致时段，当前模型无法区分
4. **可信度差异**：正史记载 vs 民间传说 vs 书籍作者观点，当前模型不区分

**潜在解决方向**（按性价比排序）

A. 加 `reliability` 字段（高价值，低成本）：区分 confirmed / legend / speculation

B. 加 `raw_evidence` 字段（高价值，低成本）：保存原文时间表述，查询时 LLM 直接读原文推理

C. 多维度时间对象（完整方案，高成本）：calendar_system, approximate_distance, precision, simulation_layer, cycle_context 等

D. 轮回上下文专项标注（翁法罗斯专项，中成本）

**不建议做的**：强行统一所有历法到单一绝对时间轴——游戏刻意模糊这些，归一化会产生虚假精度。

**建议下次迭代先做**：A（reliability）+ B（raw_evidence），改动小，对 Hard 题推理质量帮助最大。
