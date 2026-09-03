"""
星穹铁道数据看板生成器
从游戏原始 JSON 数据提取信息，生成自包含的静态 HTML 看板。

用法: python build.py [--data-root ..] [--output index.html] [--lang CHS]
"""

import json
import os
import re
import argparse
from pathlib import Path


# ────────────────────────── 命途 / 元素 中文映射 ──────────────────────────
PATH_ZH = {
    "Knight":  "存护",
    "Rogue":   "巡猎",
    "Mage":    "智识",
    "Warrior": "毁灭",
    "Priest":  "丰饶",
    "Warlock": "虚无",
    "Shaman":  "同谐",
    "Elation": "欢愉",
    "Memory":  "记忆",
}
PATH_EN = {v: k for k, v in PATH_ZH.items()}
ELEMENT_ZH = {
    "Fire":      "火",
    "Ice":       "冰",
    "Wind":      "风",
    "Thunder":   "雷",
    "Physical":  "物理",
    "Quantum":   "量子",
    "Imaginary": "虚数",
}
ELEMENT_COLOR = {
    "Fire":      "#e8533e",
    "Ice":       "#5bb8d4",
    "Wind":      "#4db89b",
    "Thunder":   "#c07de0",
    "Physical":  "#a0a0b0",
    "Quantum":   "#7b68ee",
    "Imaginary": "#d4b84a",
}
PATH_COLOR = {
    "Knight":  "#5b9bd5",
    "Rogue":   "#70ad47",
    "Mage":    "#4472c4",
    "Warrior": "#e05c5c",
    "Priest":  "#ffd966",
    "Warlock": "#9966cc",
    "Shaman":  "#47b5c8",
    "Elation": "#ff8c69",
    "Memory":  "#c0a0e0",
}
RARITY_STAR = {
    "CombatPowerAvatarRarityType5": 5,
    "CombatPowerAvatarRarityType4": 4,
    "CombatPowerLightconeRarity5":  5,
    "CombatPowerLightconeRarity4":  4,
    "CombatPowerLightconeRarity3":  3,
}

PROPERTY_ZH = {
    "HealRatioBase":         "治疗量加成",
    "AttackAddedRatio":      "攻击力%",
    "DefenceAddedRatio":     "防御力%",
    "HPAddedRatio":          "生命值%",
    "SpeedDelta":            "速度",
    "CriticalChanceBase":    "暴击率",
    "CriticalDamageBase":    "暴击伤害",
    "StatusProbabilityBase": "效果命中",
    "StatusResistanceBase":  "效果抵抗",
    "BreakDamageAddedRatioBase": "击破特攻",
    "FireAddedRatio":        "火属性伤害",
    "IceAddedRatio":         "冰属性伤害",
    "ThunderAddedRatio":     "雷属性伤害",
    "WindAddedRatio":        "风属性伤害",
    "QuantumAddedRatio":     "量子属性伤害",
    "ImaginaryAddedRatio":   "虚数属性伤害",
    "PhysicalAddedRatio":    "物理属性伤害",
    "EnergyRecoveryRate":    "充能效率",
}


def load_json(path: str) -> list | dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def hash_str(h) -> str:
    """Turn a hash value (int or dict) into a string key."""
    if isinstance(h, dict):
        h = h.get("Hash", 0)
    return str(h)


def resolve(tm: dict, h) -> str:
    """Resolve a TextMap hash to display text."""
    key = hash_str(h)
    return tm.get(key, "")


def strip_tags(s: str) -> str:
    """Remove <unbreak>…</unbreak> and similar rich-text markup."""
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"#\d+\[([^\]]+)\]", r"{\1}", s)
    return s.strip()


# ─────────────────────────── Main extractors ───────────────────────────

def build_characters(data_root: str, tm: dict) -> list:
    raw = load_json(f"{data_root}/ExcelOutput/AvatarConfig.json")
    promo_raw = load_json(f"{data_root}/ExcelOutput/AvatarPromotionConfig.json")
    skill_raw = load_json(f"{data_root}/ExcelOutput/AvatarSkillConfig.json")
    rank_raw  = load_json(f"{data_root}/ExcelOutput/AvatarRankConfig.json")

    # Map avatarID → max promotion stats (last entry per avatar)
    promo_map: dict[int, dict] = {}
    for p in promo_raw:
        aid = p["AvatarID"]
        if aid not in promo_map or p["MaxLevel"] > promo_map[aid]["MaxLevel"]:
            promo_map[aid] = p

    # Map skillID → skill info (level 1 only for display)
    skill_map: dict[int, dict] = {}
    for s in skill_raw:
        sid = s["SkillID"]
        if sid not in skill_map or s["Level"] == 1:
            skill_map[sid] = s

    # Map rankID → eidolon info
    rank_map: dict[int, dict] = {}
    for r in rank_raw:
        rank_map[r["RankID"]] = r

    characters = []
    for av in raw:
        aid = av["AvatarID"]
        name = resolve(tm, av["AvatarName"])
        full_name = resolve(tm, av["AvatarFullName"])
        if not name:
            continue
        path = av["AvatarBaseType"]
        element = av["DamageType"]
        stars = RARITY_STAR.get(av["Rarity"], 4)

        # Base stats from max ascension
        stats = {}
        if aid in promo_map:
            p = promo_map[aid]
            # Per-level growth values at max ascension; SPD is final value
            stats = {
                "hp_base":  round(p["HPBase"]["Value"]),
                "hp_add":   round(p["HPAdd"]["Value"], 2),
                "atk_base": round(p["AttackBase"]["Value"]),
                "atk_add":  round(p["AttackAdd"]["Value"], 2),
                "def_base": round(p["DefenceBase"]["Value"]),
                "def_add":  round(p["DefenceAdd"]["Value"], 2),
                "spd":      round(p["SpeedBase"]["Value"], 1) if "SpeedBase" in p else 0,
                "crit_rate": round(p.get("CriticalChance", {}).get("Value", 0.05) * 100, 1),
                "crit_dmg":  round(p.get("CriticalDamage", {}).get("Value", 0.5) * 100, 1),
                "taunt":    round(p.get("BaseAggro", {}).get("Value", 0)),
            }

        # Skills (from SkillList on the avatar)
        skills = []
        for sid in av.get("SkillList", []):
            s = skill_map.get(sid)
            if not s:
                continue
            sname = resolve(tm, s["SkillName"])
            sdesc = strip_tags(resolve(tm, s.get("SkillDesc", {})))
            stag  = resolve(tm, s["SkillTypeDesc"])
            if sname:
                skills.append({"name": sname, "tag": stag, "desc": sdesc, "icon": s.get("SkillIcon", "")})

        # Eidolons
        eidolons = []
        for rid in av.get("RankIDList", []):
            r = rank_map.get(rid)
            if not r:
                continue
            rname = resolve(tm, r["Name"])
            rdesc = strip_tags(resolve(tm, r["Desc"]))
            if rname:
                eidolons.append({"rank": r["Rank"], "name": rname, "desc": rdesc})

        characters.append({
            "id":       aid,
            "name":     name,
            "fullName": full_name,
            "path":     path,
            "element":  element,
            "stars":    stars,
            "stats":    stats,
            "skills":   skills,
            "eidolons": eidolons,
        })

    characters.sort(key=lambda c: (-c["stars"], c["name"]))
    return characters


def build_relic_sets(data_root: str, tm: dict) -> list:
    rs_raw  = load_json(f"{data_root}/ExcelOutput/RelicSetConfig.json")
    rss_raw = load_json(f"{data_root}/ExcelOutput/RelicSetSkillConfig.json")

    # Group set skills by SetID
    skills_by_set: dict[int, list] = {}
    for s in rss_raw:
        sid = s["SetID"]
        skills_by_set.setdefault(sid, []).append(s)

    # Load relic piece info for piece type breakdown
    relic_raw = load_json(f"{data_root}/ExcelOutput/RelicConfig.json")
    pieces_by_set: dict[int, list] = {}
    for r in relic_raw:
        pieces_by_set.setdefault(r["SetID"], []).append(r["Type"])

    sets = []
    for rs in rs_raw:
        if not rs.get("Release", False):
            continue
        sid = rs["SetID"]
        name = resolve(tm, rs["SetName"])
        if not name:
            continue

        effects = []
        for s in sorted(skills_by_set.get(sid, []), key=lambda x: x["RequireNum"]):
            req = s["RequireNum"]
            # SkillDesc might be a hash dict or a plain key like "RelicDesc_1012"
            desc_field = s.get("SkillDesc", {})
            if isinstance(desc_field, dict):
                desc = strip_tags(resolve(tm, desc_field))
            else:
                desc = ""
            props = []
            for prop in s.get("PropertyList", []):
                # obfuscated key names – find the property type key
                prop_type = None
                prop_val  = None
                for k, v in prop.items():
                    if isinstance(v, str) and v in PROPERTY_ZH:
                        prop_type = v
                    elif isinstance(v, dict) and "Value" in v:
                        prop_val = v["Value"]
                if prop_type:
                    pct = "%" if "Ratio" in prop_type or "Rate" in prop_type or "Chance" in prop_type or "Damage" in prop_type else ""
                    val_str = f"+{prop_val*100:.0f}{pct}" if pct else f"+{prop_val:.0f}"
                    props.append(f"{PROPERTY_ZH[prop_type]} {val_str}")
            effects.append({"req": req, "desc": desc, "props": props})

        piece_types = list(set(pieces_by_set.get(sid, [])))
        is_planar = any(t in ("Neck", "Object", "Foot", "Hand") for t in piece_types) and len(piece_types) <= 2

        sets.append({
            "id":       sid,
            "name":     name,
            "effects":  effects,
            "isPlanar": is_planar,
            "version":  rs.get("ReleaseVersion", ""),
        })

    sets.sort(key=lambda s: (s["isPlanar"], s["name"]))
    return sets


def build_lightcones(data_root: str, tm: dict) -> list:
    eq_raw = load_json(f"{data_root}/ExcelOutput/EquipmentConfig.json")
    # Try to load skill descriptions
    try:
        esk_raw = load_json(f"{data_root}/ExcelOutput/EquipmentSkillConfig.json")
        skill_map: dict[int, dict] = {}
        for s in esk_raw:
            eid = s.get("SkillID")
            if eid and (eid not in skill_map or s.get("Level", 0) == 1):
                skill_map[eid] = s
    except FileNotFoundError:
        skill_map = {}

    lcs = []
    for eq in eq_raw:
        if not eq.get("Release", False):
            continue
        name = resolve(tm, eq["EquipmentName"])
        if not name:
            continue
        desc = strip_tags(resolve(tm, eq.get("EquipmentDesc", {}) or {}))
        stars = RARITY_STAR.get(eq["Rarity"], 3)
        path  = eq["AvatarBaseType"]

        skill_desc = ""
        sid = eq.get("SkillID")
        if sid and sid in skill_map:
            s = skill_map[sid]
            sname = resolve(tm, s.get("SkillName", {}))
            sdesc = strip_tags(resolve(tm, s.get("SkillDesc", {})))
            skill_desc = f"{sname}：{sdesc}" if sname else sdesc

        lcs.append({
            "id":    eq["EquipmentID"],
            "name":  name,
            "desc":  desc,
            "stars": stars,
            "path":  path,
            "skill": skill_desc,
        })

    lcs.sort(key=lambda c: (-c["stars"], c["path"], c["name"]))
    return lcs


def build_monsters(data_root: str, tm: dict) -> list:
    raw = load_json(f"{data_root}/ExcelOutput/MonsterConfig.json")
    seen: set[str] = set()
    monsters = []
    for m in raw:
        name = resolve(tm, m["MonsterName"])
        if not name or name in seen:
            continue
        seen.add(name)
        intro = strip_tags(resolve(tm, m.get("MonsterIntroduction", {})))
        weaknesses = m.get("StanceWeakList", [])
        monsters.append({
            "name":      name,
            "intro":     intro[:120],
            "weaknesses": weaknesses,
            "isElite":   bool(m.get("EliteGroup")),
        })
    monsters.sort(key=lambda m: (not m["isElite"], m["name"]))
    return monsters


def build_achievements(data_root: str, tm: dict) -> list:
    raw     = load_json(f"{data_root}/ExcelOutput/AchievementData.json")
    ser_raw = load_json(f"{data_root}/ExcelOutput/AchievementSeries.json")
    series_names = {s["SeriesID"]: resolve(tm, s["SeriesTitle"]) for s in ser_raw}

    achs = []
    for a in raw:
        title = resolve(tm, a["AchievementTitle"])
        desc  = strip_tags(resolve(tm, a["AchievementDesc"]))
        if not title:
            continue
        achs.append({
            "id":     a["AchievementID"],
            "series": series_names.get(a["SeriesID"], "其他"),
            "title":  title,
            "desc":   desc,
        })
    achs.sort(key=lambda a: (a["series"], a["title"]))
    return achs


# ───────────────────────────── HTML Template ──────────────────────────────

def render_html(characters, relic_sets, lightcones, monsters, achievements) -> str:
    # Precompute filter options
    paths    = sorted({c["path"]    for c in characters})
    elements = sorted({c["element"] for c in characters})

    chars_json  = json.dumps(characters,   ensure_ascii=False)
    relics_json = json.dumps(relic_sets,   ensure_ascii=False)
    lcs_json    = json.dumps(lightcones,   ensure_ascii=False)
    mons_json   = json.dumps(monsters,     ensure_ascii=False)
    achs_json   = json.dumps(achievements, ensure_ascii=False)

    path_zh_json    = json.dumps(PATH_ZH,      ensure_ascii=False)
    elem_zh_json    = json.dumps(ELEMENT_ZH,   ensure_ascii=False)
    elem_color_json = json.dumps(ELEMENT_COLOR, ensure_ascii=False)
    path_color_json = json.dumps(PATH_COLOR,   ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>星穹铁道数据看板</title>
<style>
:root {{
  --bg: #0d1117;
  --bg2: #161b22;
  --bg3: #21262d;
  --border: #30363d;
  --text: #e6edf3;
  --muted: #8b949e;
  --accent: #58a6ff;
  --gold: #e3b341;
  --silver: #c9d1d9;
  font-family: 'Segoe UI', system-ui, sans-serif;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--text); min-height: 100vh; }}

/* ── Nav ── */
nav {{
  position: sticky; top: 0; z-index: 100;
  background: rgba(13,17,23,.92); backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 0; padding: 0 1.5rem;
}}
.nav-brand {{
  font-size: 1.1rem; font-weight: 700; color: var(--gold);
  padding: 1rem 1rem 1rem 0; white-space: nowrap;
  text-shadow: 0 0 20px rgba(227,179,65,.4);
}}
.nav-tabs {{ display: flex; gap: 0; flex: 1; overflow-x: auto; }}
.nav-tab {{
  padding: .9rem 1.2rem; cursor: pointer; font-size: .9rem;
  color: var(--muted); border-bottom: 3px solid transparent;
  transition: all .2s; white-space: nowrap;
}}
.nav-tab:hover {{ color: var(--text); }}
.nav-tab.active {{ color: var(--accent); border-bottom-color: var(--accent); }}
.nav-stats {{ font-size: .8rem; color: var(--muted); padding: .9rem 0; white-space: nowrap; }}

/* ── Pages ── */
.page {{ display: none; padding: 1.5rem; max-width: 1400px; margin: 0 auto; }}
.page.active {{ display: block; }}

/* ── Filters ── */
.filters {{ display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 1.5rem; }}
.filter-btn {{
  padding: .35rem .8rem; border-radius: 20px; border: 1px solid var(--border);
  background: var(--bg2); color: var(--muted); cursor: pointer; font-size: .82rem;
  transition: all .15s;
}}
.filter-btn:hover {{ border-color: var(--accent); color: var(--text); }}
.filter-btn.active {{ background: var(--accent); border-color: var(--accent); color: #0d1117; font-weight: 600; }}
input[type=search], input[type=text] {{
  background: var(--bg2); border: 1px solid var(--border); border-radius: 8px;
  color: var(--text); padding: .4rem .9rem; font-size: .9rem; outline: none;
  transition: border-color .15s; width: 260px;
}}
input:focus {{ border-color: var(--accent); }}

/* ── Cards grid ── */
.cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px,1fr)); gap: 1rem; }}
.card {{
  background: var(--bg2); border: 1px solid var(--border); border-radius: 12px;
  padding: 1rem; cursor: pointer; transition: all .2s; position: relative; overflow: hidden;
}}
.card:hover {{ border-color: var(--accent); transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,.4); }}
.card-name {{ font-size: 1rem; font-weight: 600; margin-bottom: .3rem; }}
.card-sub  {{ font-size: .78rem; color: var(--muted); margin-bottom: .5rem; }}
.stars {{ color: var(--gold); font-size: .9rem; }}
.stars.s4 {{ color: #a78bfa; }}
.badge {{
  display: inline-block; font-size: .72rem; padding: .2rem .5rem;
  border-radius: 12px; font-weight: 600; margin: .15rem .1rem 0 0;
}}
.badge-path  {{ background: rgba(88,166,255,.15); color: var(--accent); border: 1px solid rgba(88,166,255,.3); }}
.card-accent-bar {{
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
}}

/* ── Detail modal ── */
.modal-overlay {{
  display: none; position: fixed; inset: 0; z-index: 200;
  background: rgba(0,0,0,.7); backdrop-filter: blur(4px);
  align-items: center; justify-content: center;
}}
.modal-overlay.open {{ display: flex; }}
.modal {{
  background: var(--bg2); border: 1px solid var(--border); border-radius: 16px;
  padding: 1.5rem; max-width: 680px; width: 95%; max-height: 88vh;
  overflow-y: auto; position: relative;
}}
.modal h2 {{ font-size: 1.4rem; margin-bottom: .25rem; }}
.modal-close {{
  position: absolute; top: 1rem; right: 1rem;
  background: none; border: none; color: var(--muted); font-size: 1.4rem;
  cursor: pointer; line-height: 1;
}}
.modal-close:hover {{ color: var(--text); }}
.section-title {{
  font-size: .8rem; font-weight: 700; letter-spacing: .08em;
  text-transform: uppercase; color: var(--muted); margin: 1rem 0 .5rem;
}}
.stat-grid {{ display: grid; grid-template-columns: repeat(3,1fr); gap: .4rem; }}
.stat-item {{
  background: var(--bg3); border-radius: 8px; padding: .4rem .6rem; font-size: .82rem;
}}
.stat-label {{ color: var(--muted); font-size: .72rem; }}
.skill-list, .eidolon-list {{ display: flex; flex-direction: column; gap: .5rem; }}
.skill-item, .eidolon-item {{
  background: var(--bg3); border-radius: 8px; padding: .6rem .8rem;
}}
.skill-name {{ font-weight: 600; font-size: .9rem; }}
.skill-tag  {{ font-size: .75rem; color: var(--accent); }}
.skill-desc {{ font-size: .8rem; color: var(--muted); margin-top: .25rem; line-height: 1.5; }}

/* ── Relic sets ── */
.relic-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px,1fr)); gap: 1rem; }}
.relic-card {{
  background: var(--bg2); border: 1px solid var(--border); border-radius: 12px; padding: 1rem;
}}
.relic-card h3 {{ font-size: 1rem; margin-bottom: .75rem; }}
.effect-item {{ background: var(--bg3); border-radius: 8px; padding: .5rem .7rem; margin-bottom: .4rem; }}
.effect-req {{ display: inline-block; font-size: .75rem; font-weight: 700; color: var(--gold); margin-bottom: .2rem; }}
.effect-props {{ font-size: .78rem; color: #58d68d; margin-bottom: .2rem; }}
.effect-desc {{ font-size: .78rem; color: var(--muted); line-height: 1.5; }}
.planar-badge {{
  display: inline-block; font-size: .7rem; padding: .15rem .4rem;
  background: rgba(227,179,65,.15); color: var(--gold); border-radius: 6px;
  border: 1px solid rgba(227,179,65,.3); margin-bottom: .5rem;
}}

/* ── Monster table ── */
.mon-search-row {{ display: flex; gap: .75rem; flex-wrap: wrap; align-items: center; }}
.mon-table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: .88rem; }}
.mon-table th {{ background: var(--bg3); padding: .5rem .8rem; text-align: left; font-size: .75rem; color: var(--muted); font-weight: 600; text-transform: uppercase; position: sticky; top: 60px; }}
.mon-table td {{ padding: .45rem .8rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
.mon-table tr:hover td {{ background: var(--bg3); }}
.elem-chip {{
  display: inline-block; font-size: .72rem; font-weight: 600;
  padding: .15rem .45rem; border-radius: 10px; margin: .1rem .1rem 0 0;
  border: 1px solid;
}}
.elite-marker {{ font-size: .7rem; color: var(--gold); margin-left: .4rem; }}

/* ── Achievement ── */
.ach-search-row {{ display: flex; gap: .75rem; flex-wrap: wrap; align-items: center; margin-bottom: .75rem; }}
.ach-series {{ font-size: .75rem; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: .06em; margin: 1.25rem 0 .4rem; }}
.ach-list {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: .5rem; }}
.ach-item {{
  background: var(--bg2); border: 1px solid var(--border); border-radius: 8px; padding: .6rem .8rem;
  font-size: .85rem;
}}
.ach-item-title {{ font-weight: 600; margin-bottom: .2rem; }}
.ach-item-desc  {{ font-size: .78rem; color: var(--muted); line-height: 1.4; }}

/* ── Overview ── */
.overview-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px,1fr)); gap: 1rem; margin-bottom: 2rem; }}
.overview-card {{
  background: var(--bg2); border: 1px solid var(--border); border-radius: 12px;
  padding: 1.2rem; text-align: center;
}}
.overview-num {{ font-size: 2rem; font-weight: 700; color: var(--accent); }}
.overview-label {{ font-size: .8rem; color: var(--muted); margin-top: .25rem; }}
.chart-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
.chart-box {{
  background: var(--bg2); border: 1px solid var(--border); border-radius: 12px; padding: 1rem;
}}
.chart-box h3 {{ font-size: .9rem; color: var(--muted); margin-bottom: .75rem; }}
.bar-row {{ display: flex; align-items: center; gap: .6rem; margin-bottom: .4rem; font-size: .82rem; }}
.bar-label {{ width: 70px; text-align: right; color: var(--muted); flex-shrink: 0; }}
.bar-outer {{ flex: 1; background: var(--bg3); border-radius: 4px; height: 16px; overflow: hidden; }}
.bar-inner {{ height: 100%; border-radius: 4px; transition: width .5s; }}
.bar-count {{ width: 28px; color: var(--text); flex-shrink: 0; }}

@media(max-width:600px) {{
  .chart-row {{ grid-template-columns: 1fr; }}
  .stat-grid {{ grid-template-columns: repeat(2,1fr); }}
}}
</style>
</head>
<body>

<nav>
  <div class="nav-brand">✦ 星穹铁道</div>
  <div class="nav-tabs">
    <div class="nav-tab active" onclick="showPage('overview',this)">总览</div>
    <div class="nav-tab" onclick="showPage('characters',this)">角色</div>
    <div class="nav-tab" onclick="showPage('relics',this)">遗器套装</div>
    <div class="nav-tab" onclick="showPage('lightcones',this)">光锥</div>
    <div class="nav-tab" onclick="showPage('monsters',this)">怪物弱点</div>
    <div class="nav-tab" onclick="showPage('achievements',this)">成就</div>
  </div>
  <div class="nav-stats" id="navStats"></div>
</nav>

<!-- OVERVIEW -->
<div class="page active" id="page-overview">
  <div class="overview-grid" id="overviewCards"></div>
  <div class="chart-row">
    <div class="chart-box"><h3>命途分布</h3><div id="chartPath"></div></div>
    <div class="chart-box"><h3>属性分布</h3><div id="chartElem"></div></div>
  </div>
</div>

<!-- CHARACTERS -->
<div class="page" id="page-characters">
  <div class="filters" id="charFilters"></div>
  <div class="cards" id="charGrid"></div>
</div>

<!-- RELICS -->
<div class="page" id="page-relics">
  <div class="filters" id="relicFilters"></div>
  <div class="relic-grid" id="relicGrid"></div>
</div>

<!-- LIGHTCONES -->
<div class="page" id="page-lightcones">
  <div class="filters" id="lcFilters"></div>
  <div class="cards" id="lcGrid"></div>
</div>

<!-- MONSTERS -->
<div class="page" id="page-monsters">
  <div class="mon-search-row">
    <input type="search" id="monSearch" placeholder="搜索怪物名称…" oninput="renderMonsters()">
    <div class="filters" id="monFilters" style="margin:0"></div>
  </div>
  <table class="mon-table">
    <thead><tr><th>名称</th><th>弱点</th><th>简介</th></tr></thead>
    <tbody id="monBody"></tbody>
  </table>
</div>

<!-- ACHIEVEMENTS -->
<div class="page" id="page-achievements">
  <div class="ach-search-row">
    <input type="search" id="achSearch" placeholder="搜索成就标题或描述…" oninput="renderAchievements()">
    <span id="achCount" style="font-size:.82rem;color:var(--muted)"></span>
  </div>
  <div id="achContainer"></div>
</div>

<!-- MODAL -->
<div class="modal-overlay" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal" id="modalContent">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <div id="modalBody"></div>
  </div>
</div>

<script>
const CHARS     = {chars_json};
const RELICS    = {relics_json};
const LCS       = {lcs_json};
const MONS      = {mons_json};
const ACHS      = {achs_json};
const PATH_ZH   = {path_zh_json};
const ELEM_ZH   = {elem_zh_json};
const ELEM_COLOR= {elem_color_json};
const PATH_COLOR= {path_color_json};

// ─── State ───
const state = {{
  charPath: 'all', charElem: 'all', charStars: 'all',
  relicType: 'all',
  lcPath: 'all', lcStars: 'all',
  monElem: 'all',
}};

// ─── Nav ───
function showPage(id, tab) {{
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('page-' + id).classList.add('active');
  tab.classList.add('active');
}}

// ─── Stars ───
function stars(n, rarity) {{
  const c = rarity >= 5 ? 'stars' : (rarity === 4 ? 'stars s4' : 'stars s3');
  return `<span class="${{c}}">${{'★'.repeat(n)}}</span>`;
}}

// ─── Overview ───
function renderOverview() {{
  const ov = document.getElementById('overviewCards');
  const entries = [
    [CHARS.length,       '角色'],
    [CHARS.filter(c=>c.stars===5).length, '5★角色'],
    [RELICS.length,      '遗器套装'],
    [LCS.length,         '光锥'],
    [MONS.length,        '怪物种类'],
    [ACHS.length,        '成就'],
  ];
  ov.innerHTML = entries.map(([n,l])=>`
    <div class="overview-card">
      <div class="overview-num">${{n}}</div>
      <div class="overview-label">${{l}}</div>
    </div>`).join('');

  // Path bar chart
  const pathCounts = {{}};
  CHARS.forEach(c => pathCounts[c.path] = (pathCounts[c.path]||0)+1);
  const maxP = Math.max(...Object.values(pathCounts));
  document.getElementById('chartPath').innerHTML =
    Object.entries(pathCounts).sort((a,b)=>b[1]-a[1]).map(([p,n])=>{{
      const color = PATH_COLOR[p] || '#58a6ff';
      const pct = Math.round(n/maxP*100);
      return `<div class="bar-row">
        <div class="bar-label">${{PATH_ZH[p]||p}}</div>
        <div class="bar-outer"><div class="bar-inner" style="width:${{pct}}%;background:${{color}}"></div></div>
        <div class="bar-count">${{n}}</div>
      </div>`;
    }}).join('');

  // Element bar chart
  const elemCounts = {{}};
  CHARS.forEach(c => elemCounts[c.element] = (elemCounts[c.element]||0)+1);
  const maxE = Math.max(...Object.values(elemCounts));
  document.getElementById('chartElem').innerHTML =
    Object.entries(elemCounts).sort((a,b)=>b[1]-a[1]).map(([e,n])=>{{
      const color = ELEM_COLOR[e] || '#58a6ff';
      const pct = Math.round(n/maxE*100);
      return `<div class="bar-row">
        <div class="bar-label">${{ELEM_ZH[e]||e}}</div>
        <div class="bar-outer"><div class="bar-inner" style="width:${{pct}}%;background:${{color}}"></div></div>
        <div class="bar-count">${{n}}</div>
      </div>`;
    }}).join('');

  document.getElementById('navStats').textContent =
    `${{CHARS.length}} 角色 · ${{RELICS.length}} 遗器 · ${{LCS.length}} 光锥 · ${{ACHS.length}} 成就`;
}}

// ─── Characters ───
function buildCharFilters() {{
  const paths = [...new Set(CHARS.map(c=>c.path))].sort();
  const elems = [...new Set(CHARS.map(c=>c.element))].sort();
  let html = '<input type="search" id="charSearch" placeholder="搜索角色…" oninput="renderChars()" style="margin-right:.5rem">';
  html += '<button class="filter-btn active" onclick="setFilter(\'charPath\',\'all\',this)">全部命途</button>';
  paths.forEach(p => html += `<button class="filter-btn" onclick="setFilter('charPath','${{p}}',this)">${{PATH_ZH[p]||p}}</button>`);
  html += '&nbsp;<button class="filter-btn active" onclick="setFilter(\'charElem\',\'all\',this)">全部属性</button>';
  elems.forEach(e => html += `<button class="filter-btn" style="border-color:${{ELEM_COLOR[e]}}22" onclick="setFilter('charElem','${{e}}',this)">${{ELEM_ZH[e]||e}}</button>`);
  html += '&nbsp;<button class="filter-btn active" onclick="setFilter(\'charStars\',\'all\',this)">全部稀有度</button>';
  html += '<button class="filter-btn" onclick="setFilter(\'charStars\',5,this)">5★</button>';
  html += '<button class="filter-btn" onclick="setFilter(\'charStars\',4,this)">4★</button>';
  document.getElementById('charFilters').innerHTML = html;
}}

function setFilter(key, val, btn) {{
  state[key] = val;
  // Update active button in group by finding siblings
  const parent = btn.parentElement;
  const sameGroup = [...parent.children].filter(b => b.classList.contains('filter-btn') &&
    b.getAttribute('onclick') && b.getAttribute('onclick').includes(`'${{key}}'`));
  sameGroup.forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (key.startsWith('char')) renderChars();
  else if (key.startsWith('relic')) renderRelics();
  else if (key.startsWith('lc')) renderLC();
  else if (key.startsWith('mon')) renderMonsters();
}}

function renderChars() {{
  const q = (document.getElementById('charSearch')?.value||'').toLowerCase();
  const filtered = CHARS.filter(c =>
    (state.charPath === 'all' || c.path === state.charPath) &&
    (state.charElem === 'all' || c.element === state.charElem) &&
    (state.charStars === 'all' || c.stars === state.charStars) &&
    (!q || c.name.includes(q) || (c.fullName||'').includes(q))
  );
  document.getElementById('charGrid').innerHTML = filtered.map(c => {{
    const col = ELEM_COLOR[c.element] || '#58a6ff';
    const pCol = PATH_COLOR[c.path] || '#58a6ff';
    return `<div class="card" onclick="showChar(${{c.id}})">
      <div class="card-accent-bar" style="background:linear-gradient(90deg,${{col}},${{pCol}})"></div>
      <div class="card-name">${{c.name}}</div>
      <div class="card-sub">${{c.fullName||''}}</div>
      ${{stars(c.stars,c.stars)}}
      <div style="margin-top:.4rem">
        <span class="badge badge-path">${{PATH_ZH[c.path]||c.path}}</span>
        <span class="badge" style="background:${{col}}22;color:${{col}};border:1px solid ${{col}}44">${{ELEM_ZH[c.element]||c.element}}</span>
      </div>
    </div>`;
  }}).join('');
}}

function showChar(id) {{
  const c = CHARS.find(x=>x.id===id);
  if (!c) return;
  const col = ELEM_COLOR[c.element] || '#58a6ff';
  let html = `<div style="border-bottom:1px solid var(--border);padding-bottom:1rem;margin-bottom:1rem">
    <h2>${{c.name}}</h2>
    <div style="font-size:.85rem;color:var(--muted);margin:.25rem 0">${{c.fullName||''}}</div>
    ${{stars(c.stars,c.stars)}}
    <div style="margin-top:.5rem">
      <span class="badge badge-path">${{PATH_ZH[c.path]||c.path}}</span>
      <span class="badge" style="background:${{col}}22;color:${{col}};border:1px solid ${{col}}44">${{ELEM_ZH[c.element]||c.element}}</span>
    </div>
  </div>`;

  if (c.stats && Object.keys(c.stats).length > 0) {{
    const s = c.stats;
    html += `<div class="section-title">基础属性参数（满突破阶段）</div>
    <div style="font-size:.75rem;color:var(--muted);margin-bottom:.5rem">HP/攻/防显示为基础值+每级成长，速度/暴击为固定值</div>
    <div class="stat-grid">
      <div class="stat-item"><div class="stat-label">生命值</div>${{s.hp_base||'—'}} <span style="color:var(--muted);font-size:.75rem">+${{s.hp_add}}/级</span></div>
      <div class="stat-item"><div class="stat-label">攻击力</div>${{s.atk_base||'—'}} <span style="color:var(--muted);font-size:.75rem">+${{s.atk_add}}/级</span></div>
      <div class="stat-item"><div class="stat-label">防御力</div>${{s.def_base||'—'}} <span style="color:var(--muted);font-size:.75rem">+${{s.def_add}}/级</span></div>
      <div class="stat-item"><div class="stat-label">速度</div>${{s.spd||'—'}}</div>
      <div class="stat-item"><div class="stat-label">基础暴击率</div>${{s.crit_rate}}%</div>
      <div class="stat-item"><div class="stat-label">基础暴击伤害</div>${{s.crit_dmg}}%</div>
    </div>`;
  }}

  if (c.skills && c.skills.length > 0) {{
    html += `<div class="section-title">技能</div><div class="skill-list">`;
    c.skills.forEach(sk => {{
      html += `<div class="skill-item">
        <div class="skill-name">${{sk.name}} <span class="skill-tag">${{sk.tag}}</span></div>
        <div class="skill-desc">${{sk.desc||''}}</div>
      </div>`;
    }});
    html += `</div>`;
  }}

  if (c.eidolons && c.eidolons.length > 0) {{
    html += `<div class="section-title">星魂</div><div class="eidolon-list">`;
    c.eidolons.forEach(e => {{
      html += `<div class="eidolon-item">
        <div class="skill-name">${{e.rank}}魂 · ${{e.name}}</div>
        <div class="skill-desc">${{e.desc||''}}</div>
      </div>`;
    }});
    html += `</div>`;
  }}

  document.getElementById('modalBody').innerHTML = html;
  document.getElementById('modal').classList.add('open');
}}

// ─── Relic Sets ───
function buildRelicFilters() {{
  let html = '<button class="filter-btn active" onclick="setFilter(\'relicType\',\'all\',this)">全部</button>';
  html += '<button class="filter-btn" onclick="setFilter(\'relicType\',\'relic\',this)">遗器套装</button>';
  html += '<button class="filter-btn" onclick="setFilter(\'relicType\',\'planar\',this)">位面饰品</button>';
  document.getElementById('relicFilters').innerHTML = html;
}}

function renderRelics() {{
  const filtered = RELICS.filter(r =>
    state.relicType === 'all' ||
    (state.relicType === 'planar' && r.isPlanar) ||
    (state.relicType === 'relic' && !r.isPlanar)
  );
  document.getElementById('relicGrid').innerHTML = filtered.map(r => {{
    const effHtml = r.effects.map(ef => {{
      const propHtml = ef.props.length > 0
        ? `<div class="effect-props">${{ef.props.join('  ')}}</div>` : '';
      const descHtml = ef.desc
        ? `<div class="effect-desc">${{ef.desc}}</div>` : '';
      return `<div class="effect-item">
        <span class="effect-req">${{ef.req}}件套</span>
        ${{propHtml}}${{descHtml}}
      </div>`;
    }}).join('');
    return `<div class="relic-card">
      ${{r.isPlanar ? '<span class="planar-badge">位面饰品</span>' : ''}}
      <h3>${{r.name}}</h3>
      ${{effHtml}}
    </div>`;
  }}).join('');
}}

// ─── Light Cones ───
function buildLCFilters() {{
  const paths = [...new Set(LCS.map(c=>c.path))].sort();
  let html = '<input type="search" id="lcSearch" placeholder="搜索光锥…" oninput="renderLC()" style="margin-right:.5rem">';
  html += '<button class="filter-btn active" onclick="setFilter(\'lcPath\',\'all\',this)">全部命途</button>';
  paths.forEach(p => html += `<button class="filter-btn" onclick="setFilter('lcPath','${{p}}',this)">${{PATH_ZH[p]||p}}</button>`);
  html += '&nbsp;<button class="filter-btn active" onclick="setFilter(\'lcStars\',\'all\',this)">全部稀有度</button>';
  [5,4,3].forEach(s => html += `<button class="filter-btn" onclick="setFilter('lcStars',${{s}},this)">${{s}}★</button>`);
  document.getElementById('lcFilters').innerHTML = html;
}}

function renderLC() {{
  const q = (document.getElementById('lcSearch')?.value||'').toLowerCase();
  const filtered = LCS.filter(c =>
    (state.lcPath  === 'all' || c.path  === state.lcPath) &&
    (state.lcStars === 'all' || c.stars === state.lcStars) &&
    (!q || c.name.toLowerCase().includes(q))
  );
  document.getElementById('lcGrid').innerHTML = filtered.map(c => {{
    const pCol = PATH_COLOR[c.path] || '#58a6ff';
    const starColor = c.stars===5 ? '#e3b341' : c.stars===4 ? '#a78bfa' : '#6b7280';
    return `<div class="card" onclick="showLC(${{c.id}})">
      <div class="card-accent-bar" style="background:${{pCol}}"></div>
      <div class="card-name">${{c.name}}</div>
      <div class="card-sub">${{PATH_ZH[c.path]||c.path}}</div>
      <span class="stars" style="color:${{starColor}}">${{'★'.repeat(c.stars)}}</span>
    </div>`;
  }}).join('');
}}

function showLC(id) {{
  const c = LCS.find(x=>x.id===id);
  if (!c) return;
  const pCol = PATH_COLOR[c.path] || '#58a6ff';
  const starColor = c.stars===5 ? '#e3b341' : c.stars===4 ? '#a78bfa' : '#6b7280';
  document.getElementById('modalBody').innerHTML = `
    <div style="border-bottom:1px solid var(--border);padding-bottom:1rem;margin-bottom:1rem">
      <h2>${{c.name}}</h2>
      <span class="stars" style="color:${{starColor}}">${{'★'.repeat(c.stars)}}</span>
      <span class="badge badge-path" style="margin-left:.5rem">${{PATH_ZH[c.path]||c.path}}</span>
    </div>
    ${{c.skill ? `<div class="section-title">光锥技能</div><div class="skill-item"><div class="skill-desc">${{c.skill}}</div></div>` : ''}}
    ${{c.desc ? `<div class="section-title">简介</div><p style="font-size:.85rem;color:var(--muted);line-height:1.6">${{c.desc}}</p>` : ''}}
  `;
  document.getElementById('modal').classList.add('open');
}}

// ─── Monsters ───
function buildMonFilters() {{
  const elems = ['Fire','Ice','Wind','Thunder','Physical','Quantum','Imaginary'];
  let html = '<button class="filter-btn active" onclick="setFilter(\'monElem\',\'all\',this)">全部弱点</button>';
  elems.forEach(e => {{
    const col = ELEM_COLOR[e];
    html += `<button class="filter-btn" style="border-color:${{col}}55" onclick="setFilter('monElem','${{e}}',this)">${{ELEM_ZH[e]}}</button>`;
  }});
  document.getElementById('monFilters').innerHTML = html;
}}

function renderMonsters() {{
  const q    = (document.getElementById('monSearch')?.value||'').toLowerCase();
  const elem = state.monElem;
  const filtered = MONS.filter(m =>
    (!q || m.name.toLowerCase().includes(q) || m.intro.toLowerCase().includes(q)) &&
    (elem === 'all' || m.weaknesses.includes(elem))
  );
  document.getElementById('monBody').innerHTML = filtered.map(m => {{
    const wkHtml = m.weaknesses.map(w => {{
      const col = ELEM_COLOR[w]||'#888';
      return `<span class="elem-chip" style="color:${{col}};border-color:${{col}}55;background:${{col}}15">${{ELEM_ZH[w]||w}}</span>`;
    }}).join('');
    const elite = m.isElite ? '<span class="elite-marker">★精英</span>' : '';
    return `<tr>
      <td><strong>${{m.name}}</strong>${{elite}}</td>
      <td>${{wkHtml||'—'}}</td>
      <td style="color:var(--muted)">${{m.intro||'—'}}</td>
    </tr>`;
  }}).join('');
}}

// ─── Achievements ───
function renderAchievements() {{
  const q = (document.getElementById('achSearch')?.value||'').toLowerCase();
  const filtered = ACHS.filter(a =>
    !q || a.title.toLowerCase().includes(q) || a.desc.toLowerCase().includes(q)
  );
  document.getElementById('achCount').textContent = `共 ${{filtered.length}} 条`;

  // Group by series
  const bySeries = {{}};
  filtered.forEach(a => {{
    (bySeries[a.series] = bySeries[a.series]||[]).push(a);
  }});
  let html = '';
  Object.entries(bySeries).sort().forEach(([ser, achs]) => {{
    html += `<div class="ach-series">${{ser}} (${{achs.length}})</div>
      <div class="ach-list">
        ${{achs.map(a=>`<div class="ach-item">
          <div class="ach-item-title">${{a.title}}</div>
          <div class="ach-item-desc">${{a.desc}}</div>
        </div>`).join('')}}
      </div>`;
  }});
  document.getElementById('achContainer').innerHTML = html;
}}

// ─── Modal ───
function closeModal() {{
  document.getElementById('modal').classList.remove('open');
}}
document.addEventListener('keydown', e => {{ if(e.key==='Escape') closeModal(); }});

// ─── Init ───
renderOverview();
buildCharFilters();
renderChars();
buildRelicFilters();
renderRelics();
buildLCFilters();
renderLC();
buildMonFilters();
renderMonsters();
renderAchievements();
</script>
</body>
</html>"""


# ─────────────────────────────── main ───────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="星穹铁道数据看板生成器")
    parser.add_argument("--data-root", default="..", help="游戏数据根目录（含 ExcelOutput/TextMap）")
    parser.add_argument("--output",    default="index.html", help="输出 HTML 文件路径")
    parser.add_argument("--lang",      default="CHS", help="语言：CHS/EN/JP/KR…")
    args = parser.parse_args()

    root = args.data_root
    lang = args.lang

    print(f"[1/6] 加载 TextMap ({lang})…")
    tm_path = f"{root}/TextMap/TextMap{lang}.json"
    if not os.path.exists(tm_path):
        print(f"  ⚠ 找不到 {tm_path}，回退到 TextMapCHS.json")
        tm_path = f"{root}/TextMap/TextMapCHS.json"
    tm = load_json(tm_path)
    print(f"      {len(tm):,} 条文本")

    print("[2/6] 处理角色数据…")
    characters = build_characters(root, tm)
    print(f"      {len(characters)} 名角色")

    print("[3/6] 处理遗器套装…")
    relic_sets = build_relic_sets(root, tm)
    print(f"      {len(relic_sets)} 套遗器")

    print("[4/6] 处理光锥…")
    lightcones = build_lightcones(root, tm)
    print(f"      {len(lightcones)} 把光锥")

    print("[5/6] 处理怪物数据…")
    monsters = build_monsters(root, tm)
    print(f"      {len(monsters)} 种怪物")

    print("[6/6] 处理成就数据…")
    achievements = build_achievements(root, tm)
    print(f"      {len(achievements)} 个成就")

    print(f"\n生成 HTML 看板 → {args.output}")
    html = render_html(characters, relic_sets, lightcones, monsters, achievements)

    out_path = args.output
    if not os.path.isabs(out_path):
        out_path = os.path.join(os.path.dirname(__file__), out_path)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"✓ 完成！文件大小: {size_kb:.0f} KB  →  {out_path}")
    print(f"\n用浏览器打开即可使用（无需服务器）：")
    print(f"  open {out_path}   # macOS")
    print(f"  start {out_path}  # Windows")
    print(f"  xdg-open {out_path}  # Linux")


if __name__ == "__main__":
    main()
