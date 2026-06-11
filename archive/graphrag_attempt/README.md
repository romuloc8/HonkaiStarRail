# GraphRAG Attempt — Archive

> 归档时间：2026-06-11  
> 归档原因：架构调整——从 GraphRAG 转向 Agent 工作流

---

## 这里存放了什么

### 背景

项目初期选择了 GraphRAG（基于 LightRAG）的架构，目标是通过构建知识图谱来实现星铁 lore 的隐性连接发现。在经历了完整的实施周期后，决定转向更简单、推理能力更强的 Agent 工作流架构。

### 归档内容

#### `code/` — GraphRAG 相关代码

| 文件 | 说明 |
|------|------|
| `lightrag_builder.py` | LightRAG 知识图谱构建器（串行插入，max_async=2）|
| `scripts/check_lightrag_progress.py` | LightRAG 建图进度检查脚本 |
| `scripts/dedup_entity_names.py` | 实体名称去重脚本（旧管线，已被新 entity_pipeline.py 覆盖）|

#### `data/` — 中间处理产物

| 文件 | 说明 |
|------|------|
| `merge_candidates.json` | 实体合并候选对（基于启发式规则预生成）|
| `normalization_map.json` | 关系动词归一化映射表 |
| `normalization_groups.json` | 关系动词分组 |
| `deepseek_merge_suggestions.json` | DeepSeek 实体名称合并建议（基于全量名称列表）|
| `all_entity_names.txt` | 所有实体规范名称的平铺列表 |

#### `data/legacy_format/` — 旧格式数据（已被场景级文件取代）

| 文件 | 说明 |
|------|------|
| `wiki_mission.jsonl` | 旧格式：按任务级别的对话文档（已被 `output/main_story/` 场景级文件取代）|
| `wiki_category.jsonl` | 旧格式：分类任务对话文档（已被 `output/companion/` 等取代）|

---

## 为什么改变方向

### 主要问题

1. **建图速度极慢**：LightRAG 串行建图花了近两周，最终只覆盖 23% 的源内容（ch01-ch09）
2. **数据质量问题**：知识图谱实体验证发现 184 个问题，包括：
   - 关系方向完全反向（药师 `worships→仙舟联盟`，实际应为 `hunted_by`）
   - 幻觉关系（克里珀 `worships→胖子拉里`）
   - 错误的令使归属
3. **GraphRAG 实际贡献为零**：Phase 1 评估显示，Easy(88%)/Medium(83%) 的成绩来自简单向量搜索，复杂查询因 LightRAG keyword_extraction bug 全部 fallback 到 Hybrid，GraphRAG 未贡献任何提升
4. **维护成本高**：复杂的 schema → 复杂的提取 → 复杂的验证，形成无限循环

### 新架构方向

**Agent 工作流 + 迭代检索**：
- 向量知识库（Chroma + BM25）保持不变，作为检索基础
- 去掉知识图谱层
- 添加 ReAct 风格的推理 Agent：检索 → 推理 → 识别缺口 → 再检索 → 生成答案
- 利用 DeepSeek-reasoner 的推理能力代替图遍历

---

## 如何重启 GraphRAG（如果未来需要）

如果未来决定重试 GraphRAG，参考以下改进点：

1. **使用并行插入**：参考 `lightrag_builder_v2.py`（已在 PR #3 schema-upgrade 分支中）
2. **先补全数据再建图**：用 `entity_attribute_enricher.py` 补全 entities.json 属性后再运行
3. **从匹诺康尼之后的内容开始**：ch01-ch09 的内容已覆盖，从 ch10 开始继续
4. **关注 keyword_extraction 兼容性**：DeepSeek 不支持 Pydantic beta.parse()，需要 json_object fallback（修复代码已在 `lightrag_builder.py` 中）
