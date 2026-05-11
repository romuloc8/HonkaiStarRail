"""
别称歧义过滤器（第一步：启发式规则）。

将实体的 aliases 拆分为：
  aliases         — 全局唯一别称，可安全注入 LightRAG prompt
  context_aliases — 上下文相关别称，保留备用但不注入 prompt

运行：
    python -m starrail_rag.tools.alias_filter

输入：  output/entities_merged.json
输出：  output/entities_clean.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path

INPUT_PATH = Path("/workspace/output/entities_merged.json")
OUTPUT_PATH = Path("/workspace/output/entities_clean.json")

# -----------------------------------------------------------------------
# 规则 1：直接删除 — 人称代词（在任何语境下都不具备指代唯一性）
# -----------------------------------------------------------------------
PRONOUNS = frozenset([
    "他", "她", "祂", "它", "你", "我", "吾",
    "他们", "她们", "它们", "你们", "我们",
    "那人", "那位", "此人", "这人",
    "那他", "那她",
])

# -----------------------------------------------------------------------
# 规则 2：移至 context_aliases — 泛化名词（极常见于多个不同实体）
# -----------------------------------------------------------------------
GENERIC_NOUNS = frozenset([
    # 年龄/性别泛称
    "少年", "少女", "女孩", "男孩", "小孩", "孩子",
    "女人", "男人", "老人", "老者", "长者", "老者",
    "女子", "男子", "女性", "男性",
    "小姑娘", "小女孩", "小男孩", "小伙子",
    "年轻人", "年轻女子", "年轻男子",
    "青年", "少壮", "老翁", "老妪",
    # 外貌泛称
    "红发女子", "黑发少年", "白发男子", "金发少女",
    "银发男子", "棕发男子", "白发青年",
    # 身份泛称（无专名）
    "学者", "商人", "旅人", "旅者", "战士",
    "武者", "剑士", "弓手", "骑士", "信使",
    "诗人", "画家", "歌者", "舞者",
    "医者", "医师", "药师",
    "织者", "猎人", "渔夫", "农夫",
    "孤儿", "难民", "流浪者", "冒险者",
    "外来者", "外来客", "异乡人", "访客",
    "主角", "主人公",
    # 关系泛称
    "父亲", "母亲", "儿子", "女儿", "兄弟", "姐妹",
    "哥哥", "弟弟", "姐姐", "妹妹",
    "爷爷", "奶奶", "叔叔", "阿姨",
    "丈夫", "妻子", "爱人",
    "朋友", "同伴", "伙伴", "搭档",
    "导师", "弟子", "徒弟", "师父",
    # 职位泛称（无专名前缀）
    "将军", "大人", "大人物",
    "统领", "首领", "领袖", "头领",
    "船长", "队长", "班长",
    "先生", "女士", "小姐", "夫人",
    "大哥", "大姐", "老大",
    "老师", "教授", "博士",
    "使者", "使臣",
    "守卫", "卫士", "护卫", "侍卫",
    "判官", "判者",
])

# -----------------------------------------------------------------------
# 规则 3：保留 — 可信唯一别称的标志性前缀/模式
# -----------------------------------------------------------------------

# 这些模式出现时，别称基本是唯一的（如「景元将军」、「#83号会员」）
RELIABLE_PATTERNS = [
    re.compile(r'.{2,}将军$'),          # XXX将军
    re.compile(r'.{2,}大人$'),          # XXX大人（带具体名字）
    re.compile(r'.{2,}统领$'),
    re.compile(r'.{2,}首领$'),
    re.compile(r'#\d+'),                 # 天才俱乐部#83
    re.compile(r'^AR-\d+'),             # AR-26710
    re.compile(r'•'),                    # 丹恒•腾荒
    re.compile(r'「.+」'),              # 「黑塔」空间站
    re.compile(r'[··].+'),             # 中文间隔号
]

# 单字别称（几乎不可能唯一）
def _is_too_short(text: str) -> bool:
    return len(text.strip('「」『』""\'\'')) <= 1


def _is_reliable(alias: str) -> bool:
    """判断别称是否足够可靠（全局唯一）。"""
    alias = alias.strip()

    # 单字直接排除
    if _is_too_short(alias):
        return False

    # 纯代词
    if alias in PRONOUNS:
        return False

    # 泛化名词（精确匹配）
    if alias in GENERIC_NOUNS:
        return False

    # 匹配可信模式
    for pattern in RELIABLE_PATTERNS:
        if pattern.search(alias):
            return True

    # 两字纯汉字泛化词（很可能模糊）
    if re.fullmatch(r'[\u4e00-\u9fff]{2}', alias):
        # 只有两个汉字 → 大概率泛化（她/那个/男人等）
        # 但有专名例外，先保守处理：移入 context
        return False

    return True


def _classify_alias(alias: str, entity_canonical: str) -> str:
    """
    返回 'keep' | 'context' | 'drop'
    """
    alias = alias.strip()
    if not alias or alias == entity_canonical:
        return "drop"
    if alias in PRONOUNS:
        return "drop"
    if _is_reliable(alias):
        return "keep"
    # 泛化名词 or 短词 → context
    return "context"


# -----------------------------------------------------------------------
# 主处理函数
# -----------------------------------------------------------------------

def filter_aliases(input_path: Path = INPUT_PATH, output_path: Path = OUTPUT_PATH) -> dict:
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    stats = {
        "total_entities": 0,
        "total_aliases_before": 0,
        "kept": 0,
        "moved_to_context": 0,
        "dropped": 0,
    }

    cleaned_entities = []
    for entity in data["entities"]:
        stats["total_entities"] += 1
        raw_aliases = entity.get("aliases", [])
        stats["total_aliases_before"] += len(raw_aliases)

        kept: list[str] = []
        context: list[dict] = []

        for alias in raw_aliases:
            decision = _classify_alias(alias, entity["canonical"])
            if decision == "keep":
                kept.append(alias)
                stats["kept"] += 1
            elif decision == "context":
                context.append({
                    "text": alias,
                    "context": entity.get("source_hint", ""),
                })
                stats["moved_to_context"] += 1
            else:
                stats["dropped"] += 1

        cleaned = {
            "canonical": entity["canonical"],
            "type": entity["type"],
            "aliases": kept,
            "context_aliases": context,
            "source_hint": entity.get("source_hint", ""),
            "mention_count": entity.get("mention_count", 1),
        }
        cleaned_entities.append(cleaned)

    output = {
        "version": "2.1",
        "description": data.get("description", "") + "（别称已过滤）",
        "model": data.get("model", ""),
        "filter_rules": "v1: pronouns→drop, generic nouns→context, short words→context",
        "stats": {
            **data.get("stats", {}),
            "alias_filter": stats,
        },
        "entities": cleaned_entities,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return stats


if __name__ == "__main__":
    stats = filter_aliases()
    before = stats["total_aliases_before"]
    kept = stats["kept"]
    ctx = stats["moved_to_context"]
    dropped = stats["dropped"]
    print(f"\n别称过滤完成")
    print(f"  处理实体:   {stats['total_entities']}")
    print(f"  过滤前别称: {before}")
    print(f"  保留 (aliases):          {kept:4d}  ({100*kept/before:.0f}%)")
    print(f"  移入 (context_aliases):  {ctx:4d}  ({100*ctx/before:.0f}%)")
    print(f"  删除 (pronouns/empty):   {dropped:4d}  ({100*dropped/before:.0f}%)")
    print(f"\n输出: output/entities_clean.json")
