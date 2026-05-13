# 数据处理工作流文档

> 最后更新：2026-05-13  
> 阶段：数据工程完成，向量化准备就绪

本文档记录从原始提取数据到可用于 GraphRAG 的结构化数据集的完整处理流程，**不包含数据提取部分**（wiki 爬取、游戏数据解析见 `RAG_BOOK_OF_WORK.md`）。

---

## 1. 输入数据

处理流程的起点是以下 JSONL/JSON 文件，每行一个 `Document` 对象：

| 文件 | 文档数 | 说明 |
|------|--------|------|
| `output/wiki_mission.jsonl` | 199 | 开拓主线剧情对话（去重后）|
| `output/wiki_category.jsonl` | 280 | 同行/续闻/冒险/活动任务对话 |
| `output/character_story.jsonl` | 82 | 角色故事 |
| `output/relic_set.jsonl` | 56 | 遗器套装描述 |
| `output/light_cone.jsonl` | 161 | 光锥描述 |
| `output/book.jsonl` | 1,018 | 游戏内书籍/档案 |
| `output/item_lore.jsonl` | 2,058 | 道具背景描述 |

### Document 数据结构

```python
{
  "doc_id":    str,          # 唯一标识符，如 "wiki_mission_1010902"
  "doc_type":  str,          # "main_mission" | "character_story" | "book" | ...
  "title":     str,          # 文档标题
  "dialogues": [             # 对话行列表（非对话类文档为空）
    {
      "sentence_id": int,    # 负数为 wiki 来源（无 game sentence id）
      "speaker":     str,    # 说话人（空字符串为旁白）
      "text":        str,    # 台词正文
      "voice_id":    int|null
    }
  ],
  "body":     str,           # 非对话类文本正文（书籍、描述等）
  "metadata": { ... }        # 文档元数据（chapter_name, mission_id 等）
}
```

---

## 2. 文本清洗层

**入口**：`starrail_rag/core/cleaner.py` — `CleaningPipeline`

所有文档的文本字段（`text`、`speaker`、`body`）在生成后统一经过清洗管线处理。

### 清洗规则（按应用顺序）

| 规则 | 处理内容 | 示例 |
|------|---------|------|
| `nickname` | `{NICKNAME}` → `开拓者` | `{NICKNAME}你好` → `开拓者你好` |
| `layout_tags` | 移除布局标签，保留文本 | `{LAYOUT_MOBILE#点击}` → `点击` |
| `unbreak_tags` | 移除 `<unbreak>` 标签 | `<unbreak>23</unbreak>时` → `23时` |
| `ruby_annotations` | 移除注音标注包装 | `{RUBY_B#泰坦}尼卡多利{RUBY_E}` → `尼卡多利` |
| `gender_tags` | 性别条件取女性（F#）形式 | `{F#少女}{M#少年}` → `少女` |
| `rich_text_tags` | 移除富文本标签，`<br>` → 换行 | `<size=28>标题</size>` → `标题` |
| `wiki_markup` | 移除 wiki 加粗/斜体标记 | `'''加粗'''` → `加粗` |
| `remaining_xml` | 移除残余 XML 标签 | `<color=#ff0000>文字</color>` → `文字` |
| `curly_placeholders` | 移除残余占位符 | `{ENGINE_TAG}` → `` |
| `normalise_whitespace` | 折叠多余空白/换行 | — |

### wiki 对话分支处理

wiki 对话中的 `{{剧情选项}}` 模板（玩家选项 + NPC 回应）按以下规则处理：

- **所有分支 NPC 回应相同** → 合并玩家选项为 `开拓者：选项A / 选项B / 选项C`，NPC 回应只保留一份
- **各分支 NPC 回应不同** → 完整保留每个分支（`开拓者：选项A` + NPC 回应A，`开拓者：选项B` + NPC 回应B……）

---

## 3. 实体知识图谱生成管线

**入口**：`starrail_rag/tools/entity_pipeline.py`

从游戏结构化数据 + lore 语料两路合并，生成带时间锚点关系的实体知识图谱。

### 管线阶段

```
Phase 1  种子提取
  游戏结构化数据 → 102 个种子实体（可玩角色、星神、命途）
  AvatarConfig.json → 角色（名字、命途、属性、稀有度）
  RogueAeonDisplay.json → 星神（名字、对应命途）
  AvatarBaseType.json → 命途（中英文名对照）

Phase 2  DeepSeek 丰富
  lore 文本（书籍/遗器套装/角色故事/光锥/道具描述）
  → 批量发送给 deepseek-chat（6 篇/批，1200 token/批）
  → 提取：实体描述（description）、别称（aliases）、带时间锚点的关系

Phase 3  合并
  种子实体 + DeepSeek 提取结果 → 按 canonical 名合并
  种子字段（attributes）优先级高于 DeepSeek（不覆盖）
  description 取第一个非空值
  aliases / known_relations 取并集去重

Phase 4  别称过滤
  aliases 拆分为两类：
  - aliases: 全局唯一别称（可安全注入 LightRAG prompt）
  - context_aliases: 上下文相关别称（仅供参考）
  过滤规则：代词 → 删除；泛化名词（少年/将军等）→ 移入 context_aliases

Phase 5  序列化输出
  entities.json（含时间锚点表、统计信息）
```

### 时间锚点

关系的 `temporal` 字段使用 15 个命名锚点（`temporal_anchors.py`），例：

```json
{"anchor": "event_belo_isolation", "position": "during"}
```

| 锚点 ID | 含义 |
|---------|------|
| `epoch_titan` | 泰坦纪·翁法罗斯（黄金裔逐火时代）|
| `event_jimu` | 建木灾异 |
| `event_yinyue` | 饮月之乱 |
| `event_belo_isolation` | 贝洛伯格封闭（距主线约十余年）|
| `arc_main_belobog` | 第一幕·雅利洛-Ⅵ |
| `arc_main_luofu` | 第二幕·仙舟「罗浮」 |
| `arc_main_penacony` | 第三幕·匹诺康尼 |
| `arc_main_amphoreus` | 第四幕·翁法罗斯 |
| … | （共 15 个） |

---

## 4. 实体数据清理

### 4.1 系列文档自动归并

模式识别（`其一/其二/上下/卷N/第N章`）将系列子文档归并进父实体：

```
《帝弓迹躔歌》注疏 其一~五  →  《帝弓迹躔歌》注疏
《贝洛伯格的音乐家》卷一~五  →  《贝洛伯格的音乐家》
科员们的留言便条 其一~六     →  科员们的留言便条
```

共归并 44 个子文档，实体减少 44 个。

### 4.2 实体去重（DeepSeek 辅助）

Step 1 — 启发式候选对生成（无 API 调用）：
- **规则 A**：某实体的别称 = 另一实体的规范名 → 候选对
- **规则 B**：名称包含关系（同类型）→ 候选对
- **规则 C**：名称编辑距离 ≤ 2（同类型）→ 候选对

Step 2 — 将所有实体名称列表发给 `deepseek-chat`，人工审核建议后执行 42 组合并：

```
丰饶灵兽·奎木    →  丰饶灵兽•奎木   （标点差异）
佩拉格娅·谢尔... →  佩拉            （用简称作规范名）
布洛妮娅         →  布洛妮娅·兰德   （用全名作规范名）
岚               →  岚（巡猎星神）   （星神带括号说明）
罗浮/仙舟罗浮    →  仙舟「罗浮」     （统一地点名）
假面愚者         →  假面愚人         （不同译名）
{NICKNAME}       →  开拓者           （占位符）
```

Step 3（待执行）— BGE-M3 嵌入相似度筛选，发现未被启发式规则覆盖的潜在重复实体。

### 4.3 关系动词规范化

将 1,311 个唯一动词规范化为主要类别（99 条映射，覆盖 16% 关系）：

| 规范动词 | 被合并的同义词 |
|---------|--------------|
| `located_in` | home_of, birthplace_of, resides_in, set_in, ... |
| `created_by` | authored_by, built_by, founded_by, written_by, ... |
| `leads` | led_by, ruler_of, governs, commands, ... |
| `member_of` | belongs_to, affiliated_with |
| `opposes` | enemy_of, conflicts_with, hostile_toward |
| `uses` | used_by, wields, used_in |
| ... | （共 18 个规范动词组）|

---

## 5. wiki_mission 去重

同名任务（如「漩涡止于中心」有 4 个 mission_id 但对应同一 wiki 页面）按 `wiki_url` 去重，保留 `mission_id` 最小的条目：

```
wiki_mission.jsonl: 299 → 199 条（减少 100 条重复页面）
对话行数: 69,537 → 42,308
```

---

## 6. 当前数据状态

### 知识图谱

| 指标 | 数值 |
|------|------|
| 实体总数 | 3,428 |
| 含描述的实体 | 3,487（99.4%）|
| 关系总数 | 7,320 |
| 规范化后唯一动词 | 1,218 |

| 实体类型 | 数量 | 关系数 |
|---------|------|--------|
| concept | 1,635 | 1,768 |
| character | 993 | 2,698 |
| location | 355 | 1,181 |
| faction | 271 | 1,127 |
| event | 119 | 258 |
| item | 63 | 74 |
| aeon | 56 | 185 |
| path | 14 | 59 |

### 语料文档

| 类型 | 文档数 | 对话/文本量 |
|------|--------|-----------|
| 开拓主线剧情（wiki） | 199 | 42,308 行对话 |
| 同行/续闻/冒险/活动 | 280 | 24,764 行对话 |
| 角色故事 | 82 | — |
| 光锥描述 | 161 | — |
| 遗器套装 | 56 | — |
| 书籍/档案 | 1,018 | — |
| 道具描述 | 2,058 | — |
| **合计** | **3,854** | — |

---

## 7. 待完成工作

按优先级：

1. **Entity Resolution Step 2/3**：BGE-M3 嵌入相似度 → DeepSeek 验证剩余候选对
2. **Chunk Builder（W07）**：设计各文档类型的切分策略（BGE-M3 最大 8192 token）
3. **向量库索引（W08）**：Chroma（本地）或 Qdrant，待选型
4. **LightRAG 建图（W10/W11）**：注入 entities.json 的 aliases 作为 entity hints
5. **检索层（W12）**：向量检索 + 图遍历混合路由
6. **评估（W15）**：30 题分级评估集（`starrail_rag/eval_set.json`）

---

## 关键文件索引

| 文件 | 说明 |
|------|------|
| `starrail_rag/core/cleaner.py` | 文本清洗管线 |
| `starrail_rag/core/models.py` | Document / DialogueLine 数据模型 |
| `starrail_rag/tools/entity_pipeline.py` | 实体生成管线（Phase 1-5）|
| `starrail_rag/tools/temporal_anchors.py` | 15 个时间锚点定义 |
| `output/entities.json` | 最终实体知识图谱 |
| `output/normalization_map.json` | 关系动词规范化映射 |
| `output/merge_candidates.json` | 实体合并候选对（Step 1 结果）|
| `starrail_rag/eval_set.json` | 30 题评估集 |
| `PENDING_ISSUES.md` | 待解决问题清单 |
| `RAG_BOOK_OF_WORK.md` | 项目工作项总追踪 |
