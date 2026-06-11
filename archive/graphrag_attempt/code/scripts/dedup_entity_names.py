"""
实体名称去重脚本：将所有实体名称发给 DeepSeek，识别可合并的重复实体。
结果需人工审核后再执行合并。

用法：
    python3 -m starrail_rag.scripts.dedup_entity_names

输出：
    output/deepseek_merge_suggestions.json
"""
import json, os
from pathlib import Path
from openai import OpenAI

ENTITIES_PATH    = Path("output/entities.json")
SUGGESTIONS_PATH = Path("output/deepseek_merge_suggestions.json")

api_key = os.environ.get("HSR_DEEPSEEK_API_KEY")
if not api_key:
    raise RuntimeError("请设置 HSR_DEEPSEEK_API_KEY 环境变量")

client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

with open(ENTITIES_PATH) as f:
    entities = json.load(f)["entities"]

names = "\n".join(f'{e["canonical"]}: {e["type"]}' for e in entities)
print(f"发送 {len(entities)} 个实体名称给 DeepSeek...")

resp = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {
            "role": "system",
            "content": (
                "你是崩坏：星穹铁道世界观专家。找出以下实体列表中可以合并的实体对。\n"
                "合并标准：1) 标点符号差异  2) 全名与简称（同一人）"
                "  3) 带定语的同一人/地  4) 占位符（如{NICKNAME}=开拓者）\n"
                "不合并：上下位关系、不同形态的同一角色、同系列不同作品\n"
                "输出 JSON 数组：[{\"keep\": \"保留名\", \"merge\": [\"合并名\"], \"reason\": \"原因\"}]"
            ),
        },
        {"role": "user", "content": names},
    ],
    max_tokens=3000,
    temperature=0.1,
)

content = resp.choices[0].message.content or ""
start, end = content.find("["), content.rfind("]") + 1
if start == -1 or end == 0:
    print("DeepSeek 未返回有效 JSON，原始输出：")
    print(content[:500])
else:
    suggestions = json.loads(content[start:end])
    with open(SUGGESTIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(suggestions, f, ensure_ascii=False, indent=2)
    print(f"✓ {len(suggestions)} 组合并建议已保存到 {SUGGESTIONS_PATH}")
    print("请人工审核后再执行合并（参考 entity_pipeline.py 中的 merge 逻辑）")
