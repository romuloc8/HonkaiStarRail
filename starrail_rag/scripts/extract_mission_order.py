"""
任务顺序提取脚本：从游戏数据构建完整的任务时序图，生成可读的顺序文件。

输出：
  output/mission_order.json   - 结构化任务顺序数据（用于 entity_pipeline 注入元数据）
  output/mission_order.md     - 人工可读版本（含中文名、前置要求、时序锚点）

用法：
  python3 -m starrail_rag.scripts.extract_mission_order
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

DATA_ROOT  = Path("/workspace")
EXCEL_DIR  = DATA_ROOT / "ExcelOutput"
OUTPUT_DIR = DATA_ROOT / "output"

# wiki 文件章节名 → (锚点, 说明)  按游戏进度顺序排列
WIKI_CHAPTER_TO_ANCHOR: dict[str, tuple[str, str]] = {
    "今天是昨天的明天":     ("ch01", "第1章：今天是昨天的明天（空间站「黑塔」）"),
    "于枯索的冬夜里":       ("ch02", "第2章：于枯索的冬夜里（贝洛伯格前期）"),
    "于曈昽的骄阳下":       ("ch03", "第3章：于曈昽的骄阳下（贝洛伯格后期/结局，可可利亚身亡，布洛妮娅接任）"),
    "乘槎驭风仙窟游":       ("ch04", "第4章：乘槎驭风仙窟游（仙舟前期）"),
    "云树百丈蔽重楼":       ("ch05", "第5章：云树百丈蔽重楼（仙舟中期，建木灾异）"),
    "劫波渡尽战云收":       ("ch06", "第6章：劫波渡尽战云收（仙舟结局，幻胧被击败）"),
    "喧哗与骚动":           ("ch07", "第7章：喧哗与骚动（仙舟后传/匹诺康尼前奏，刃线索）"),
    "鸽群中的猫":           ("ch08", "第8章：鸽群中的猫（仙舟尾声/过渡）"),
    "在我们的时代里":       ("ch09", "第9章：在我们的时代里（匹诺康尼 2.2 结局，星期日决战）"),
    "记忆是梦的开场白":     ("ch10", "第10章：记忆是梦的开场白（匹诺康尼开幕 2.0）"),
    "再见，匹诺康尼":       ("ch11", "第11章：再见，匹诺康尼（匹诺康尼中期 2.1）"),
    "在第八日启程":         ("ch12", "第12章：在第八日启程（翁法罗斯序章）"),
    "落木逐火英雄纪":       ("ch13", "第13章：落木逐火英雄纪（翁法罗斯，逐火之旅）"),
    "门扉之启，王座之终":   ("ch14", "第14章：门扉之启，王座之终（翁法罗斯，凯撒相关）"),
    "走过安眠地的花丛":     ("ch15", "第15章：走过安眠地的花丛（翁法罗斯中期）"),
    "在黎明升起时坠落":     ("ch16", "第16章：在黎明升起时坠落（翁法罗斯，轮回相关）"),
    "因为太阳将要毁伤":     ("ch17", "第17章：因为太阳将要毁伤（翁法罗斯后期）"),
    "英雄未死之前":         ("ch18", "第18章：英雄未死之前（翁法罗斯，决战前）"),
    "于长夜重返大地":       ("ch19", "第19章：于长夜重返大地（翁法罗斯主线结局）"),
    "成为昨日的明天":       ("ch20", "第20章：成为昨日的明天（二相乐园序章）"),
    "欢迎来到乐园":         ("ch21", "第21章：欢迎来到乐园（二相乐园）"),
    "献给破晓的失控":       ("ch22", "第22章：献给破晓的失控（二相乐园中期）"),
    "如是，众生欢笑不已":   ("ch23", "第23章：如是，众生欢笑不已（二相乐园后期）"),
    "宇宙均衡":             ("ch99", "特别章：宇宙均衡"),
}

CHAPTER_ORDER = [
    "ch01","ch02","ch03","ch04","ch05","ch06",
    "ch07","ch08","ch09","ch10","ch11","ch12",
    "ch13","ch14","ch15","ch16","ch17","ch18",
    "ch19","ch20","ch21","ch22","ch23","ch99",
    "unknown",
]

def chapter_index(anchor: str) -> int:
    try:
        return CHAPTER_ORDER.index(anchor)
    except ValueError:
        return 999


def build_id_to_chapter_map() -> dict[int, tuple[str, str]]:
    """遍历 main_story JSONL，建立 mission_id → (chapter_anchor, chapter_label) 映射。"""
    id_map: dict[int, tuple[str, str]] = {}
    for f in sorted((OUTPUT_DIR / "main_story").glob("*.jsonl")):
        stem = f.stem
        chapter_name = stem.split("_", 1)[1] if "_" in stem else stem
        anchor_info = WIKI_CHAPTER_TO_ANCHOR.get(chapter_name)
        if not anchor_info:
            continue
        for line in open(f):
            doc = json.loads(line.strip())
            mid = doc.get("metadata", {}).get("mission_id")
            if mid and mid not in id_map:
                id_map[mid] = anchor_info
    return id_map


def load_missions() -> dict[int, dict]:
    data = json.load(open(EXCEL_DIR / "MainMission.json"))
    items = data if isinstance(data, list) else list(data.values())
    return {(m.get("MainMissionID") or m.get("ID")): m
            for m in items if (m.get("MainMissionID") or m.get("ID"))}


def build_mission_order(
    missions: dict[int, dict],
    id_to_chapter: dict[int, tuple[str, str]],
    resolver,
) -> list[dict]:

    def get_main_prereqs(mission: dict, depth: int = 0) -> list[int]:
        if depth > 6:
            return []
        result = []
        for p in mission.get("TakeParam", []):
            if p.get("Type") == "MultiSequence":
                pid = p["Value"]
                if pid not in missions:
                    continue
                ptype = missions[pid].get("Type", "")
                if ptype == "Main":
                    result.append(pid)
                elif ptype in ("Companion", "Gap", "Branch"):
                    result.extend(get_main_prereqs(missions[pid], depth + 1))
        return result

    def resolve_chapter(mid: int) -> tuple[str, str]:
        if mid in id_to_chapter:
            return id_to_chapter[mid]
        return "unknown", f"未知章节（ID={mid}）"

    results = []

    # 主线任务
    for mid, m in sorted(missions.items(), key=lambda x: x[1].get("DisplayPriority", 0)):
        if m.get("Type") != "Main":
            continue
        chap_anchor, chap_label = resolve_chapter(mid)
        name = resolver.resolve_field(m.get("Name")) or f"Mission_{mid}"
        results.append({
            "id":               mid,
            "type":             "main",
            "name":             name,
            "display_priority": m.get("DisplayPriority"),
            "chapter_anchor":   chap_anchor,
            "chapter_label":    chap_label,
            "prereq_main_ids":  [],
            "prereq_anchor":    chap_anchor,
            "prereq_info":      "",
            "next_track":       m.get("NextTrackMainMission"),
        })

    # 同行（Companion）和续闻（Gap）
    for mission_type, type_label in [("Companion", "companion"), ("Gap", "continuance")]:
        for mid, m in sorted(missions.items(), key=lambda x: x[1].get("DisplayPriority", 0)):
            if m.get("Type") != mission_type:
                continue
            name = resolver.resolve_field(m.get("Name")) or f"Mission_{mid}"
            main_prereqs = get_main_prereqs(m)

            if main_prereqs:
                latest = max(main_prereqs, key=lambda p: missions[p].get("DisplayPriority", 0))
                chap_anchor, chap_label = resolve_chapter(latest)
                prereq_name = resolver.resolve_field(missions[latest].get("Name"))
                prereq_info = f"完成主线「{prereq_name}」（ID={latest}）后"
            else:
                chap_anchor, chap_label = "unknown", "前置要求不明"
                prereq_info = "无明确前置主线任务"

            results.append({
                "id":               mid,
                "type":             type_label,
                "name":             name,
                "display_priority": m.get("DisplayPriority"),
                "chapter_anchor":   chap_anchor,
                "chapter_label":    chap_label,
                "prereq_main_ids":  main_prereqs,
                "prereq_anchor":    chap_anchor,
                "prereq_info":      prereq_info,
                "next_track":       m.get("NextTrackMainMission"),
            })

    return results


def load_wiki_missions() -> dict[str, dict]:
    wiki: dict[str, dict] = {}
    dirs = {
        "main_story": "main", "companion": "companion",
        "continuance": "continuance", "adventure": "adventure", "activity": "activity",
    }
    for dir_name, mission_type in dirs.items():
        d = OUTPUT_DIR / dir_name
        if not d.exists():
            continue
        for f in sorted(d.glob("*.jsonl")):
            for line in open(f):
                doc = json.loads(line.strip())
                meta = doc.get("metadata", {})
                title = meta.get("mission_title", "")
                if title and title not in wiki:
                    wiki[title] = {
                        "type":         mission_type,
                        "category":     meta.get("category", ""),
                        "group":        meta.get("group", ""),
                        "wiki_url":     meta.get("wiki_url", ""),
                        "mission_id":   meta.get("mission_id"),
                        "chapter_name": meta.get("chapter_name", ""),
                    }
    return wiki


def match_wiki_to_game(
    ordered: list[dict],
    wiki_missions: dict[str, dict],
    missions: dict[int, dict],
    id_to_chapter: dict[int, tuple[str, str]],
    resolver,
) -> dict[str, dict]:
    id_to_record = {r["id"]: r for r in ordered}
    name_to_id: dict[str, int] = {}
    for mid, m in missions.items():
        n = resolver.resolve_field(m.get("Name"))
        if n:
            name_to_id[n] = mid

    result: dict[str, dict] = {}
    for title, wmeta in wiki_missions.items():
        # 1. 通过 mission_id
        mid = wmeta.get("mission_id")
        if mid and mid in id_to_record:
            rec = id_to_record[mid]
            result[title] = {
                "game_id": mid, "chapter_anchor": rec["chapter_anchor"],
                "chapter_label": rec["chapter_label"],
                "prereq_info": rec.get("prereq_info", ""),
                "match_method": "id", "type": wmeta["type"],
            }
            continue

        # 2. 通过 chapter_name（主线专用）
        ch = wmeta.get("chapter_name", "")
        if ch and ch in WIKI_CHAPTER_TO_ANCHOR:
            anchor, label = WIKI_CHAPTER_TO_ANCHOR[ch]
            result[title] = {
                "game_id": mid, "chapter_anchor": anchor, "chapter_label": label,
                "prereq_info": "", "match_method": "chapter_name", "type": wmeta["type"],
            }
            continue

        # 3. 通过任务中文名
        if title in name_to_id:
            mid2 = name_to_id[title]
            rec = id_to_record.get(mid2)
            if rec:
                result[title] = {
                    "game_id": mid2, "chapter_anchor": rec["chapter_anchor"],
                    "chapter_label": rec["chapter_label"],
                    "prereq_info": rec.get("prereq_info", ""),
                    "match_method": "name", "type": wmeta["type"],
                }
                continue

        result[title] = {
            "game_id": None, "chapter_anchor": "unknown",
            "chapter_label": "未匹配（冒险/活动任务不在 MainMission.json 中）",
            "prereq_info": "", "match_method": "none", "type": wmeta["type"],
        }

    return result


def generate_markdown(ordered: list[dict], wiki_match: dict[str, dict]) -> str:
    lines = [
        "# 星穹铁道任务时序总览",
        "",
        "> 生成自游戏数据 `ExcelOutput/MainMission.json`",
        "> 同行/续闻任务的时序锚点通过 `TakeParam[MultiSequence]` 前置链推导",
        "",
        "---",
        "",
        "## 一、主线任务完整顺序",
        "",
    ]

    current_anchor = None
    main_tasks = [r for r in ordered if r["type"] == "main"]
    for r in main_tasks:
        if r["chapter_anchor"] != current_anchor:
            current_anchor = r["chapter_anchor"]
            label = r["chapter_label"]
            lines.append(f"### `{current_anchor}` — {label}")
            lines.append("")
            lines.append("| ID | 任务名 | 下一个 |")
            lines.append("|-----|--------|--------|")
        nxt = r.get("next_track") or "-"
        lines.append(f"| {r['id']} | {r['name']} | {nxt} |")

    lines += ["", "---", "", "## 二、同行任务时序（按前置主线任务推导）", ""]
    for anchor in CHAPTER_ORDER:
        tasks = [r for r in ordered if r["type"] == "companion" and r["chapter_anchor"] == anchor]
        if not tasks:
            continue
        label = next(
            (v[1] for k, v in WIKI_CHAPTER_TO_ANCHOR.items() if v[0] == anchor),
            anchor
        )
        lines.append(f"### 解锁时间点：`{anchor}` — {label}")
        lines.append("")
        lines.append("| 任务名 | 前置说明 |")
        lines.append("|--------|---------|")
        for r in tasks:
            lines.append(f"| {r['name']} | {r.get('prereq_info','无明确前置')} |")
        lines.append("")

    lines += ["---", "", "## 三、开拓续闻时序", ""]
    for anchor in CHAPTER_ORDER:
        tasks = [r for r in ordered if r["type"] == "continuance" and r["chapter_anchor"] == anchor]
        if not tasks:
            continue
        label = next(
            (v[1] for k, v in WIKI_CHAPTER_TO_ANCHOR.items() if v[0] == anchor),
            anchor
        )
        lines.append(f"### 解锁时间点：`{anchor}` — {label}")
        lines.append("")
        lines.append("| 任务名 | 前置说明 |")
        lines.append("|--------|---------|")
        for r in tasks:
            lines.append(f"| {r['name']} | {r.get('prereq_info','无明确前置')} |")
        lines.append("")

    lines += ["---", "", "## 四、Wiki 任务时序锚点汇总", ""]
    by_type: dict[str, list] = defaultdict(list)
    for title, info in wiki_match.items():
        by_type[info["type"]].append((title, info))

    type_order = [
        ("main",        "主线任务（开拓任务）"),
        ("companion",   "同行任务"),
        ("continuance", "开拓续闻"),
        ("adventure",   "冒险任务（世界任务）"),
        ("activity",    "活动任务"),
    ]
    for t, t_label in type_order:
        items = sorted(by_type.get(t, []), key=lambda x: chapter_index(x[1]["chapter_anchor"]))
        if not items:
            continue
        lines.append(f"### {t_label}")
        lines.append("")
        lines.append("| 任务名 | 锚点 | 说明 | 匹配 |")
        lines.append("|--------|------|------|------|")
        for title, info in items:
            m = {"id": "✓", "chapter_name": "✓", "name": "~", "none": "✗"}.get(
                info["match_method"], "?"
            )
            lines.append(
                f"| {title} | `{info['chapter_anchor']}` | {info['chapter_label']} | {m} |"
            )
        lines.append("")

    lines += [
        "---",
        "**匹配方式说明**",
        "- ✓ `id` / `chapter_name`：精确匹配",
        "- ~ `name`：中文名模糊匹配",
        "- ✗ `none`：冒险任务/活动任务，不在 MainMission.json 中（时序待人工补充）",
    ]
    return "\n".join(lines)


def main():
    from starrail_rag.core.textmap import TextMapResolver
    resolver = TextMapResolver(DATA_ROOT)

    print("从 wiki 数据建立 mission_id → chapter 映射…")
    id_to_chapter = build_id_to_chapter_map()
    print(f"  覆盖 {len(id_to_chapter)} 个 mission_id")

    print("加载游戏任务数据…")
    missions = load_missions()
    print(f"  总任务数: {len(missions)}")

    print("构建时序顺序…")
    ordered = build_mission_order(missions, id_to_chapter, resolver)
    by_type = defaultdict(int)
    for r in ordered:
        by_type[r["type"]] += 1
    print(f"  已排序: {dict(by_type)}")

    print("加载 wiki 任务数据…")
    wiki_missions = load_wiki_missions()
    print(f"  wiki 任务名: {len(wiki_missions)} 个")

    print("建立对应关系…")
    wiki_match = match_wiki_to_game(ordered, wiki_missions, missions, id_to_chapter, resolver)
    by_method = defaultdict(int)
    for v in wiki_match.values():
        by_method[v["match_method"]] += 1
    print(f"  匹配结果: {dict(by_method)}")

    out_json = OUTPUT_DIR / "mission_order.json"
    out_md   = OUTPUT_DIR / "mission_order.md"

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "chapter_anchors": [{"anchor": a, "label": l} for a, l in WIKI_CHAPTER_TO_ANCHOR.values()],
            "mission_order":   ordered,
            "wiki_title_map":  wiki_match,
        }, f, ensure_ascii=False, indent=2)
    print(f"✓ JSON  → {out_json}")

    out_md.write_text(generate_markdown(ordered, wiki_match), encoding="utf-8")
    print(f"✓ MD    → {out_md}")

    print("\n各章节主线任务数：")
    from collections import Counter
    cnt = Counter(r["chapter_anchor"] for r in ordered if r["type"] == "main")
    for anchor in CHAPTER_ORDER:
        if anchor in cnt:
            label = next(
                (v[1] for k, v in WIKI_CHAPTER_TO_ANCHOR.items() if v[0] == anchor),
                anchor
            )
            print(f"  {anchor}: {cnt[anchor]:3d}  {label[:40]}")


if __name__ == "__main__":
    main()
