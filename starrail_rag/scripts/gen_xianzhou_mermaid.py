"""
生成两级 Mermaid 图，对应游戏攻略图的两种视图：

Level 1 (截图1风格): 仙舟「罗浮」弧线总览
  - 主线章节节点（大卡片）→ 各章节解锁的同行/续闻/世界任务

Level 2 (截图2风格): 某一章节内部结构
  - 章节内各 MainMission 节点（小卡片）→ 解锁的分支任务及其链式结构

同时输出最终的数据结构说明（JSON 示例）。

用法：
  python3 -m starrail_rag.scripts.gen_xianzhou_mermaid
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

DATA_ROOT = Path("/workspace")
OUTPUT_DIR = DATA_ROOT / "output"


def load_data():
    raw = json.load(open(DATA_ROOT / "ExcelOutput/MainMission.json"))
    missions = {m.get("MainMissionID"): m
                for m in (raw if isinstance(raw, list) else raw.values())}
    order = json.load(open(OUTPUT_DIR / "mission_order.json"))
    from starrail_rag.core.textmap import TextMapResolver
    tr = TextMapResolver(DATA_ROOT)
    return missions, order["mission_order"], tr


def build_reverse_index(missions: dict) -> dict[int, list[dict]]:
    """MainMissionID → 以该 ID 为前置的所有任务列表"""
    idx: dict[int, list[dict]] = defaultdict(list)
    for mid, m in missions.items():
        for p in m.get("TakeParam", []):
            if p.get("Type") == "MultiSequence":
                idx[p["Value"]].append({
                    "id":   mid,
                    "type": m.get("Type", ""),
                    "name": "",  # 填充在下面
                    "next": m.get("NextTrackMainMission"),
                })
    return idx


def resolve_names(missions: dict, tr) -> dict[int, str]:
    return {mid: (tr.resolve_field(m.get("Name")) or f"Mission_{mid}")
            for mid, m in missions.items()}


def type_label(t: str) -> tuple[str, str]:
    """(中文类型, style_class)"""
    return {
        "Main":      ("主线", "mainTask"),
        "Companion": ("同行", "companion"),
        "Gap":       ("续闻", "continuance"),
        "Branch":    ("支线", "branch"),
        "Daily":     ("日常", "branch"),
    }.get(t, (t, "branch"))


def short(name: str, n: int = 14) -> str:
    return name[:n] + "…" if len(name) > n else name


# ─────────────────────────────────────────────────────────────────────────────
# Level 1：弧线总览图（对应截图1）
# 展示一个弧线内所有主线章节 + 每个章节解锁的任务
# ─────────────────────────────────────────────────────────────────────────────

def gen_level1_arc(
    arc_name: str,
    chapter_anchors: list[str],  # 弧线内的章节 anchor 列表
    ordered: list[dict],
    missions: dict,
    names: dict[int, str],
    rev_idx: dict[int, list[dict]],
    chapter_labels: dict[str, str],
    chapter_last_main: dict[str, int],   # 每个章节最后一个 Main 任务 ID
) -> str:
    """生成弧线级 Mermaid（对应截图1）。"""

    lines = [
        f"```mermaid",
        f"%%{{init: {{'theme':'dark','flowchart':{{'curve':'basis'}}}}}}%%",
        f"flowchart LR",
        f"",
        f"    classDef mainCh   fill:#1B4F72,stroke:#1A5276,color:#fff,font-weight:bold",
        f"    classDef companion fill:#784212,stroke:#6E2C00,color:#fff",
        f"    classDef continuance fill:#145A32,stroke:#0B5345,color:#fff",
        f"    classDef branch    fill:#424949,stroke:#616A6B,color:#eee",
        f"    classDef chain     fill:#1A237E,stroke:#283593,color:#fff",
        f"",
        f"    %% ═══ 主线章节链 ═══════════════════════════════",
    ]

    # 章节节点
    prev_ch = None
    for ch in chapter_anchors:
        label = chapter_labels.get(ch, ch).replace("_", " ")
        lines.append(f"    {ch}[\"{label}\"]:::mainCh")
        if prev_ch:
            lines.append(f"    {prev_ch} --> {ch}")
        prev_ch = ch

    lines.append("")
    lines.append("    %% ═══ 各章节解锁的任务（完成最后一个主线任务后）══")

    seen_ids: set[int] = set()

    for ch in chapter_anchors:
        last_main_id = chapter_last_main.get(ch)
        if not last_main_id:
            continue

        last_main_name = names.get(last_main_id, str(last_main_id))
        unlocked = rev_idx.get(last_main_id, [])
        # 过滤掉下一个 Main 任务（那是主线链，已经有箭头）
        side_tasks = [u for u in unlocked
                      if u["id"] not in seen_ids
                      and missions.get(u["id"], {}).get("Type") != "Main"]
        if not side_tasks:
            continue

        lines.append(f"    %% --- {ch} 解锁 ---")
        # 按类型分组
        for task in sorted(side_tasks, key=lambda x: x["type"]):
            tid = task["id"]
            if tid in seen_ids:
                continue
            seen_ids.add(tid)
            tname = names.get(tid, f"Mission_{tid}")
            _, style = type_label(missions.get(tid, {}).get("Type", ""))
            nid = f"s{tid}"
            # 检查这个任务是否有下一个（形成链）
            nxt = missions.get(tid, {}).get("NextTrackMainMission")
            lines.append(f"    {nid}[\"{short(tname)}\"]:::{style}")
            lines.append(f"    {ch} --> {nid}")
            # 链式展开（最多2级）
            if nxt and nxt in missions:
                nxt_name = names.get(nxt, str(nxt))
                nxt_nid = f"s{nxt}"
                lines.append(f"    {nxt_nid}[\"{short(nxt_name)}\"]:::chain")
                lines.append(f"    {nid} --> {nxt_nid}")
                nxt2 = missions[nxt].get("NextTrackMainMission")
                if nxt2 and nxt2 in missions:
                    nxt2_name = names.get(nxt2, str(nxt2))
                    nxt2_nid = f"s{nxt2}"
                    lines.append(f"    {nxt2_nid}[\"{short(nxt2_name)}\"]:::chain")
                    lines.append(f"    {nxt_nid} --> {nxt2_nid}")

        lines.append("")

    lines.append("```")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Level 2：章节内部结构（对应截图2）
# 展示单个章节内的 MainMission 链 + 每个 Mission 解锁的任务
# ─────────────────────────────────────────────────────────────────────────────

def gen_level2_chapter(
    chapter_anchor: str,
    chapter_label: str,
    ordered: list[dict],
    missions: dict,
    names: dict[int, str],
    rev_idx: dict[int, list[dict]],
) -> str:
    """生成章节内部 Mermaid（对应截图2）。"""

    # 章节内的 Main 任务（按 display_priority 排序）
    ch_mains = sorted(
        [r for r in ordered if r["type"] == "main" and r["chapter_anchor"] == chapter_anchor],
        key=lambda x: x["display_priority"] or 0,
    )

    lines = [
        f"```mermaid",
        f"%%{{init: {{'theme':'dark','flowchart':{{'curve':'basis'}}}}}}%%",
        f"flowchart LR",
        f"",
        f"    classDef mainTask  fill:#1B4F72,stroke:#1A5276,color:#fff,font-weight:bold",
        f"    classDef companion fill:#784212,stroke:#6E2C00,color:#fff",
        f"    classDef continuance fill:#145A32,stroke:#0B5345,color:#fff",
        f"    classDef branch    fill:#424949,stroke:#616A6B,color:#eee",
        f"    classDef chain     fill:#1A237E,stroke:#283593,color:#fff",
        f"",
        f"    %% ═══ 章节主线任务链 ═══════════════════════",
    ]

    # 主线链（按 next_track 追踪）
    visited: set[int] = set()
    chain: list[int] = []
    if ch_mains:
        # 找链的起点（没有被章节内其他任务作为 next_track 的任务）
        is_next = {r.get("next_track") for r in ch_mains}
        starts = [r for r in ch_mains if r["id"] not in is_next]
        if starts:
            cur = starts[0]["id"]
        else:
            cur = ch_mains[0]["id"]
        while cur:
            if cur in visited:
                break
            visited.add(cur)
            chain.append(cur)
            m = missions.get(cur, {})
            nxt = m.get("NextTrackMainMission")
            # 只跟随章节内的任务
            if nxt and nxt in {r["id"] for r in ch_mains}:
                cur = nxt
            else:
                break

    for mid in chain:
        label = short(names.get(mid, str(mid)), 18)
        lines.append(f"    m{mid}[\"{label}\"]:::mainTask")
    for i in range(len(chain) - 1):
        lines.append(f"    m{chain[i]} --> m{chain[i+1]}")

    lines.append("")
    lines.append("    %% ═══ 各主线任务解锁的分支任务 ═══════════")

    seen_branch: set[int] = set()
    for mid in chain:
        unlocked = rev_idx.get(mid, [])
        side = [u for u in unlocked
                if u["id"] not in seen_branch
                and missions.get(u["id"], {}).get("Type") != "Main"]
        if not side:
            continue

        lines.append(f"    %% -- 完成「{short(names.get(mid,''), 12)}」后解锁 --")
        for task in sorted(side, key=lambda x: x["type"]):
            tid = task["id"]
            if tid in seen_branch:
                continue
            seen_branch.add(tid)
            tname = names.get(tid, f"Mission_{tid}")
            if not tname or tname.startswith("Mission_"):
                continue  # 跳过无名任务
            _, style = type_label(missions.get(tid, {}).get("Type", ""))
            nid = f"b{tid}"
            lines.append(f"    {nid}[\"{short(tname)}\"]:::{style}")
            lines.append(f"    m{mid} --> {nid}")
            # 展开链（最多3级）
            cur = missions.get(tid, {}).get("NextTrackMainMission")
            prev_nid = nid
            depth = 0
            while cur and cur in missions and depth < 3:
                cn = names.get(cur, str(cur))
                if not cn or cn.startswith("Mission_"):
                    break
                cnid = f"b{cur}"
                lines.append(f"    {cnid}[\"{short(cn)}\"]:::chain")
                lines.append(f"    {prev_nid} --> {cnid}")
                prev_nid = cnid
                cur = missions[cur].get("NextTrackMainMission")
                depth += 1

        lines.append("")

    lines.append("```")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 数据结构 JSON 示例
# ─────────────────────────────────────────────────────────────────────────────

DATA_STRUCTURE_EXAMPLE = '''## 最终数据结构方案

### 核心设计原则

游戏本身的任务树结构已经编码了完整的时序信息，我们直接利用：
- `TakeParam[MultiSequence]` = 前置任务 ID → 时效起点
- `NextTrackMainMission` = 下一个任务 → 任务链
- `Type` = Main/Companion/Gap/Branch/Daily → 任务类别

### 任务节点（用于 entity_pipeline 注入 temporal context）

```json
{
  "mission_id": 1021501,
  "name": "有龙矫矫，其渊渺渺",
  "type": "Main",
  "chapter_anchor": "ch05",
  "arc_anchor": "arc_main_luofu",
  "display_priority": 1021501,
  "prereq_mission_ids": [1021401],
  "next_main_mission": 1021702,
  "unlocks": {
    "companion": [
      {"id": 6020101, "name": "因为我已触碰过天空"},
      {"id": 6020201, "name": "陌生女人的来信"}
    ],
    "branch": [
      {"id": 2020901, "name": "诗仙机器人"},
      {"id": 2021601, "name": "动物凶猛"},
      {"id": 8002211, "name": "评书奇谭•第一回",
       "chain": ["评书奇谭•第二回", "评书奇谭•第三回"]},
      {"id": 2020201, "name": "陶德•雷奥登的学术研究：晚窥青囊"}
    ],
    "gap": []
  }
}
```

### 实体关系时间标注（entity_pipeline 新 schema）

```json
{
  "entity": "可可利亚",
  "relation": "holds_title",
  "target": "贝洛伯格大守护者",
  "temporal": {
    "anchor":               "ch03",
    "position":             "during",
    "valid_from":           null,
    "valid_until":          "ch03",
    "valid_until_mission":  1011503,
    "valid_until_name":     "静静的星河",
    "precision":            "mission_level",
    "raw_evidence":         "可可利亚在「静静的星河」中身亡，由女儿布洛妮娅·兰德接任大守护者"
  },
  "reliability": "confirmed"
}

{
  "entity": "布洛妮娅·兰德",
  "relation": "holds_title",
  "target": "贝洛伯格大守护者",
  "temporal": {
    "anchor":              "ch03",
    "position":            "after",
    "valid_from":          "ch03",
    "valid_from_mission":  1011503,
    "valid_from_name":     "静静的星河",
    "valid_until":         null,
    "valid_until_mission": null,
    "precision":           "mission_level",
    "raw_evidence":        "主线结局后布洛妮娅继任大守护者，后续续闻中作为守护者领导贝洛伯格"
  },
  "reliability": "confirmed"
}
```

### 三级时间系统总结

| 锚点级别 | 用于 | 精度 | 示例 |
|---------|------|------|------|
| `epoch_*` | 远古历史、星神纪元 | 数百年 | `epoch_yinyue` |
| `arc_*` | lore/书籍/角色故事 | 数月~1年 | `arc_main_luofu` |
| `ch_*` | 主线/续闻场景（当无更精确信息）| 数周 | `ch05` |
| `mission_level` | 关键状态变化（`valid_until_mission`）| 单个任务 | `m1011503` |

### 对话来源可信度

```json
{
  "scene_metadata": {
    "mission_id": 1021501,
    "mission_name": "有龙矫矫，其渊渺渺",
    "mission_type": "Main",
    "chapter_anchor": "ch05",
    "narrative_layer": "L1",
    "reliability": "confirmed"
  }
}
// narrative_layer 规则：
// L1 confirmed  = Main 类型主线直接叙事
// L2 historical = Gap/续闻（角色视角回顾）
// L3 character  = Companion 同行任务（角色自述）
// L4 speculation = 已知含记忆重建的 Companion 场景
// L5 fictional  = Branch 中明确标注为世界内虚构的任务
```
'''


# ─────────────────────────────────────────────────────────────────────────────
# 主函数
# ─────────────────────────────────────────────────────────────────────────────

def main():
    missions, ordered, tr = load_data()
    names = resolve_names(missions, tr)
    rev_idx = build_reverse_index(missions)

    # 填充 rev_idx 的 name 字段
    for prereq_id, tasks in rev_idx.items():
        for t in tasks:
            t["name"] = names.get(t["id"], f"Mission_{t['id']}")

    # 仙舟弧章节信息
    xianzhou_arcs = {
        "arc1": {
            "name": "仙舟「罗浮」— 全弧总览（对应截图1风格）",
            "chapters": ["ch04", "ch05", "ch06"],
        },
    }

    # 章节最后一个 Main 任务（用于确定解锁点）
    # 通过 NextTrackMainMission 追踪：最后一个 Main 任务是那个 next 指向下一章节的
    chapter_last_main: dict[str, int] = {
        "ch04": 1021101,   # 茸客鸣呦，玉角盘虬
        "ch05": 1021501,   # 有龙矫矫，其渊渺渺
        "ch06": 1021702,   # 安灵布奠，天清路远
        "ch02": 1011001,   # 我们不擅长告别
        "ch03": 1011503,   # 静静的星河
    }

    chapter_labels = {
        "ch04": "ch04\n乘槎驭风仙窟游\n（仙舟前期）",
        "ch05": "ch05\n云树百丈蔽重楼\n（建木灾异）",
        "ch06": "ch06\n劫波渡尽战云收\n（幻胧被击败）",
        "ch02": "ch02\n于枯索的冬夜里\n（贝洛伯格前期）",
        "ch03": "ch03\n于曈昽的骄阳下\n（可可利亚→布洛妮娅）",
    }

    output_lines = [
        "# 任务时序 Mermaid 图\n",
        DATA_STRUCTURE_EXAMPLE,
        "---\n",
        "## Level 1：弧线总览图（仿截图1）\n",
        "> 展示章节链 + 每章结束后解锁的同行/续闻/世界任务\n\n",
    ]

    # 仙舟弧 Level 1
    l1 = gen_level1_arc(
        arc_name="仙舟「罗浮」",
        chapter_anchors=["ch04", "ch05", "ch06"],
        ordered=ordered,
        missions=missions,
        names=names,
        rev_idx=rev_idx,
        chapter_labels=chapter_labels,
        chapter_last_main=chapter_last_main,
    )
    output_lines.append(l1)

    output_lines.append("\n\n---\n")
    output_lines.append("## Level 1：贝洛伯格弧（额外示例）\n\n")
    l1b = gen_level1_arc(
        arc_name="雅利洛-Ⅵ",
        chapter_anchors=["ch02", "ch03"],
        ordered=ordered,
        missions=missions,
        names=names,
        rev_idx=rev_idx,
        chapter_labels=chapter_labels,
        chapter_last_main=chapter_last_main,
    )
    output_lines.append(l1b)

    output_lines.append("\n\n---\n")
    output_lines.append("## Level 2：云树百丈蔽重楼 内部结构（仿截图2）\n")
    output_lines.append("> 展示章节内各主线任务 + 每个任务后解锁的分支链\n\n")
    l2_ch05 = gen_level2_chapter(
        chapter_anchor="ch05",
        chapter_label="云树百丈蔽重楼",
        ordered=ordered,
        missions=missions,
        names=names,
        rev_idx=rev_idx,
    )
    output_lines.append(l2_ch05)

    output_lines.append("\n\n---\n")
    output_lines.append("## Level 2：于曈昽的骄阳下 内部结构（贝洛伯格结局章）\n\n")
    l2_ch03 = gen_level2_chapter(
        chapter_anchor="ch03",
        chapter_label="于曈昽的骄阳下",
        ordered=ordered,
        missions=missions,
        names=names,
        rev_idx=rev_idx,
    )
    output_lines.append(l2_ch03)

    out_path = OUTPUT_DIR / "mermaid_xianzhou_full.md"
    out_path.write_text("\n".join(output_lines), encoding="utf-8")
    print(f"✓ 输出 → {out_path}")

    # 验证输出的关键任务节点
    print("\n关键验证：")
    print("  ch05 截图2里的任务是否出现在 Level 2 图中？")
    content = out_path.read_text()
    checks = [
        "金鼎灵树，穷途梼杌",
        "有龙矫矫，其渊渺渺",
        "因为我已触碰过天空",
        "陌生女人的来信",
        "诗仙机器人",
        "动物凶猛",
        "评书奇谭•第一回",
        "评书奇谭•第二回",
        "评书奇谭•第三回",
    ]
    for c in checks:
        print(f"  {'✓' if c in content else '✗'} {c}")


if __name__ == "__main__":
    main()
