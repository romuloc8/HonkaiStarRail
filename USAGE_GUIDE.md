# 星穹铁道世界观 RAG 系统 — 使用手册

> 版本：v1.0  
> 最后更新：2026-05-15  
> 面向对象：独立运行，无 AI Agent 辅助

本手册记录从零开始完整运行本系统的所有步骤。

---

## 目录

1. [环境准备](#1-环境准备)
2. [配置 API Key](#2-配置-api-key)
3. [数据提取（爬取 Wiki + 游戏数据）](#3-数据提取)
4. [实体知识图谱生成](#4-实体知识图谱生成)
5. [向量化索引](#5-向量化索引)
6. [LightRAG 知识图谱构建](#6-lightrag-知识图谱构建)
7. [运行查询](#7-运行查询)
8. [评估系统质量](#8-评估系统质量)
9. [常见问题排查](#9-常见问题排查)
10. [文件结构说明](#10-文件结构说明)

---

## 1. 环境准备

### 1.1 Python 依赖

```bash
pip install chromadb sentence-transformers rank_bm25 requests openai \
            lightrag-hku dashscope jieba tqdm xxhash
```

### 1.2 克隆仓库

```bash
git clone https://github.com/<your-repo>/HonkaiStarRail.git
cd HonkaiStarRail
```

仓库根目录结构：
```
HonkaiStarRail/
├── ExcelOutput/          # 游戏配置表（JSON）
├── TextMap/              # 游戏文本表（Hash → 中文字符串）
├── Story/                # 故事图脚本
├── Config/               # 关卡配置
├── starrail_rag/         # 核心代码
├── output/               # 生成的数据文件（部分已提交）
├── DATA_PIPELINE.md      # 工作流技术文档
└── USAGE_GUIDE.md        # 本手册
```

---

## 2. 配置 API Key

以下 API Key 通过环境变量传入，**不要硬编码到代码里**。

| 变量名 | 用途 | 获取地址 |
|--------|------|---------|
| `HSR_DEEPSEEK_API_KEY` | 实体提取、LightRAG 建图、查询生成 | https://platform.deepseek.com |
| `ALI_API_KEY` | 向量化 Embedding（DashScope）| https://dashscope.console.aliyun.com |

设置方式（每次启动终端需要执行，或加入 `.bashrc`）：

```bash
export HSR_DEEPSEEK_API_KEY="sk-xxxxxxxxxx"
export ALI_API_KEY="sk-xxxxxxxxxx"
```

**DashScope 注意事项**：
- 账号需实名认证
- 需在控制台开通 `text-embedding-v4` 服务
- 关闭「仅使用免费额度」模式（否则超出免费额度后报 403）
- 如果账号在新加坡/海外，使用国际版端点（代码已自动处理）

---

## 3. 数据提取

> 如果 `output/` 目录已有数据文件，可跳过此步骤。

### 3.1 开拓任务主线（场景级）

```bash
python3 -m starrail_rag.extractors.wiki_scene
```

输出：`output/main_story/{01-24}_{章节名}.jsonl`（24 个文件，按章节）

### 3.2 同行/续闻/冒险/活动任务

```bash
python3 -c "
from starrail_rag.extractors.wiki_category_scene import WikiCategorySceneExtractor
from starrail_rag.core.textmap import TextMapResolver
extractor = WikiCategorySceneExtractor('/workspace', TextMapResolver('/workspace'))
extractor.extract()
"
```

输出：`output/companion/`、`output/continuance/`、`output/adventure/`、`output/activity/`

### 3.3 静态 Lore（角色故事/光锥/遗器/书籍/道具）

```bash
python3 -m starrail_rag.cli --extractors character_story light_cone relic_set book item_lore
```

输出：`output/lore/*.jsonl`

### 3.4 数据清洗验证

```bash
# 快速检查是否有残留标签
python3 -c "
import json, re
for f in ['output/main_story/01_今天是昨天的明天.jsonl']:
    docs = [json.loads(l) for l in open(f)]
    dirty = [d for d in docs for dl in d.get('dialogues',[]) 
             if re.search(r'<[a-zA-Z]|\{NICKNAME\}', dl['text'])]
    print(f'{f}: {len(dirty)} 条含残留标签')
"
```

---

## 4. 实体知识图谱生成

### 4.1 运行实体管线

```bash
python3 -m starrail_rag.tools.entity_pipeline
```

这会依次执行：
- **Phase 1**：从游戏数据提取角色/命途/稀有度属性（~1秒）
- **Phase 2**：DeepSeek 批量处理 lore 文本，提取实体 + 别称 + 关系（~3-6小时）
- **Phase 3**：实体合并去重
- **Phase 4**：输出 `output/entities.json`

**断点续传**（中断后继续）：

```bash
python3 -m starrail_rag.tools.entity_pipeline  # 自动从上次中断处继续
```

**只运行特定阶段**：

```bash
python3 -m starrail_rag.tools.entity_pipeline --phases 3,4  # 只做合并和输出
```

### 4.2 名称层去重（可选，提升质量）

将所有实体名称发给 DeepSeek 识别重复：

```bash
python3 -c "
import json, os
from openai import OpenAI

client = OpenAI(api_key=os.environ['HSR_DEEPSEEK_API_KEY'], base_url='https://api.deepseek.com')

# 生成名称列表
with open('output/entities.json') as f:
    entities = json.load(f)['entities']
names = '\n'.join(f'{e[\"canonical\"]}: {e[\"type\"]}' for e in entities)

resp = client.chat.completions.create(
    model='deepseek-chat',
    messages=[
        {'role': 'system', 'content': '找出可以合并的实体对（标点差异/全名简称/同人不同称谓）。输出 JSON：[{\"keep\": \"保留名\", \"merge\": [\"合并名\"], \"reason\": \"原因\"}]'},
        {'role': 'user', 'content': names}
    ],
    max_tokens=3000, temperature=0.1
)
with open('output/deepseek_merge_suggestions.json', 'w') as f:
    json.dump(json.loads(resp.choices[0].message.content), f, ensure_ascii=False, indent=2)
print('建议已保存到 output/deepseek_merge_suggestions.json，请人工审核后执行合并')
"
```

---

## 5. 向量化索引

### 5.1 构建 Dense 向量索引（Chroma + DashScope）

```bash
python3 -m starrail_rag.indexing.indexer --backend dashscope --reset
```

- 首次运行用 `--reset` 清空后重建
- 中断后重新运行（不加 `--reset`）可断点续传
- 预计时间：~20-30 分钟（7,819 个 chunk，DashScope API）

**其他 backend 选项**：

```bash
python3 -m starrail_rag.indexing.indexer --backend openai  # OpenAI text-embedding-3-small
python3 -m starrail_rag.indexing.indexer --backend bge     # 本地 BGE-M3（需 GPU）
```

### 5.2 构建 BM25 Sparse 索引（本地，无需 API）

```bash
python3 -c "
from starrail_rag.indexing.chunker import ChunkBuilder
from starrail_rag.indexing.sparse_store import BM25Store
chunks = ChunkBuilder().build_all()
BM25Store().build(chunks)
print('BM25 索引构建完成')
"
```

预计时间：~10 秒

### 5.3 验证索引

```bash
python3 -c "
import chromadb
col = chromadb.PersistentClient('output/chroma_db').get_collection('starrail_lore')
print(f'Chroma: {col.count()} chunks')
from starrail_rag.indexing.sparse_store import BM25Store
s = BM25Store(); s.load()
print(f'BM25: {s.count} chunks')
"
```

---

## 6. LightRAG 知识图谱构建

> **注意**：此步骤耗时约 6-10 小时，建议在后台运行。

```bash
# 后台运行
nohup python3 -m starrail_rag.lightrag_builder > output/lightrag_build.log 2>&1 &
echo "PID: $!"

# 查看进度
python3 -c "
import json
data = json.load(open('output/lightrag_db/kv_store_doc_status.json'))
done = sum(1 for v in data.values() if v.get('status')=='processed')
print(f'{done}/{len(data)} ({done/len(data)*100:.1f}%)')
"

# 查看图谱规模
python3 -c "
with open('output/lightrag_db/graph_chunk_entity_relation.graphml') as f:
    c = f.read()
print(f'节点: {c.count(\"<node \")}  边: {c.count(\"<edge \")}')
"
```

中断后恢复（LightRAG 自带 LLM cache，不会重复处理已完成的 chunk）：

```bash
python3 -m starrail_rag.lightrag_builder
```

---

## 7. 运行查询

### 7.1 交互式命令行

```bash
export HSR_DEEPSEEK_API_KEY="sk-xxx"
export ALI_API_KEY="sk-xxx"
python3 -m starrail_rag.retrieval.cli
```

支持前缀强制指定模式：
- `/simple 问题` → HybridRetriever（Dense + BM25）
- `/complex 问题` → LightRAG 局部搜索
- `/global 问题` → LightRAG 全局搜索

### 7.2 单次查询

```bash
python3 -m starrail_rag.retrieval.cli -q "帝弓司命是谁"
python3 -m starrail_rag.retrieval.cli -q "贝洛伯格封闭的原因" -m complex
python3 -m starrail_rag.retrieval.cli -q "总结翁法罗斯的主要角色" -m global --verbose
```

### 7.3 Python API

```python
import asyncio, os
from starrail_rag.retrieval.query_engine import QueryEngine

engine = QueryEngine(
    deepseek_key=os.environ["HSR_DEEPSEEK_API_KEY"],
    ali_key=os.environ["ALI_API_KEY"],
)

result = asyncio.run(engine.query("帝弓司命是谁"))
print(result.answer)
print(f"模式: {result.mode.value}")
print(f"来源: {len(result.sources)} 条")
```

### 7.4 查询路由规则

| 模式 | 触发条件 | 检索方式 | LLM |
|------|---------|---------|-----|
| SIMPLE | 短查询 ≤30字，无复杂关键词 | Chroma Dense + BM25 | deepseek-chat |
| COMPLEX | 含「为什么/原因/历史/关系变化/隐秘」等 | LightRAG local | deepseek-chat |
| GLOBAL | 含「总结/概述/整体/全部」等 | LightRAG global | deepseek-reasoner |

---

## 8. 评估系统质量

评估集位于 `starrail_rag/eval_set.json`，包含 30 道分级问题：
- **Easy（10题）**：单一事实查询
- **Medium（10题）**：跨文档综合
- **Hard（10题）**：隐性关联推理

```bash
# ⬜ TODO：评估脚本（W15，待实现）
# python3 -m starrail_rag.evaluate
```

手动测试方法：

```bash
python3 -c "
import json
qs = json.load(open('starrail_rag/eval_set.json'))['questions']
for q in qs[:3]:  # 先测3道
    print(f'[{q[\"difficulty\"]}] {q[\"question\"]}')
    print(f'参考答案: {q[\"answer_key_points\"]}')
    print()
"
```

---

## 9. 常见问题排查

**Q: DashScope 返回 401**
- 检查 `ALI_API_KEY` 是否正确
- 如账号在海外（新加坡），确认代码使用 `dashscope-intl.aliyuncs.com` 端点

**Q: DashScope 返回 403 free tier exhausted**
- 登录 DashScope 控制台 → 关闭「仅使用免费额度」→ 确保账号有余额（充值 ¥10 足够）

**Q: DeepSeek 返回 401**
- 检查 `HSR_DEEPSEEK_API_KEY` 是否正确
- 前往 https://platform.deepseek.com 验证 key

**Q: LightRAG 建图进度不动**
- 查看日志：`tail -20 output/lightrag_build.log`
- 检查进程：`pgrep -f lightrag_builder`
- 如进程已死，重新运行（会自动续传）

**Q: 查询响应很慢**
- SIMPLE 查询：检查 DashScope API 延迟（约 3-5秒/次）
- COMPLEX/GLOBAL：LightRAG 需要多次 LLM 调用，30-60 秒属正常

**Q: 提示「LightRAG unavailable, falling back to HybridRetriever」**
- LightRAG 尚未完成建图，或 `output/lightrag_db/` 目录不存在
- 可先使用 SIMPLE 模式，等建图完成后 COMPLEX/GLOBAL 会自动切换

---

## 10. 文件结构说明

```
output/
├── main_story/                  # 开拓主线场景（24 章，各一个 JSONL）
├── companion/                   # 同行任务（按角色）
├── continuance/                 # 开拓续闻（按星球）
├── adventure/                   # 冒险任务（按星球）
├── activity/                    # 活动任务（按大版本）
├── lore/
│   ├── books.jsonl              # 游戏内书籍（1,018 条）
│   ├── character_stories.jsonl  # 角色故事（82 条）
│   ├── relic_sets.jsonl         # 遗器套装描述（56 条）
│   ├── light_cones.jsonl        # 光锥描述（161 条）
│   └── item_lore.jsonl          # 道具背景（2,058 条）
├── entities.json                # 实体知识图谱（3,428 实体，7,320 关系）
├── chroma_db/                   # Chroma 向量库（不提交 git，可重建）
├── bm25_index.pkl               # BM25 Sparse 索引（不提交 git，可重建）
├── lightrag_db/                 # LightRAG 工作目录（不提交 git，可重建）
├── entity_pipeline_raw.jsonl    # DeepSeek 原始提取（断点续传用）
└── deepseek_merge_suggestions.json  # 实体合并建议

starrail_rag/
├── core/
│   ├── cleaner.py               # 文本清洗管线
│   ├── models.py                # 数据模型（Document, DialogueLine）
│   └── textmap.py               # TextMap Hash 解析器
├── extractors/                  # 数据提取器（wiki 场景、lore 等）
├── indexing/
│   ├── chunk.py                 # Chunk 数据模型
│   ├── chunker.py               # Chunk Builder
│   ├── vector_store.py          # Chroma 向量库接口
│   ├── sparse_store.py          # BM25 Sparse 索引
│   ├── retriever.py             # HybridRetriever（Dense + BM25 RRF）
│   └── indexer.py               # 向量化主程序
├── retrieval/
│   ├── router.py                # 查询路由（SIMPLE/COMPLEX/GLOBAL）
│   ├── query_engine.py          # 统一查询入口
│   └── cli.py                   # 命令行界面
├── tools/
│   ├── entity_pipeline.py       # 实体生成管线（Phase 1-4）
│   └── temporal_anchors.py      # 时间锚点定义（15 个）
├── lightrag_builder.py          # LightRAG 知识图谱构建
└── eval_set.json                # 评估集（30 题）
```

---

## 快速参考：完整重建流程

```bash
# 1. 设置 API Keys
export HSR_DEEPSEEK_API_KEY="sk-xxx"
export ALI_API_KEY="sk-xxx"

# 2. 数据提取（已有则跳过）
python3 -m starrail_rag.extractors.wiki_scene          # 主线场景
python3 -m starrail_rag.cli --extractors character_story light_cone relic_set book item_lore

# 3. 实体管线
python3 -m starrail_rag.tools.entity_pipeline          # ~3-6小时，支持断点续传

# 4. 向量化
python3 -m starrail_rag.indexing.indexer --backend dashscope --reset  # ~30分钟
python3 -c "from starrail_rag.indexing.chunker import ChunkBuilder; from starrail_rag.indexing.sparse_store import BM25Store; BM25Store().build(ChunkBuilder().build_all())"

# 5. LightRAG 建图（后台运行）
nohup python3 -m starrail_rag.lightrag_builder > output/lightrag_build.log 2>&1 &

# 6. 查询
python3 -m starrail_rag.retrieval.cli
```
