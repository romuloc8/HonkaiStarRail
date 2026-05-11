"""
星穹铁道世界观时间锚点表。

锚点是世界观内的命名事件/纪元，用于为实体关系提供时间坐标。
`order` 字段定义粗粒度的偏序关系（数字越小越早），允许：
  - 同 order 的锚点表示大致同一时代
  - 锚点间 order 差值不代表精确年数，仅表示相对先后

关系的时间字段格式：
    {
        "anchor": "event_yinyue",        # 锚点 id
        "position": "before|during|after|spanning"
    }

  before   — 发生在该锚点之前
  during   — 发生在该锚点期间/同时代
  after    — 发生在该锚点之后
  spanning — 跨越该锚点前后，或持续整个纪元
"""

from __future__ import annotations

TEMPORAL_ANCHORS: list[dict] = [
    {
        "id": "epoch_titan",
        "label": "泰坦纪·翁法罗斯",
        "order": 1,
        "description": "泰坦存在于世，黄金裔逐火之旅发生的时代，远古神话纪元",
    },
    {
        "id": "epoch_xianzhou_founding",
        "label": "仙舟联盟建立时期",
        "order": 2,
        "description": "六大仙舟联合成军，开启长生不老纪元",
    },
    {
        "id": "event_jimu",
        "label": "建木灾异",
        "order": 3,
        "description": "仙舟「罗浮」遭遇建木灾变，持明族出现",
    },
    {
        "id": "event_buliren",
        "label": "步离大战",
        "order": 4,
        "description": "仙舟与步离人的大规模战争",
    },
    {
        "id": "event_yinyue",
        "label": "饮月之乱",
        "order": 5,
        "description": "丹恒•饮月事件，罗浮历史重大内乱，剑首之位空悬",
    },
    {
        "id": "event_belo_isolation",
        "label": "贝洛伯格封闭",
        "order": 6,
        "description": "贝洛伯格上下层封闭，距主线约十余年前",
    },
    {
        "id": "era_kakavasha",
        "label": "卡卡瓦夏纪",
        "order": 6,
        "description": "匹诺康尼所在的历史纪元，与贝洛伯格封闭大致同期",
    },
    {
        "id": "arc_main_110",
        "label": "序幕·湛蓝星空间站",
        "order": 7,
        "description": "主线 1.0：卡芙卡入侵黑塔空间站，开拓者觉醒",
    },
    {
        "id": "arc_main_belobog",
        "label": "第一幕·雅利洛-Ⅵ",
        "order": 8,
        "description": "主线 1.x：贝洛伯格篇，希儿/布洛妮娅/可可利亚",
    },
    {
        "id": "arc_main_luofu",
        "label": "第二幕·仙舟「罗浮」",
        "order": 9,
        "description": "主线 1.x：罗浮篇，景元/停云/符玄，建木灾变复发",
    },
    {
        "id": "arc_main_penacony",
        "label": "第三幕·匹诺康尼",
        "order": 10,
        "description": "主线 2.x：匹诺康尼篇，流萤/黄泉/知更鸟/星期日",
    },
    {
        "id": "arc_main_amphoreus",
        "label": "第四幕·翁法罗斯",
        "order": 11,
        "description": "主线 3.x：翁法罗斯篇，阿格莱雅/黄金裔/逐火之旅",
    },
    {
        "id": "arc_main_paradise",
        "label": "第五幕·二相乐园",
        "order": 12,
        "description": "主线 4.x：二相乐园篇，花火/不死途",
    },
    {
        "id": "arc_post_main",
        "label": "主线事件后",
        "order": 13,
        "description": "各主线章节结束后的后续状态",
    },
    {
        "id": "unknown",
        "label": "时间不明",
        "order": 99,
        "description": "无法从现有文本确定时间坐标",
    },
]

# 方便按 id 快速查找
ANCHOR_BY_ID: dict[str, dict] = {a["id"]: a for a in TEMPORAL_ANCHORS}

# 注入 DeepSeek prompt 的紧凑锚点描述
ANCHOR_PROMPT_HINT: str = "\n".join(
    f"  {a['id']:35s} — {a['label']}（{a['description']}）"
    for a in TEMPORAL_ANCHORS
)
