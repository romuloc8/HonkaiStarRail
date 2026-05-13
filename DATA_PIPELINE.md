# 数据处理工作流文档

> 最后更新：2026-05-13
> 阶段：数据工程完成，向量化准备就绪

本文档记录从原始提取数据到可用于 GraphRAG 的结构化数据集的完整处理流程，**不包含数据提取部分**（wiki 爬取、游戏数据解析见 `RAG_BOOK_OF_WORK.md`）。

---

## 1. 输入数据

处理流程的起点是以下目录结构，每个 `.jsonl` 文件的每行一个场景/文档对象：

```
output/
├── main_story/                    # 开拓主线，按章节分 24 个文件
│   ├── 01_今天是昨天的明天.jsonl
│   ├── 07_喧哗与骚动.jsonl        # 匹诺康尼
│   ├── 13_落木逐火英雄纪.jsonl    # 翁法罗斯
│   ├── 21_欢迎来到乐园.jsonl      # 二相乐园
│   └── ...（共 24 个）
├── companion/                     # 同行任务，按角色分文件
│   ├── 卡芙卡.jsonl
│   ├── 希儿.jsonl
│   └── ...（共 21 个）
├── continuance/                   # 开拓续闻，按星球分文件
│   ├── 雅利洛-Ⅵ.jsonl
│   └── ...（共 4 个）
├── adventure/                     # 冒险任务，按星球分文件（共 6 个）
├── activity/                      # 活动任务，按大版本分文件
│   ├── 1_x.jsonl, 2_x.jsonl ...（共 5 个）
└── lore/                          # 静态 lore（不拆分，整体较小）
    ├── books.jsonl                # 游戏内书籍/档案
    ├── character_stories.jsonl    # 角色故事
    ├── relic_sets.jsonl           # 遗器套装描述
    ├── light_cones.jsonl          # 光锥描述
    └── item_lore.jsonl            # 道具背景描述
```

### 文档数据结构（Scene Document）

```python
{
  "doc_id":       str,   # 唯一标识符，如 "main_mission_scene_1010902_003"
  "doc_type":     str,   # "main_mission_scene" | "companion_scene" | ...
  "title":        str,   # 场景标题（来自 wiki === 小节标题 ===）
  "dialogues": [
    {
      "sentence_id": int,  # 负数为 wiki 来源（无 game sentence id）
      "speaker":     str,  # 说话人（空字符串为旁白）
      "text":        str   # 台词正文（已清洗）
    }
  ],
  "metadata": {
    "source":          "wiki",
    "category":        str,    # "同行任务" | "开拓续闻" | ...
    "mission_title":   str,    # 所属任务名称
    "chapter_name":    str,    # 所属章节（主线专有）
    "scene_title":     str,    # 场景小节标题
    "scene_index":     int,    # 场景在任务内的序号
    "wiki_url":        str,
    "sentence_count":  int
  }
}
```

---

## 2. 数据清洗（向量化前置）

所有数据源在进入后续流程前均需经过清洗，清洗包含两个层次：

### 2.1 文本清洗（`CleaningPipeline`）

**入口**：`starrail_rag/core/cleaner.py`

| 规则 | 处理内容 | 示例 |
|------|---------|------|
| `nickname` | `{NICKNAME}` → `开拓者` | |
| `layout_tags` | `{LAYOUT_X#文字}` → `文字` | |
| `unbreak_tags` | `<unbreak>N</unbreak>` → `N` | |
| `ruby_annotations` | `{RUBY_B#...}文字{RUBY_E}` → `文字` | |
| `gender_tags` | `{F#少女}{M#少年}` → `少女`（保留 F# 形式）| |
| `rich_text_tags` | `<size=N>` `<align=...>` `<br/>→换行` 等 | |
| `wiki_markup` | `'''加粗'''` `''斜体''` | |
| `remaining_xml` | 残余 XML/HTML 标签 | |
| `curly_placeholders` | 残余 `{...}` 占位符 | |
| `normalise_whitespace` | 折叠多余空白/换行 | |

### 2.2 wiki 对话分支处理

`{{剧情选项}}` 模板按以下规则展开：

- **所有分支 NPC 响应相同** → 合并选项：`开拓者：选项A / 选项B / 选项C` + 单份 NPC 响应
- **各分支 NPC 响应不同** → 每个分支完整保留（选项文本 + 对应 NPC 响应）

### 2.3 wiki_mission 去重

同名任务（如「漩涡止于中心」对应多个 mission_id 但同一 wiki 页面）按 `wiki_url` 去重，保留 `mission_id` 最小的条目。

**注意**：此步骤属于语料准备阶段，应在实体知识图谱生成之前完成。

---

## 3. 实体知识图谱生成管线

**入口**：`starrail_rag/tools/entity_pipeline.py`

### 当前管线设计（现状）

```
Phase 1  种子提取
  AvatarConfig + RogueAeonDisplay + AvatarBaseType
  → 102 个种子实体（角色/星神/命途的结构化属性）

Phase 2  DeepSeek 丰富
  lore 文本 → deepseek-chat
  → 实体描述、别称、带时间锚点的关系

Phase 3  合并
  种子 + DeepSeek 结果 → 按 canonical 去重合并

Phase 4  别称过滤（启发式规则）
  代词/泛化名词 → context_aliases
  全局唯一别称 → aliases

Phase 5  序列化 → entities.json
```

### 待优化设计（方向）

Phase 1 的种子实体价值在于结构化属性（命途/属性/稀有度），而非实体发现本身。
建议改为：将游戏技术属性表**作为 Phase 2 prompt 的背景上下文注入**，
让 DeepSeek 在生成实体时直接带上这些属性，消除独立的 Phase 1 和 Phase 3。

别称分类（全局唯一 vs 上下文相关）也应移入 Phase 2 的 prompt schema，
由 DeepSeek 在提取时直接完成分类，比启发式规则更准确。

---

## 4. DeepSeek Prompt 与数据契约

### Phase 2 实体提取 Prompt

**System Prompt**：

```
你是崩坏：星穹铁道世界观的专业分析师，负责构建知识图谱。

你的任务是从游戏文本中识别命名实体，并为每个实体生成：
1. description（简短客观描述，说明该实体是什么，20-50字）
2. aliases（全局唯一别称，任何地方出现都指向此实体）
3. relations（与其他实体的关系，需标注时间锚点）

实体类型：
  character | aeon | path | faction | location | event | concept

时间锚点（relations 中必须使用下列 id 之一）：
  epoch_titan            — 泰坦纪·翁法罗斯（黄金裔逐火时代）
  epoch_xianzhou_founding — 仙舟联盟建立时期
  event_jimu             — 建木灾异
  event_buliren          — 步离大战
  event_yinyue           — 饮月之乱
  event_belo_isolation   — 贝洛伯格封闭
  era_kakavasha          — 卡卡瓦夏纪（匹诺康尼历史纪元）
  arc_main_110           — 序幕·湛蓝星空间站
  arc_main_belobog       — 第一幕·雅利洛-Ⅵ
  arc_main_luofu         — 第二幕·仙舟「罗浮」
  arc_main_penacony      — 第三幕·匹诺康尼
  arc_main_amphoreus     — 第四幕·翁法罗斯
  arc_main_paradise      — 第五幕·二相乐园
  arc_post_main          — 主线事件后
  unknown                — 时间不明

position 取值：before | during | after | spanning

注意：
- aliases 只包含全局唯一别称（不含 他/她/祂/少年/将军 等泛化词）
- relations 只包含文本中有明确依据的关系
```

**User Prompt 模板**：

```
请从以下【{count}段】崩坏：星穹铁道文本中提取实体信息。

{texts}

---
输出 JSON 数组，每个实体格式：
{
  "canonical": "规范名称",
  "type": "类型",
  "description": "20-50字描述",
  "aliases": ["唯一别称1"],
  "relations": [
    {
      "target": "目标实体canonical名",
      "relation": "关系动词（英文）",
      "temporal_anchor": "锚点id",
      "temporal_position": "before|during|after|spanning",
      "note": "中文补充说明（可空）"
    }
  ]
}

JSON 数组：
```

### Phase 2 调用参数

```python
model      = "deepseek-chat"
max_tokens = 2000
temperature = 0.1
batch_size  = 6 文档/批（目标约 1200 tokens 文本）
```

### 关系动词规范化 Prompt

（用于 Phase 2 后的 normalization_map.json 生成）

```
Group these knowledge graph verbs by semantics.
Output only a JSON array: [{"canonical": "verb", "variants": ["v1","v2"]},...].
Only include groups with 2+ members. Max 50 groups.
```

### 实体合并建议 Prompt

（从 all_entity_names.txt 发给 DeepSeek）

```
System: 你是崩坏：星穹铁道世界观的专业分析师。
将以下实体名称列表中可以合并的实体分组。

合并标准：
1. 标点符号差异
2. 全名与简称（同一人）
3. 带定语的同一人/地
4. 占位符（{NICKNAME} = 开拓者）

不合并：上下位关系、不同形态的同一角色、同系列不同作品

输出 JSON：
[{"keep": "保留名", "merge": ["要合并的名字"], "reason": "原因"}]
```

---

## 5. 实体数据结构

**文件**：`output/entities.json`

```json
{
  "version": "3.0",
  "temporal_anchors": [...],
  "entities": [
    {
      "canonical":    "实体规范名",
      "type":         "character|aeon|path|faction|location|event|concept",
      "description":  "20-50字描述",
      "attributes":   {"path": "...", "element": "...", "rarity": "..."},
      "aliases":      ["全局唯一别称"],
      "context_aliases": [{"text": "上下文别称", "context": "适用场景说明"}],
      "known_relations": [
        {
          "target":   "目标实体 canonical 名",
          "relation": "规范化动词（见 normalization_map.json）",
          "temporal": {"anchor": "锚点id", "position": "before|during|after|spanning"},
          "note":     "补充说明"
        }
      ],
      "source_hint":  "来源提示",
      "mention_count": 0,
      "disambiguation_note": ""
    }
  ]
}
```

### 时间锚点说明

见 `starrail_rag/tools/temporal_anchors.py`，15 个锚点按 `order` 字段定义偏序关系，相邻锚点 order 差值不代表精确年数，仅表示先后顺序。

---

## 6. 实体清理流程

### 6.1 系列文档自动归并

**脚本**：`entity_pipeline.py` 内置

识别模式：`其一/其二/...`, `上/中/下`, `卷N`, `第N章`, `（一）/（二）...`

```
《帝弓迹躔歌》注疏 其一~五  →  《帝弓迹躔歌》注疏
《贝洛伯格的音乐家》卷一~五  →  《贝洛伯格的音乐家》
```

### 6.2 实体去重

**步骤 1：名称层去重（发送全部名称给 DeepSeek）**

将所有实体名称列表（`output/all_entity_names.txt`）一次性发给 `deepseek-chat`，
让其直接识别可合并的名称对（标点差异、全名/简称、同一人的不同称谓等）。
无需启发式规则预筛选——3,473 个名称约 13k tokens，DeepSeek 可一次处理。

结果见 `output/deepseek_merge_suggestions.json`，人工审核后批量执行。

**步骤 2：描述层语义去重（待执行，与向量化阶段合并）**

名称层无法发现「奥赫玛」和「圣城」这类用不同名字指代同一地点的情况。
这类语义层重复需要：
1. BGE-M3 对所有实体 description 生成嵌入向量
2. 计算余弦相似度，找出高相似度候选对（将 ~600 万对压缩到数百对）
3. DeepSeek 逐对验证

此步骤与向量化阶段（W08）合并执行，避免重复计算嵌入。

### 6.3 关系动词规范化

**映射文件**：`output/normalization_map.json`（99 条映射，18 个规范动词组）

规范动词示例：`located_in`, `created_by`, `leads`, `member_of`, `opposes`, `uses`, `owns` 等。

---

## 7. 待完成工作

按优先级：

1. **Entity Resolution Step 2**：BGE-M3 嵌入相似度筛选（与向量化阶段合并）
2. **Chunk Builder（W07）**：设计各文档类型的切分策略（BGE-M3 最大 8192 token）
3. **向量库索引（W08）**：选型 Chroma 或 Qdrant
4. **LightRAG 建图（W10/W11）**：注入 `entities.json` 的 `aliases` 作为 entity hints
5. **检索层（W12）**：向量检索 + 图遍历混合路由
6. **评估（W15）**：30 题分级评估集（`starrail_rag/eval_set.json`）

---

## 关键文件索引

| 文件 | 说明 |
|------|------|
| `starrail_rag/core/cleaner.py` | 文本清洗管线 |
| `starrail_rag/core/models.py` | Document / DialogueLine 数据模型 |
| `starrail_rag/extractors/wiki_scene.py` | 主线场景级爬取器 |
| `starrail_rag/extractors/wiki_category_scene.py` | 分类任务场景级爬取器 |
| `starrail_rag/tools/entity_pipeline.py` | 实体生成管线（Phase 1-5）|
| `starrail_rag/tools/temporal_anchors.py` | 15 个时间锚点定义 |
| `output/entities.json` | 最终实体知识图谱 |
| `output/normalization_map.json` | 关系动词规范化映射 |
| `output/merge_candidates.json` | 实体合并候选对（Step 1 结果）|
| `output/deepseek_merge_suggestions.json` | DeepSeek 合并建议 |
| `starrail_rag/eval_set.json` | 30 题评估集 |
| `PENDING_ISSUES.md` | 待解决问题清单 |
| `RAG_BOOK_OF_WORK.md` | 项目工作项总追踪 |
