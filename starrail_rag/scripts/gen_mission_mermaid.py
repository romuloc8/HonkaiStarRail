"""
将 mission_order.json 转换为 Mermaid 流程图代码。

输出：
  output/mermaid_mission_overview.md   - 章节级概览（24 节点，最直观）
  output/mermaid_mission_detail.md     - 各弧线详细图（含同行/续闻分支）

用法：
  python3 -m starrail_rag.scripts.gen_mission_mermaid
"""

from __future__ import annotations
import json
import re
from collections import defaultdict
from pathlib import Path

OUTPUT_DIR = Path("/workspace/output")

CHAPTER_ORDER = [
    "ch01","ch02","ch03","ch04","ch05","ch06",
    "ch07","ch08","ch09","ch10","ch11","ch12",
    "ch13","ch14","ch15","ch16","ch17","ch18",
    "ch19","ch20","ch21","ch22","ch23","ch99",
]

# 弧线分组（用于详细图）
ARC_CHAPTERS = {
    "空间站「黑塔」":     ["ch01"],
    "雅利洛-Ⅵ / 贝洛伯格": ["ch02", "ch03"],
    "仙舟「罗浮」前期":   ["ch04", "ch05", "ch06"],
    "仙舟「罗浮」后期":   ["ch07", "ch08"],
    "匹诺康尼":           ["ch09", "ch10", "ch11"],
    "翁法罗斯":           ["ch12", "ch13", "ch14", "ch15", "ch16", "ch17", "ch18", "ch19"],
    "二相乐园":           ["ch20", "ch21", "ch22", "ch23", "ch99"],
}

# 章节简称（用于节点标签，避免太长）
CHAPTER_SHORT = {
    "ch01": "第1章\n今天是昨天的明天\n🌌 空间站黑塔",
    "ch02": "第2章\n于枯索的冬夜里\n❄️ 贝洛伯格前期",
    "ch03": "第3章\n于曈昽的骄阳下\n💀 贝洛伯格结局\n可可利亚↓布洛妮娅↑",
    "ch04": "第4章\n乘槎驭风仙窟游\n⚓ 仙舟前期",
    "ch05": "第5章\n云树百丈蔽重楼\n🌳 建木灾异",
    "ch06": "第6章\n劫波渡尽战云收\n⚔️ 幻胧被击败",
    "ch07": "第7章\n喧哗与骚动\n🗡️ 刃线索 匹诺康尼前奏",
    "ch08": "第8章\n鸽群中的猫\n🕊️ 仙舟尾声",
    "ch09": "第9章\n在我们的时代里\n🎭 匹诺康尼结局\n星期日决战 2.2",
    "ch10": "第10章\n记忆是梦的开场白\n🌙 匹诺康尼 2.0",
    "ch11": "第11章\n再见，匹诺康尼\n🎪 匹诺康尼 2.1",
    "ch12": "第12章\n在第八日启程\n⏳ 翁法罗斯序章",
    "ch13": "第13章\n落木逐火英雄纪\n🔥 逐火之旅",
    "ch14": "第14章\n门扉之启，王座之终\n👑 凯撒相关",
    "ch15": "第15章\n走过安眠地的花丛\n🌸 翁法罗斯中期",
    "ch16": "第16章\n在黎明升起时坠落\n🔄 轮回显现",
    "ch17": "第17章\n因为太阳将要毁伤\n☀️ 翁法罗斯后期",
    "ch18": "第18章\n英雄未死之前\n🛡️ 决战前",
    "ch19": "第19章\n于长夜重返大地\n🌅 翁法罗斯结局",
    "ch20": "第20章\n成为昨日的明天\n🎠 二相乐园序章",
    "ch21": "第21章\n欢迎来到乐园\n🎡 二相乐园",
    "ch22": "第22章\n献给破晓的失控\n🌅 失控",
    "ch23": "第23章\n如是，众生欢笑不已\n😄",
    "ch99": "特别章\n宇宙均衡\n⚖️",
}

ARC_COLORS = {
    "空间站「黑塔」":       ("#1565C0", "#E3F2FD"),
    "雅利洛-Ⅵ / 贝洛伯格": ("#B71C1C", "#FFEBEE"),
    "仙舟「罗浮」前期":     ("#4A148C", "#F3E5F5"),
    "仙舟「罗浮」后期":     ("#6A1B9A", "#EDE7F6"),
    "匹诺康尼":             ("#E65100", "#FFF3E0"),
    "翁法罗斯":             ("#1B5E20", "#E8F5E9"),
    "二相乐园":             ("#880E4F", "#FCE4EC"),
}


def safe_id(text: str) -> str:
    """将任务名转为 Mermaid 安全 ID。"""
    return re.sub(r"[^\w]", "_", text)[:40]


def truncate(text: str, maxlen: int = 12) -> str:
    """截断文字用于节点标签。"""
    return text[:maxlen] + "…" if len(text) > maxlen else text


# ──────────────────────────────────────────────────────────────────────────────
# 图1：章节级概览
# ──────────────────────────────────────────────────────────────────────────────

def gen_overview(
    ordered: list[dict],
    wiki_map: dict[str, dict],
) -> str:
    """生成 24 章节的概览流程图，同行/续闻任务只显示数量。"""

    # 统计每章的同行/续闻任务数
    comp_by_ch: dict[str, list[str]] = defaultdict(list)
    cont_by_ch: dict[str, list[str]] = defaultdict(list)
    for r in ordered:
        if r["type"] == "companion" and not r["name"].startswith("Mission_"):
            comp_by_ch[r["chapter_anchor"]].append(r["name"])
        elif r["type"] == "continuance" and not r["name"].startswith("Mission_"):
            cont_by_ch[r["chapter_anchor"]].append(r["name"])

    lines = [
        "```mermaid",
        "flowchart TD",
        "",
        "    %% ── 章节节点样式 ──────────────────────────────────────────",
        "    classDef main      fill:#1565C0,stroke:#0D47A1,color:#fff,font-size:11px",
        "    classDef mainKey   fill:#B71C1C,stroke:#7F0000,color:#fff,font-size:11px",
        "    classDef companion fill:#E65100,stroke:#BF360C,color:#fff,font-size:10px",
        "    classDef continua  fill:#2E7D32,stroke:#1B5E20,color:#fff,font-size:10px",
        "",
        "    %% ── 主线章节节点 ──────────────────────────────────────────",
    ]

    prev = None
    for arc_name, chapters in ARC_CHAPTERS.items():
        lines.append(f"    %% == {arc_name} ==")
        for ch in chapters:
            label = CHAPTER_SHORT.get(ch, ch).replace("\n", "<br/>")
            n_comp = len(comp_by_ch[ch])
            n_cont = len(cont_by_ch[ch])
            if n_comp or n_cont:
                label += f"<br/><small>同行×{n_comp} 续闻×{n_cont}</small>"
            is_key = ch in ("ch03", "ch06", "ch09", "ch19")
            style = "mainKey" if is_key else "main"
            lines.append(f"    {ch}[\"{label}\"]:::{style}")
            if prev:
                lines.append(f"    {prev} --> {ch}")
            prev = ch
        lines.append("")

    lines.append("```")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# 图2：各弧线详细图（同行/续闻作为分支）
# ──────────────────────────────────────────────────────────────────────────────

def gen_arc_detail(
    arc_name: str,
    arc_chapters: list[str],
    ordered: list[dict],
) -> str:
    """生成单个弧线的详细 Mermaid 图。"""

    # 弧线内主线任务（有中文名，按 display_priority 排序）
    main_in_arc = [
        r for r in ordered
        if r["type"] == "main"
        and r["chapter_anchor"] in arc_chapters
        and not r["name"].startswith("Mission_")
    ]

    # 弧线内同行/续闻任务
    comp_in_arc = [
        r for r in ordered
        if r["type"] == "companion"
        and r["chapter_anchor"] in arc_chapters
        and not r["name"].startswith("Mission_")
    ]
    cont_in_arc = [
        r for r in ordered
        if r["type"] == "continuance"
        and r["chapter_anchor"] in arc_chapters
        and not r["name"].startswith("Mission_")
    ]

    # 用章节节点作为锚点（比单个任务节点更清晰）
    lines = [
        f"```mermaid",
        f"flowchart TD",
        f"",
        f"    classDef mainCh   fill:#1565C0,stroke:#0D47A1,color:#fff",
        f"    classDef mainTask fill:#42A5F5,stroke:#1E88E5,color:#fff,font-size:10px",
        f"    classDef comp     fill:#FF7043,stroke:#E64A19,color:#fff,font-size:10px",
        f"    classDef cont     fill:#66BB6A,stroke:#43A047,color:#fff,font-size:10px",
        f"",
    ]

    # 章节节点
    for ch in arc_chapters:
        label = CHAPTER_SHORT.get(ch, ch).replace("\n", "<br/>")
        lines.append(f"    {ch}[\"{label}\"]:::mainCh")
    lines.append("")

    # 主线章节连接
    for i in range(len(arc_chapters) - 1):
        lines.append(f"    {arc_chapters[i]} --> {arc_chapters[i+1]}")
    lines.append("")

    # 每章内：显示 3-5 个代表性主线任务（首/尾）
    lines.append("    %% ── 主线关键任务（每章首尾）──")
    for ch in arc_chapters:
        ch_tasks = [r for r in main_in_arc if r["chapter_anchor"] == ch]
        if len(ch_tasks) <= 4:
            display = ch_tasks
        else:
            display = [ch_tasks[0], ch_tasks[len(ch_tasks)//2], ch_tasks[-1]]
        for r in display:
            nid = f"m{r['id']}"
            label = truncate(r["name"], 14)
            lines.append(f"    {nid}[\"{label}\"]:::mainTask")
            lines.append(f"    {ch} -.-> {nid}")
    lines.append("")

    # 同行任务分支（按解锁章节分组，按任务名去重）
    if comp_in_arc:
        lines.append("    %% ── 同行任务 ──")
        comp_by_ch: dict[str, list] = defaultdict(list)
        seen_comp: set[str] = set()
        for r in comp_in_arc:
            name_key = f"{r['chapter_anchor']}:{r['name']}"
            if name_key not in seen_comp:
                seen_comp.add(name_key)
                comp_by_ch[r["chapter_anchor"]].append(r)
        for ch in arc_chapters:
            for r in comp_by_ch[ch]:
                nid = f"c{safe_id(r['name'])}_{ch}"
                prereq = r.get("prereq_info", "")
                prereq_short = ""
                if "「" in prereq:
                    m = re.search(r'「(.{1,12})」', prereq)
                    if m:
                        prereq_short = f"\\n🔓{m.group(1)}"
                label = f"{truncate(r['name'], 14)}{prereq_short}"
                lines.append(f"    {nid}[\"{label}\"]:::comp")
                lines.append(f"    {ch} ==> {nid}")
        lines.append("")

    # 续闻任务分支（按任务名去重）
    if cont_in_arc:
        lines.append("    %% ── 开拓续闻 ──")
        cont_by_ch: dict[str, list] = defaultdict(list)
        seen_cont: set[str] = set()
        for r in cont_in_arc:
            name_key = f"{r['chapter_anchor']}:{r['name']}"
            if name_key not in seen_cont:
                seen_cont.add(name_key)
                cont_by_ch[r["chapter_anchor"]].append(r)
        for ch in arc_chapters:
            for r in cont_by_ch[ch]:
                nid = f"g{safe_id(r['name'])}_{ch}"
                label = truncate(r["name"], 14)
                lines.append(f"    {nid}[\"{label}\"]:::cont")
                lines.append(f"    {ch} --> {nid}")
        lines.append("")

    lines.append("```")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────────────────────────────────────

def main():
    data     = json.load(open(OUTPUT_DIR / "mission_order.json"))
    ordered  = data["mission_order"]
    wiki_map = data.get("wiki_title_map", {})

    # ── 图1：概览
    overview_md = "# 任务时序概览图（章节级）\n\n"
    overview_md += "> 节点颜色：蓝色=普通章节，红色=关键状态变化章节（布洛妮娅接任/幻胧击败/星期日决战等）\n"
    overview_md += "> 每个节点标注了该章节解锁的同行×N 和续闻×N 数量\n\n"
    overview_md += gen_overview(ordered, wiki_map)
    (OUTPUT_DIR / "mermaid_mission_overview.md").write_text(overview_md, encoding="utf-8")
    print("✓ 概览图 → output/mermaid_mission_overview.md")

    # ── 图2：各弧线详细图
    detail_parts = ["# 任务时序详细图（按弧线分）\n\n"]
    detail_parts.append("> - 蓝色实线箭头 `-->` = 主线章节顺序\n")
    detail_parts.append("> - 蓝色虚线箭头 `-.->` = 章节内主线关键任务\n")
    detail_parts.append("> - 橙色粗箭头 `==>` = 同行任务（注明解锁前置）\n")
    detail_parts.append("> - 绿色箭头 `-->` = 开拓续闻\n\n---\n\n")

    for arc_name, arc_chapters in ARC_CHAPTERS.items():
        detail_parts.append(f"## {arc_name}\n\n")
        detail_parts.append(gen_arc_detail(arc_name, arc_chapters, ordered))
        detail_parts.append("\n\n")

    (OUTPUT_DIR / "mermaid_mission_detail.md").write_text(
        "".join(detail_parts), encoding="utf-8"
    )
    print("✓ 详细图 → output/mermaid_mission_detail.md")


if __name__ == "__main__":
    main()
