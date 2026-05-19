"""
星穹铁道世界观时间锚点系统 — 三级体系。

=== 三级锚点 ===

  Level 1 — epoch_*    宏观纪元（远古到现代，跨越数百年）
  Level 2 — arc_*      弧线级（游戏各版本的叙事弧，数月到一年）
  Level 3 — ch*        章节级（主线/同行/续闻各章，精度最高）

章节级锚点来源于游戏数据 MainMission.json 的 DisplayPriority 顺序，
通过 TakeParam[MultiSequence] 前置链，同行任务和开拓续闻也能精确
定位到对应章节之后解锁。

=== 关系时间字段完整格式 ===

{
    // 基础时间位置（Level 1/2/3 均通用）
    "anchor":   "ch03",
    "position": "during",          // before | during | after | spanning

    // 时效窗口（所有关系通用，null = 始终成立或不明）
    "valid_from":  null,           // 关系开始成立的 anchor（null = 未知/始终）
    "valid_until": null,           // 关系停止成立的 anchor（null = 仍然成立）

    // 精度标注
    "precision": "arc_level",      // arc_level | event_level | approximate | unknown

    // 原文时间证据（保留原始表述，不归一化）
    "raw_evidence": "主线结局后布洛妮娅接任",

    // 翁法罗斯专项（仅帝皇权杖模拟宇宙内的内容使用）
    "simulation_context": null,    // null | "amphorean_scepter"
    "cycle_number": null           // null | 整数（第 N 次轮回）
}

precision 枚举说明：
  arc_level   — 只知道所在弧线（最常用）
  event_level — 精确到具体命名事件（如饮月之乱发生当天）
  approximate — "数百年前" 等模糊表述，无法映射到具体锚点
  unknown     — 文本中无任何时间信息
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────────────────────
# Level 1：宏观纪元锚点（epoch_*）
# ──────────────────────────────────────────────────────────────────────────────

EPOCH_ANCHORS: list[dict] = [
    {
        "id": "epoch_titan",
        "label": "泰坦纪·翁法罗斯",
        "order": 1,
        "level": 1,
        "description": "泰坦存在于世，黄金裔逐火之旅发生的时代，远古神话纪元",
    },
    {
        "id": "epoch_xianzhou_founding",
        "label": "仙舟联盟建立时期",
        "order": 2,
        "level": 1,
        "description": "六大仙舟联合成军，开启长生不老纪元",
    },
    {
        "id": "event_jimu",
        "label": "建木灾异",
        "order": 3,
        "level": 1,
        "description": "仙舟「罗浮」遭遇建木灾变，持明族出现",
    },
    {
        "id": "event_buliren",
        "label": "步离大战",
        "order": 4,
        "level": 1,
        "description": "仙舟与步离人的大规模战争",
    },
    {
        "id": "event_yinyue",
        "label": "饮月之乱",
        "order": 5,
        "level": 1,
        "description": "丹枫（丹恒前世）饮月事件，罗浮历史重大内乱，云上五骁解散",
    },
    {
        "id": "event_belo_isolation",
        "label": "贝洛伯格封闭",
        "order": 6,
        "level": 1,
        "description": "贝洛伯格上下层封闭，距主线约十余年前",
    },
    {
        "id": "era_kakavasha",
        "label": "卡卡瓦夏纪（匹诺康尼历史纪元）",
        "order": 6,
        "level": 1,
        "description": "匹诺康尼早期历史，家族接管前的边境监狱时代",
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# Level 2：弧线级锚点（arc_*）
# 用于 lore/书籍/角色故事/同行续闻（当无更精确章节信息时）
# ──────────────────────────────────────────────────────────────────────────────

ARC_ANCHORS: list[dict] = [
    {
        "id": "arc_main_110",
        "label": "序幕·空间站「黑塔」（1.0）",
        "order": 10,
        "level": 2,
        "description": "主线序幕，卡芙卡入侵黑塔，开拓者觉醒",
        "chapter_range": ["ch01"],
    },
    {
        "id": "arc_main_belobog",
        "label": "第一幕·雅利洛-Ⅵ（1.x）",
        "order": 11,
        "level": 2,
        "description": "贝洛伯格篇，可可利亚 → 布洛妮娅接任，希儿、杰帕德",
        "chapter_range": ["ch02", "ch03"],
    },
    {
        "id": "arc_main_luofu",
        "label": "第二幕·仙舟「罗浮」（1.x）",
        "order": 12,
        "level": 2,
        "description": "罗浮篇，景元/停云/符玄，建木灾变复发，幻胧被击败",
        "chapter_range": ["ch04", "ch05", "ch06"],
    },
    {
        "id": "arc_main_luofu_late",
        "label": "仙舟后传·第二幕延续（1.x~2.x）",
        "order": 13,
        "level": 2,
        "description": "仙舟尾声及过渡章节，饮月君/刃线索显现",
        "chapter_range": ["ch07", "ch08"],
    },
    {
        "id": "arc_main_penacony",
        "label": "第三幕·匹诺康尼（2.x）",
        "order": 14,
        "level": 2,
        "description": "匹诺康尼篇，流萤/黄泉/星期日，家族与忆质",
        "chapter_range": ["ch09", "ch10", "ch11"],
    },
    {
        "id": "arc_main_amphoreus",
        "label": "第四幕·翁法罗斯（3.x）",
        "order": 15,
        "level": 2,
        "description": "翁法罗斯篇，阿格莱雅/黄金裔/凯撒，帝皇权杖轮回",
        "chapter_range": ["ch12", "ch13", "ch14", "ch15", "ch16", "ch17", "ch18", "ch19"],
    },
    {
        "id": "arc_main_paradise",
        "label": "第五幕·二相乐园（4.x）",
        "order": 16,
        "level": 2,
        "description": "二相乐园篇，花火/不死途",
        "chapter_range": ["ch20", "ch21", "ch22", "ch23"],
    },
    {
        "id": "unknown",
        "label": "时间不明",
        "order": 99,
        "level": 1,
        "description": "无法从现有文本确定时间坐标",
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# Level 3：章节级锚点（ch*）
# 主线/同行/续闻内容专用，来源于游戏数据 MainMission.json
# ──────────────────────────────────────────────────────────────────────────────

CHAPTER_ANCHORS: list[dict] = [
    {
        "id": "ch01",
        "label": "第1章：今天是昨天的明天（空间站「黑塔」）",
        "order": 101,
        "level": 3,
        "arc": "arc_main_110",
        "description": "列车组初到黑塔空间站，开拓者觉醒，遇见帕姆",
    },
    {
        "id": "ch02",
        "label": "第2章：于枯索的冬夜里（贝洛伯格前期）",
        "order": 102,
        "level": 3,
        "arc": "arc_main_belobog",
        "description": "进入地下城，遇见娜塔莎、克拉拉、杰帕德，了解地面/地下矛盾",
    },
    {
        "id": "ch03",
        "label": "第3章：于曈昽的骄阳下（贝洛伯格后期/结局）",
        "order": 103,
        "level": 3,
        "arc": "arc_main_belobog",
        "description": "可可利亚身亡，布洛妮娅接任大守护者，贝洛伯格主线结局",
        "state_changes": [
            "可可利亚 从「贝洛伯格大守护者」变为「已故」",
            "布洛妮娅·兰德 成为「贝洛伯格大守护者」",
        ],
    },
    {
        "id": "ch04",
        "label": "第4章：乘槎驭风仙窟游（仙舟前期）",
        "order": 104,
        "level": 3,
        "arc": "arc_main_luofu",
        "description": "登上仙舟罗浮，初识景元、停云、白露，遭遇仙舟危机",
    },
    {
        "id": "ch05",
        "label": "第5章：云树百丈蔽重楼（仙舟中期，建木灾异）",
        "order": 105,
        "level": 3,
        "arc": "arc_main_luofu",
        "description": "建木灾变显现，太卜司调查，幻胧伪装成停云的真相逐渐浮现",
    },
    {
        "id": "ch06",
        "label": "第6章：劫波渡尽战云收（仙舟结局）",
        "order": 106,
        "level": 3,
        "arc": "arc_main_luofu",
        "description": "幻胧（绝灭大君）被击败，仙舟危机解除，停云回归",
    },
    {
        "id": "ch07",
        "label": "第7章：喧哗与骚动（仙舟后传/匹诺康尼前奏）",
        "order": 107,
        "level": 3,
        "arc": "arc_main_luofu_late",
        "description": "刃相关事件发展，仙舟后续，通往匹诺康尼的过渡",
    },
    {
        "id": "ch08",
        "label": "第8章：鸽群中的猫（仙舟尾声/过渡）",
        "order": 108,
        "level": 3,
        "arc": "arc_main_luofu_late",
        "description": "仙舟故事收尾，列车组准备前往匹诺康尼",
    },
    {
        "id": "ch09",
        "label": "第9章：在我们的时代里（匹诺康尼 2.2 结局）",
        "order": 109,
        "level": 3,
        "arc": "arc_main_penacony",
        "description": "星期日决战，匹诺康尼主线完结，流萤/黄泉/知更鸟线索收束",
    },
    {
        "id": "ch10",
        "label": "第10章：记忆是梦的开场白（匹诺康尼 2.0）",
        "order": 110,
        "level": 3,
        "arc": "arc_main_penacony",
        "description": "初到匹诺康尼，盛会之星，家族势力，忆质机制",
    },
    {
        "id": "ch11",
        "label": "第11章：再见，匹诺康尼（匹诺康尼 2.1）",
        "order": 111,
        "level": 3,
        "arc": "arc_main_penacony",
        "description": "匹诺康尼中期，钟表小子事件，星期日与家族的阴谋",
    },
    {
        "id": "ch12",
        "label": "第12章：在第八日启程（翁法罗斯序章）",
        "order": 112,
        "level": 3,
        "arc": "arc_main_amphoreus",
        "description": "翁法罗斯（帝皇权杖/安培罗斯）初登场，帝皇权杖之谜",
    },
    {
        "id": "ch13",
        "label": "第13章：落木逐火英雄纪（翁法罗斯，逐火之旅）",
        "order": 113,
        "level": 3,
        "arc": "arc_main_amphoreus",
        "description": "黄金裔历史，逐火之旅，凯撒的过去",
    },
    {
        "id": "ch14",
        "label": "第14章：门扉之启，王座之终（翁法罗斯，凯撒相关）",
        "order": 114,
        "level": 3,
        "arc": "arc_main_amphoreus",
        "description": "凯撒与帝皇权杖的秘密，轮回线索",
    },
    {
        "id": "ch15",
        "label": "第15章：走过安眠地的花丛（翁法罗斯中期）",
        "order": 115,
        "level": 3,
        "arc": "arc_main_amphoreus",
        "description": "翁法罗斯中段，各势力矛盾激化",
    },
    {
        "id": "ch16",
        "label": "第16章：在黎明升起时坠落（翁法罗斯，轮回相关）",
        "order": 116,
        "level": 3,
        "arc": "arc_main_amphoreus",
        "description": "轮回机制显现，第N次逐火之旅的真相",
        "simulation_context": "amphorean_scepter",
    },
    {
        "id": "ch17",
        "label": "第17章：因为太阳将要毁伤（翁法罗斯后期）",
        "order": 117,
        "level": 3,
        "arc": "arc_main_amphoreus",
        "description": "翁法罗斯后段，终局前夕",
    },
    {
        "id": "ch18",
        "label": "第18章：英雄未死之前（翁法罗斯，决战前）",
        "order": 118,
        "level": 3,
        "arc": "arc_main_amphoreus",
        "description": "翁法罗斯决战前准备，各英雄命运交汇",
    },
    {
        "id": "ch19",
        "label": "第19章：于长夜重返大地（翁法罗斯主线结局）",
        "order": 119,
        "level": 3,
        "arc": "arc_main_amphoreus",
        "description": "翁法罗斯主线收束，逐火之旅最终章",
    },
    {
        "id": "ch20",
        "label": "第20章：成为昨日的明天（二相乐园序章）",
        "order": 120,
        "level": 3,
        "arc": "arc_main_paradise",
        "description": "二相乐园初登场，花火登场，不死途相关",
    },
    {
        "id": "ch21",
        "label": "第21章：欢迎来到乐园（二相乐园）",
        "order": 121,
        "level": 3,
        "arc": "arc_main_paradise",
        "description": "二相乐园中段",
    },
    {
        "id": "ch22",
        "label": "第22章：献给破晓的失控（二相乐园中期）",
        "order": 122,
        "level": 3,
        "arc": "arc_main_paradise",
        "description": "二相乐园冲突激化",
    },
    {
        "id": "ch23",
        "label": "第23章：如是，众生欢笑不已（二相乐园后期）",
        "order": 123,
        "level": 3,
        "arc": "arc_main_paradise",
        "description": "二相乐园后期",
    },
    {
        "id": "ch99",
        "label": "特别章：宇宙均衡",
        "order": 199,
        "level": 3,
        "arc": "arc_post_main",
        "description": "跨版本叙事特别章",
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# 汇总与工具函数
# ──────────────────────────────────────────────────────────────────────────────

TEMPORAL_ANCHORS: list[dict] = EPOCH_ANCHORS + ARC_ANCHORS + CHAPTER_ANCHORS

ANCHOR_BY_ID: dict[str, dict] = {a["id"]: a for a in TEMPORAL_ANCHORS}

# 章节锚点顺序列表（用于 < 比较）
CHAPTER_ORDER: list[str] = [a["id"] for a in sorted(CHAPTER_ANCHORS, key=lambda x: x["order"])]

# arc → 所属章节锚点
ARC_TO_CHAPTERS: dict[str, list[str]] = {}
for _a in CHAPTER_ANCHORS:
    _arc = _a.get("arc", "")
    if _arc:
        ARC_TO_CHAPTERS.setdefault(_arc, []).append(_a["id"])


def get_arc_for_chapter(chapter_anchor: str) -> str:
    """给定章节锚点，返回所属弧线锚点。"""
    a = ANCHOR_BY_ID.get(chapter_anchor, {})
    return a.get("arc", "unknown")


def chapter_before(a: str, b: str) -> bool:
    """返回 True 如果章节 a 在章节 b 之前（时间上更早）。"""
    try:
        return CHAPTER_ORDER.index(a) < CHAPTER_ORDER.index(b)
    except ValueError:
        return False


# 注入 DeepSeek prompt 的紧凑锚点描述（仅列出弧线级和章节级）
_PROMPT_ANCHORS = [a for a in TEMPORAL_ANCHORS if a["level"] in (1, 2, 3) and a["id"] != "unknown"]
ANCHOR_PROMPT_HINT: str = "\n".join(
    f"  {a['id']:35s} [L{a['level']}] {a['label']}"
    for a in sorted(_PROMPT_ANCHORS, key=lambda x: x["order"])
)
