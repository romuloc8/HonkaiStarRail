# 数据处理工作流文档（目标版本）

> 最后更新：2026-05-13
> 阶段：数据工程完成，向量化准备就绪

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

## 关键文件索引

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
