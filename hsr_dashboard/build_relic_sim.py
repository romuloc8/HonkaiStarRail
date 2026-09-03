"""
星穹铁道 · 遗器词条蒙特卡洛模拟器
精确还原游戏内遗器词条生成规则，模拟刷遗器概率分布。

用法: python build_relic_sim.py [--data-root ..] [--output hsr_relic_sim.html]
"""

import json
import os
import random
import argparse
from collections import defaultdict


PROPERTY_ZH = {
    "HPDelta":                   "生命值",
    "AttackDelta":               "攻击力",
    "DefenceDelta":              "防御力",
    "SpeedDelta":                "速度",
    "HPAddedRatio":              "生命值%",
    "AttackAddedRatio":          "攻击力%",
    "DefenceAddedRatio":         "防御力%",
    "CriticalChanceBase":        "暴击率",
    "CriticalDamageBase":        "暴击伤害",
    "StatusProbabilityBase":     "效果命中",
    "StatusResistanceBase":      "效果抵抗",
    "BreakDamageAddedRatioBase": "击破特攻",
}
PROPERTY_FORMAT = {
    "HPDelta": "flat", "AttackDelta": "flat", "DefenceDelta": "flat", "SpeedDelta": "flat",
    "HPAddedRatio": "pct", "AttackAddedRatio": "pct", "DefenceAddedRatio": "pct",
    "CriticalChanceBase": "pct", "CriticalDamageBase": "pct",
    "StatusProbabilityBase": "pct", "StatusResistanceBase": "pct",
    "BreakDamageAddedRatioBase": "pct",
}
PROPERTY_COLOR = {
    "HPDelta": "#5bb8d4", "AttackDelta": "#e8533e", "DefenceDelta": "#4db89b",
    "SpeedDelta": "#e3b341", "HPAddedRatio": "#5bb8d4", "AttackAddedRatio": "#e8533e",
    "DefenceAddedRatio": "#4db89b", "CriticalChanceBase": "#ff8c69",
    "CriticalDamageBase": "#c07de0", "StatusProbabilityBase": "#58a6ff",
    "StatusResistanceBase": "#8b949e", "BreakDamageAddedRatioBase": "#d4b84a",
}

MAX_INITIAL_SUBS = 4
LEVEL_UP_INTERVAL = 3


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_subaffix_pool(data_root):
    raw = load_json(f"{data_root}/ExcelOutput/RelicSubAffixConfig.json")
    subs = []
    for s in raw:
        subs.append({
            "property":  s["Property"],
            "base":      s["BaseValue"]["Value"],
            "step":      s["StepValue"]["Value"],
            "stepNum":   s["StepNum"],
            "groupID":   s["GroupID"],
        })
    return subs


def roll_one_relic(subs_pool, target_props: list, num_initial: int = 4) -> dict:
    """Simulate rolling one relic piece."""
    pool = list(subs_pool)
    random.shuffle(pool)

    # Pick 3 or 4 initial subs (equal weight)
    chosen = pool[:num_initial]
    result = []
    for sub in chosen:
        steps = random.randint(0, sub["stepNum"])
        val = sub["base"] + sub["step"] * steps
        result.append({"property": sub["property"], "value": val, "rolls": 1})

    # Level up to +15 (5 upgrades at levels 3,6,9,12,15)
    num_upgrades = 5
    if num_initial == 3:
        num_upgrades += 1  # extra sub unlocked at +3

    for _ in range(num_upgrades):
        chosen_sub = random.choice(result)
        steps = random.randint(0, chosen_sub.get("stepNum", 2) if "stepNum" in chosen_sub else 2)
        # Find original step value
        orig = next((s for s in subs_pool if s["property"] == chosen_sub["property"]), None)
        if orig:
            add = orig["base"] + orig["step"] * random.randint(0, orig["stepNum"])
            chosen_sub["value"] += add
            chosen_sub["rolls"] += 1

    # Calculate score: target props get weighted score
    score = 0
    for sub in result:
        if sub["property"] in target_props:
            # Normalize: count effective rolls
            score += sub["rolls"]

    return {"subs": result, "score": score}


def monte_carlo(subs_pool, target_props, n=10000):
    scores = defaultdict(int)
    for _ in range(n):
        r = roll_one_relic(subs_pool, target_props)
        scores[r["score"]] += 1
    return dict(sorted(scores.items()))


def render_html(subs_pool, properties_zh, property_format, property_color) -> str:
    subs_json = json.dumps(subs_pool, ensure_ascii=False)
    props_zh_json = json.dumps(properties_zh, ensure_ascii=False)
    fmt_json = json.dumps(property_format, ensure_ascii=False)
    color_json = json.dumps(property_color, ensure_ascii=False)

    all_props = [s["property"] for s in subs_pool]
    unique_props = list(dict.fromkeys(all_props))

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>星穹铁道 · 遗器词条模拟器</title>
<style>
:root {{
  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;
  --border:#30363d;--text:#e6edf3;--muted:#8b949e;--accent:#58a6ff;
  --green:#3fb950;--gold:#e3b341;--red:#f85149;
  font-family:'Segoe UI',system-ui,sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);min-height:100vh;padding:1.5rem 1rem}}
h1{{font-size:1.5rem;font-weight:800;
  background:linear-gradient(135deg,#e3b341,#7b68ee);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  margin-bottom:.25rem}}
.subtitle{{font-size:.85rem;color:var(--muted);margin-bottom:1.5rem}}
.layout{{display:grid;grid-template-columns:340px 1fr;gap:1.5rem;max-width:1100px;margin:0 auto}}
@media(max-width:750px){{.layout{{grid-template-columns:1fr}}}}

/* ── Config Panel ── */
.panel{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1.2rem}}
.panel h2{{font-size:.95rem;font-weight:700;margin-bottom:1rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}}
.prop-grid{{display:grid;grid-template-columns:1fr 1fr;gap:.4rem;margin-bottom:1rem}}
.prop-btn{{
  padding:.4rem .6rem;border-radius:8px;border:1px solid var(--border);
  background:var(--bg3);color:var(--muted);cursor:pointer;font-size:.8rem;
  text-align:left;transition:all .15s;display:flex;align-items:center;gap:.4rem
}}
.prop-btn:hover{{border-color:var(--accent)}}
.prop-btn.selected{{border-color:var(--green);background:rgba(63,185,80,.1);color:var(--green)}}
.prop-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
label{{display:block;font-size:.82rem;color:var(--muted);margin:.75rem 0 .3rem}}
input[type=range]{{width:100%;accent-color:var(--accent)}}
.range-val{{font-size:.82rem;color:var(--text);font-weight:600}}
.sim-btn{{
  width:100%;padding:.65rem;border:none;border-radius:8px;
  background:var(--accent);color:#0d1117;font-size:.95rem;font-weight:700;
  cursor:pointer;margin-top:.75rem;transition:opacity .15s
}}
.sim-btn:hover{{opacity:.85}}
.sim-btn:disabled{{opacity:.4;cursor:not-allowed}}

/* ── Results Panel ── */
.results-panel{{display:flex;flex-direction:column;gap:1rem}}
.stat-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:.75rem}}
.stat-card{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:.9rem;text-align:center}}
.stat-num{{font-size:1.5rem;font-weight:700;color:var(--accent)}}
.stat-label{{font-size:.75rem;color:var(--muted);margin-top:.2rem}}

/* ── Distribution chart ── */
.chart-wrap{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1.2rem}}
.chart-wrap h2{{font-size:.9rem;font-weight:600;color:var(--muted);margin-bottom:1rem}}
.dist-chart{{display:flex;align-items:flex-end;gap:3px;height:180px;padding:0 4px}}
.dist-bar{{
  flex:1;min-width:12px;border-radius:3px 3px 0 0;
  background:var(--accent);position:relative;cursor:pointer;
  transition:opacity .15s;
}}
.dist-bar:hover{{opacity:.7}}
.dist-bar .bar-tooltip{{
  display:none;position:absolute;bottom:100%;left:50%;transform:translateX(-50%);
  background:var(--bg3);border:1px solid var(--border);border-radius:6px;
  padding:.3rem .5rem;font-size:.75rem;white-space:nowrap;z-index:10;margin-bottom:4px
}}
.dist-bar:hover .bar-tooltip{{display:block}}
.dist-labels{{display:flex;gap:3px;padding:4px 4px 0;font-size:.7rem;color:var(--muted)}}
.dist-label{{flex:1;text-align:center}}

/* ── Individual roll ── */
.roll-section{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1.2rem}}
.roll-section h2{{font-size:.9rem;color:var(--muted);font-weight:600;margin-bottom:.75rem}}
.roll-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:.75rem;margin-bottom:.75rem}}
.roll-item{{background:var(--bg3);border-radius:8px;padding:.6rem .8rem;display:flex;align-items:center;gap:.6rem}}
.roll-prop{{font-size:.82rem;color:var(--muted)}}
.roll-val{{font-weight:700;font-size:.95rem}}
.roll-stars{{color:var(--gold);font-size:.75rem;margin-top:.15rem}}
.roll-btn{{
  padding:.5rem 1.1rem;border:none;border-radius:8px;
  background:var(--bg3);color:var(--text);font-size:.88rem;
  cursor:pointer;border:1px solid var(--border);
}}
.roll-btn:hover{{border-color:var(--accent)}}
.target-badge{{
  display:inline-block;font-size:.7rem;padding:.1rem .3rem;
  background:rgba(63,185,80,.2);color:var(--green);border-radius:4px;margin-left:.3rem
}}

/* ── Probability table ── */
.prob-table{{width:100%;border-collapse:collapse;font-size:.82rem;margin-top:.5rem}}
.prob-table th{{background:var(--bg3);padding:.4rem .6rem;text-align:left;color:var(--muted);font-size:.75rem}}
.prob-table td{{padding:.35rem .6rem;border-bottom:1px solid var(--border)}}
.prob-bar-cell{{width:120px}}
.mini-bar{{height:8px;background:var(--accent);border-radius:2px;display:inline-block}}
.progress-overlay{{
  display:none;position:fixed;inset:0;z-index:200;
  background:rgba(0,0,0,.6);backdrop-filter:blur(4px);
  align-items:center;justify-content:center;flex-direction:column;gap:.75rem
}}
.progress-overlay.show{{display:flex}}
.progress-text{{font-size:1.1rem;font-weight:600}}
.progress-bar-outer{{width:280px;height:8px;background:var(--bg3);border-radius:4px;overflow:hidden}}
.progress-bar-inner{{height:100%;background:var(--accent);border-radius:4px;transition:width .1s}}
</style>
</head>
<body>

<div style="max-width:1100px;margin:0 auto">
  <h1>遗器词条蒙特卡洛模拟器</h1>
  <p class="subtitle">基于游戏实际词条权重数据模拟刷遗器概率，精确到词条步长</p>

  <div class="layout">
    <!-- Config -->
    <div class="panel">
      <h2>目标词条（多选）</h2>
      <div class="prop-grid" id="propGrid"></div>

      <label>模拟次数 <span class="range-val" id="simNumVal">10,000</span></label>
      <input type="range" id="simNum" min="1000" max="100000" step="1000" value="10000"
        oninput="document.getElementById('simNumVal').textContent=Number(this.value).toLocaleString()">

      <label>初始词条数</label>
      <div style="display:flex;gap:.5rem;margin-bottom:.25rem">
        <button class="prop-btn selected" id="sub3btn" onclick="setSubs(3)" style="flex:1;justify-content:center">3词条开始</button>
        <button class="prop-btn"          id="sub4btn" onclick="setSubs(4)" style="flex:1;justify-content:center">4词条开始</button>
      </div>
      <div style="font-size:.75rem;color:var(--muted)">3词条：升至+3时解锁第4词条</div>

      <button class="sim-btn" id="simBtn" onclick="runSimulation()">▶ 开始模拟</button>
    </div>

    <!-- Results -->
    <div class="results-panel" id="resultsPanel">
      <div class="stat-row" id="statRow">
        <div class="stat-card"><div class="stat-num" id="statAvg">—</div><div class="stat-label">平均目标词条数</div></div>
        <div class="stat-card"><div class="stat-num" id="statP50">—</div><div class="stat-label">中位数</div></div>
        <div class="stat-card"><div class="stat-num" id="statP90">—</div><div class="stat-label">90% 分位数</div></div>
        <div class="stat-card"><div class="stat-num" id="statBest">—</div><div class="stat-label">最高记录</div></div>
      </div>

      <div class="chart-wrap">
        <h2>词条数分布（<span id="chartTitle">请选择词条并模拟</span>）</h2>
        <div class="dist-chart" id="distChart"><div style="color:var(--muted);font-size:.85rem;padding:1rem">运行模拟后显示分布图</div></div>
        <div class="dist-labels" id="distLabels"></div>
      </div>

      <div class="roll-section">
        <h2>🎲 单件试算</h2>
        <div class="roll-grid" id="rollGrid"><div style="color:var(--muted);font-size:.85rem">点击下方按钮随机生成一件遗器</div></div>
        <div style="display:flex;gap:.5rem;align-items:center">
          <button class="roll-btn" onclick="rollOne()">🎲 再滚一件</button>
          <span style="font-size:.8rem;color:var(--muted)" id="rollScore"></span>
        </div>
      </div>

      <div class="chart-wrap">
        <h2>各词条期望出现次数</h2>
        <table class="prob-table" id="probTable">
          <tr><th>词条</th><th>期望次数</th><th class="prob-bar-cell">概率分布</th></tr>
        </table>
      </div>
    </div>
  </div>
</div>

<!-- Progress overlay -->
<div class="progress-overlay" id="progressOverlay">
  <div class="progress-text" id="progressText">模拟中…</div>
  <div class="progress-bar-outer"><div class="progress-bar-inner" id="progressBar" style="width:0%"></div></div>
</div>

<script>
const SUBS = {subs_json};
const PROPS_ZH = {props_zh_json};
const PROP_FMT = {fmt_json};
const PROP_COLOR = {color_json};

let selectedProps = ['CriticalChanceBase', 'CriticalDamageBase', 'AttackAddedRatio', 'SpeedDelta'];
let numInitialSubs = 4;
let lastScores = null;

// ── Build prop selector ──
const allProps = [...new Set(SUBS.map(s => s.property))];
const propGrid = document.getElementById('propGrid');
propGrid.innerHTML = allProps.map(p => `
  <button class="prop-btn ${{selectedProps.includes(p)?'selected':''}}" id="pbtn-${{p}}"
    onclick="toggleProp('${{p}}')">
    <div class="prop-dot" style="background:${{PROP_COLOR[p]||'#888'}}"></div>
    ${{PROPS_ZH[p]||p}}
  </button>`).join('');

function toggleProp(p) {{
  if (selectedProps.includes(p)) {{
    selectedProps = selectedProps.filter(x => x !== p);
  }} else {{
    selectedProps.push(p);
  }}
  document.getElementById('pbtn-' + p)?.classList.toggle('selected', selectedProps.includes(p));
}}

function setSubs(n) {{
  numInitialSubs = n;
  document.getElementById('sub3btn').classList.toggle('selected', n===3);
  document.getElementById('sub4btn').classList.toggle('selected', n===4);
}}

// ── Relic rolling logic (JS) ──
function rollRelic(targetProps, numInit) {{
  const pool = [...SUBS];
  for (let i = pool.length-1; i > 0; i--) {{
    const j = Math.floor(Math.random()*(i+1));
    [pool[i],pool[j]] = [pool[j],pool[i]];
  }}
  const chosen = pool.slice(0, numInit);
  const result = chosen.map(s => {{
    const steps = Math.floor(Math.random()*(s.stepNum+1));
    return {{ property: s.property, value: s.base + s.step*steps, rolls: 1, stepNum: s.stepNum, base: s.base, step: s.step }};
  }});

  // +3 unlock if starting with 3
  let upgrades = 5;
  if (numInit === 3) {{
    // unlock 4th sub at +3
    const extra = pool[3];
    const steps = Math.floor(Math.random()*(extra.stepNum+1));
    result.push({{ property: extra.property, value: extra.base + extra.step*steps, rolls: 1, stepNum: extra.stepNum, base: extra.base, step: extra.step }});
    upgrades = 5; // still 5 total upgrades after +3 to +15
  }}

  for (let i = 0; i < upgrades; i++) {{
    const sub = result[Math.floor(Math.random()*result.length)];
    const steps = Math.floor(Math.random()*(sub.stepNum+1));
    sub.value += sub.base + sub.step * steps;
    sub.rolls++;
  }}

  let score = 0;
  result.forEach(s => {{ if (targetProps.includes(s.property)) score += s.rolls; }});
  return {{ subs: result, score }};
}}

// ── Monte Carlo simulation ──
async function runSimulation() {{
  if (!selectedProps.length) {{ alert('请至少选择一个目标词条！'); return; }}
  const n = parseInt(document.getElementById('simNum').value);
  const btn = document.getElementById('simBtn');
  btn.disabled = true;

  const overlay = document.getElementById('progressOverlay');
  overlay.classList.add('show');

  const scores = {{}};
  const CHUNK = 1000;
  for (let done = 0; done < n; done += CHUNK) {{
    const end = Math.min(done+CHUNK, n);
    for (let i = done; i < end; i++) {{
      const r = rollRelic(selectedProps, numInitialSubs);
      scores[r.score] = (scores[r.score]||0) + 1;
    }}
    const pct = Math.round((done+CHUNK)/n*100);
    document.getElementById('progressBar').style.width = pct + '%';
    document.getElementById('progressText').textContent = `模拟中… ${{done+CHUNK >= n ? n : done+CHUNK}}/${{n}}`;
    await new Promise(r => setTimeout(r, 0));
  }}

  overlay.classList.remove('show');
  btn.disabled = false;
  lastScores = scores;
  renderResults(scores, n);
  rollOne(); // Show a sample roll
}}

function renderResults(scores, n) {{
  // Stats
  const allVals = [];
  Object.entries(scores).forEach(([k,v]) => {{
    for (let i=0; i<v; i++) allVals.push(parseInt(k));
  }});
  allVals.sort((a,b)=>a-b);
  const avg = (allVals.reduce((s,v)=>s+v,0)/allVals.length).toFixed(2);
  const p50 = allVals[Math.floor(allVals.length*.5)];
  const p90 = allVals[Math.floor(allVals.length*.9)];
  const best = allVals[allVals.length-1];

  document.getElementById('statAvg').textContent = avg;
  document.getElementById('statP50').textContent = p50;
  document.getElementById('statP90').textContent = p90;
  document.getElementById('statBest').textContent = best;

  // Chart
  const maxScore = Math.max(...Object.keys(scores).map(Number));
  const maxCount = Math.max(...Object.values(scores));
  const chart = document.getElementById('distChart');
  const labels = document.getElementById('distLabels');
  chart.innerHTML = '';
  labels.innerHTML = '';

  for (let s = 0; s <= maxScore; s++) {{
    const cnt = scores[s] || 0;
    const pct = cnt/n*100;
    const barH = Math.round(cnt/maxCount*160);
    const bar = document.createElement('div');
    bar.className = 'dist-bar';
    bar.style.height = barH + 'px';
    bar.style.background = s >= Math.round(best*.7) ? 'var(--gold)' : 'var(--accent)';
    bar.innerHTML = `<div class="bar-tooltip">${{s}}次目标词条<br>${{cnt.toLocaleString()}}件 (${{pct.toFixed(1)}}%)</div>`;
    chart.appendChild(bar);

    const lbl = document.createElement('div');
    lbl.className = 'dist-label';
    lbl.textContent = s;
    labels.appendChild(lbl);
  }}

  document.getElementById('chartTitle').textContent =
    `${{selectedProps.map(p=>PROPS_ZH[p]||p).join(' + ')}}，共 ${{n.toLocaleString()}} 次`;

  // Probability table for each sub
  const subExpected = {{}};
  allProps.forEach(p => {{ subExpected[p] = 0; }});
  // Compute from simulation
  const perRoll = {{}};
  allProps.forEach(p => {{ perRoll[p] = 0; }});
  // Run 1000 quick rolls to estimate
  for (let i=0; i<2000; i++) {{
    const r = rollRelic(selectedProps, numInitialSubs);
    r.subs.forEach(s => {{ perRoll[s.property] = (perRoll[s.property]||0) + s.rolls; }});
  }}
  const totalRolls = Object.values(perRoll).reduce((a,b)=>a+b,0);
  const probTable = document.getElementById('probTable');
  const rows = allProps.map(p => [p, perRoll[p]/2000]).sort((a,b)=>b[1]-a[1]);
  const maxExp = Math.max(...rows.map(r=>r[1]));
  probTable.innerHTML = '<tr><th>词条</th><th>期望获得次数</th><th class="prob-bar-cell">相对概率</th></tr>' +
    rows.map(([p, exp]) => {{
      const isTarget = selectedProps.includes(p);
      const barW = Math.round(exp/maxExp*100);
      const col = PROP_COLOR[p] || '#58a6ff';
      return `<tr>
        <td><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${{col}};margin-right:.4rem"></span>
          ${{PROPS_ZH[p]||p}} ${{isTarget ? '<span class="target-badge">目标</span>' : ''}}</td>
        <td style="font-weight:${{isTarget?'700':'400'}};color:${{isTarget?'var(--green)':'var(--text)'}}">${{exp.toFixed(2)}}</td>
        <td><div class="mini-bar" style="width:${{barW}}%;background:${{col}}"></div></td>
      </tr>`;
    }}).join('');
}}

function rollOne() {{
  if (!selectedProps.length) {{ alert('请先选择目标词条！'); return; }}
  const r = rollRelic(selectedProps, numInitialSubs);
  const grid = document.getElementById('rollGrid');
  grid.innerHTML = r.subs.map(s => {{
    const isTarget = selectedProps.includes(s.property);
    const col = PROP_COLOR[s.property] || '#888';
    const fmt = PROP_FMT[s.property] === 'pct'
      ? (s.value*100).toFixed(1)+'%'
      : Math.round(s.value).toString();
    return `<div class="roll-item" style="border:1px solid ${{isTarget?'var(--green)':col+'44'}}">
      <div style="width:10px;height:10px;border-radius:50%;background:${{col}};flex-shrink:0"></div>
      <div>
        <div class="roll-prop">${{PROPS_ZH[s.property]||s.property}}${{isTarget?'<span class="target-badge">✓</span>':''}}</div>
        <div class="roll-val" style="color:${{isTarget?'var(--green)':col}}">${{fmt}}</div>
        <div class="roll-stars">${{'●'.repeat(s.rolls)}} ${{s.rolls}}次强化</div>
      </div>
    </div>`;
  }}).join('');

  const scoreEl = document.getElementById('rollScore');
  const isGood = r.score >= 5;
  scoreEl.innerHTML = `得分：<strong style="color:${{isGood?'var(--gold)':'var(--text)'}}">${{r.score}}</strong> 次目标词条${{isGood?' 🎉':''}}`;
}}
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="..")
    parser.add_argument("--output", default="hsr_relic_sim.html")
    args = parser.parse_args()

    print("构建遗器词条数据…")
    subs = build_subaffix_pool(args.data_root)
    print(f"  {len(subs)} 种词条定义")

    html = render_html(subs, PROPERTY_ZH, PROPERTY_FORMAT, PROPERTY_COLOR)
    out = args.output if os.path.isabs(args.output) else os.path.join(os.path.dirname(__file__), args.output)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    size_kb = os.path.getsize(out) / 1024
    print(f"✓ 生成完毕 → {out}  ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
