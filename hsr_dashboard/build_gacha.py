"""
星穹铁道 · UIGF/SRGF 抽卡记录分析器
接受玩家上传的标准 SRGF/UIGF v4.0 格式 JSON，结合游戏内真实保底数据，
生成完整的抽卡统计报告（纯前端，不上传服务器，100% 隐私安全）。

SRGF/UIGF 标准: https://uigf.org/
用法: python build_gacha.py [--data-root ..] [--output hsr_gacha.html]
"""

import json
import os
import argparse


PATH_ZH = {
    "Knight": "存护", "Rogue": "巡猎", "Mage": "智识",
    "Warrior": "毁灭", "Priest": "丰饶", "Warlock": "虚无",
    "Shaman": "同谐", "Elation": "欢愉", "Memory": "记忆",
}
ELEMENT_COLOR = {
    "Fire": "#e8533e", "Ice": "#5bb8d4", "Wind": "#4db89b",
    "Thunder": "#c07de0", "Physical": "#a0a0b0",
    "Quantum": "#7b68ee", "Imaginary": "#d4b84a",
}

GACHA_TYPES = {
    "11": {"name": "限定角色跃迁", "hard_pity": 90, "soft_pity": 74, "guarantee": "50/50", "color": "#c07de0"},
    "12": {"name": "限定光锥跃迁", "hard_pity": 80, "soft_pity": 66, "guarantee": "75/25", "color": "#e3b341"},
    "1":  {"name": "常驻跃迁",     "hard_pity": 90, "soft_pity": 74, "guarantee": "无",    "color": "#58a6ff"},
    "2":  {"name": "新手跃迁",     "hard_pity": 50, "soft_pity": 40, "guarantee": "无",    "color": "#4db89b"},
}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_characters(data_root, tm):
    raw = load_json(f"{data_root}/ExcelOutput/AvatarConfig.json")
    chars = {}
    for av in raw:
        name = tm.get(str(av["AvatarName"]["Hash"]), "")
        if not name:
            continue
        chars[name] = {
            "id":      av["AvatarID"],
            "path":    av["AvatarBaseType"],
            "element": av["DamageType"],
            "stars":   5 if "Type5" in av["Rarity"] else 4,
        }
    return chars


def render_html(char_data: dict) -> str:
    char_json      = json.dumps(char_data,    ensure_ascii=False)
    path_zh_json   = json.dumps(PATH_ZH,      ensure_ascii=False)
    elem_col_json  = json.dumps(ELEMENT_COLOR, ensure_ascii=False)
    gacha_json     = json.dumps(GACHA_TYPES,   ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>星穹铁道 · 抽卡分析器</title>
<style>
:root {{
  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;
  --border:#30363d;--text:#e6edf3;--muted:#8b949e;--accent:#58a6ff;
  --gold:#e3b341;--green:#3fb950;--red:#f85149;--purple:#c07de0;
  font-family:'Segoe UI',system-ui,sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);min-height:100vh;padding:1.5rem 1rem}}
.wrap{{max-width:1100px;margin:0 auto}}

/* ── Header ── */
header{{text-align:center;margin-bottom:2rem}}
header h1{{font-size:1.6rem;font-weight:800;
  background:linear-gradient(135deg,#e3b341,#c07de0);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}}
header p{{font-size:.85rem;color:var(--muted);margin-top:.3rem}}

/* ── Upload area ── */
.upload-area{{
  border:2px dashed var(--border);border-radius:16px;
  padding:3rem 2rem;text-align:center;cursor:pointer;
  transition:all .2s;background:var(--bg2);
}}
.upload-area:hover,.upload-area.drag-over{{
  border-color:var(--accent);background:rgba(88,166,255,.05)
}}
.upload-icon{{font-size:2.5rem;margin-bottom:.75rem}}
.upload-title{{font-size:1rem;font-weight:600;margin-bottom:.4rem}}
.upload-sub{{font-size:.82rem;color:var(--muted);line-height:1.6}}
.upload-btn{{
  display:inline-block;margin-top:1rem;padding:.5rem 1.2rem;
  background:var(--accent);color:#0d1117;border:none;border-radius:8px;
  font-size:.9rem;font-weight:600;cursor:pointer
}}
#fileInput{{display:none}}
.paste-area{{
  width:100%;min-height:120px;background:var(--bg3);border:1px solid var(--border);
  border-radius:8px;color:var(--text);font-size:.82rem;padding:.75rem;
  resize:vertical;outline:none;margin-top:1rem;font-family:monospace;
  transition:border-color .15s
}}
.paste-area:focus{{border-color:var(--accent)}}
.parse-btn{{
  display:block;width:100%;margin-top:.75rem;padding:.65rem;
  background:var(--green);color:#0d1117;border:none;border-radius:8px;
  font-size:.95rem;font-weight:700;cursor:pointer;
}}
.parse-btn:hover{{opacity:.85}}
.error-msg{{color:var(--red);font-size:.85rem;margin-top:.5rem;display:none}}

/* ── Stats layout ── */
.results{{display:none;margin-top:1.5rem}}

/* Banner tabs */
.banner-tabs{{display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:1.2rem}}
.banner-tab{{
  padding:.4rem .9rem;border-radius:20px;border:1px solid var(--border);
  background:var(--bg2);color:var(--muted);cursor:pointer;font-size:.82rem;
  transition:all .15s
}}
.banner-tab.active{{font-weight:700;color:#0d1117}}

/* Overview cards */
.overview-row{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:.75rem;margin-bottom:1.5rem}}
.ov-card{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1rem;text-align:center}}
.ov-num{{font-size:1.8rem;font-weight:700;color:var(--accent)}}
.ov-label{{font-size:.75rem;color:var(--muted);margin-top:.2rem}}
.ov-sub{{font-size:.78rem;margin-top:.15rem}}

/* Pity gauge */
.pity-section{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1rem;margin-bottom:1rem}}
.pity-section h3{{font-size:.85rem;font-weight:600;color:var(--muted);margin-bottom:.75rem;text-transform:uppercase;letter-spacing:.06em}}
.pity-gauge{{margin-bottom:.75rem}}
.pity-label{{display:flex;justify-content:space-between;font-size:.82rem;margin-bottom:.3rem}}
.pity-bar-outer{{background:var(--bg3);border-radius:4px;height:20px;overflow:hidden;position:relative}}
.pity-bar-inner{{height:100%;border-radius:4px;transition:width .5s}}
.pity-bar-soft{{
  position:absolute;top:0;height:100%;border-left:2px dashed rgba(255,255,255,.3);
  pointer-events:none;
}}
.pity-text{{font-size:.75rem;color:var(--muted);text-align:right;margin-top:.2rem}}

/* 5★ history */
.five-star-list{{display:flex;flex-direction:column;gap:.4rem}}
.five-star-item{{
  display:flex;align-items:center;gap:.75rem;
  background:var(--bg3);border-radius:8px;padding:.5rem .75rem;
  font-size:.85rem;
}}
.five-star-name{{font-weight:600;flex:1}}
.five-star-pulls{{
  font-size:.78rem;padding:.15rem .5rem;border-radius:10px;font-weight:600
}}
.pull-count-lucky  {{background:rgba(63,185,80,.15);color:var(--green)}}
.pull-count-normal {{background:rgba(88,166,255,.15);color:var(--accent)}}
.pull-count-unlucky{{background:rgba(248,81,73,.15);color:var(--red)}}
.guaranteed-badge{{font-size:.72rem;padding:.1rem .4rem;background:rgba(192,125,224,.2);color:var(--purple);border-radius:6px}}

/* Pull timeline */
.timeline-wrap{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1rem;margin-top:1rem}}
.timeline-wrap h3{{font-size:.85rem;font-weight:600;color:var(--muted);margin-bottom:.75rem;text-transform:uppercase;letter-spacing:.06em}}
.timeline{{display:flex;align-items:flex-end;gap:2px;height:80px;overflow-x:auto;padding-bottom:4px}}
.t-bar{{
  min-width:4px;flex-shrink:0;border-radius:2px 2px 0 0;cursor:pointer;
  position:relative;transition:opacity .15s
}}
.t-bar:hover{{opacity:.7}}
.t-bar .t-tip{{
  display:none;position:absolute;bottom:100%;left:50%;transform:translateX(-50%);
  background:var(--bg3);border:1px solid var(--border);border-radius:6px;
  padding:.2rem .4rem;font-size:.7rem;white-space:nowrap;z-index:10;margin-bottom:2px
}}
.t-bar:hover .t-tip{{display:block}}

/* Luck meter */
.luck-meter{{
  display:flex;align-items:center;gap:1rem;
  background:var(--bg2);border:1px solid var(--border);border-radius:12px;
  padding:1rem 1.2rem;margin-bottom:1rem;
}}
.luck-dial{{font-size:2.5rem}}
.luck-text h4{{font-size:1rem;font-weight:700}}
.luck-text p{{font-size:.82rem;color:var(--muted);margin-top:.2rem}}

@media(max-width:550px){{
  .overview-row{{grid-template-columns:repeat(2,1fr)}}
}}
</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>⬡ 跃迁记录分析器</h1>
  <p>上传 SRGF / UIGF v4.0 格式的抽卡记录 JSON，完全在本地分析，不发送任何数据</p>
</header>

<!-- Upload -->
<div class="upload-area" id="uploadArea"
  ondragover="event.preventDefault();this.classList.add('drag-over')"
  ondragleave="this.classList.remove('drag-over')"
  ondrop="onDrop(event)">
  <div class="upload-icon">📂</div>
  <div class="upload-title">拖拽或点击上传 SRGF/UIGF JSON 文件</div>
  <div class="upload-sub">
    支持 SRGF v1.0 和 UIGF v4.0 格式<br>
    可从星穹铁道助手、Hakush、SRGF导出工具等获取
  </div>
  <label class="upload-btn" onclick="document.getElementById('fileInput').click()">选择文件</label>
  <input type="file" id="fileInput" accept=".json" onchange="onFileSelect(event)">
</div>

<div style="text-align:center;margin:.75rem 0;color:var(--muted);font-size:.82rem">— 或直接粘贴 JSON —</div>
<textarea class="paste-area" id="pasteArea" placeholder='{{"info":{{...}},"hkrpg":[...]}}'></textarea>
<button class="parse-btn" onclick="parseInput()">分析抽卡记录</button>
<div class="error-msg" id="errorMsg"></div>

<!-- Results -->
<div class="results" id="results">
  <div class="banner-tabs" id="bannerTabs"></div>
  <div id="bannerContent"></div>
</div>

</div>

<script>
const CHAR_DATA  = {char_json};
const PATH_ZH    = {path_zh_json};
const ELEM_COLOR = {elem_col_json};
const GACHA_INFO = {gacha_json};

let allData = null;
let activeBanner = null;

// ── File input ──
function onDrop(e) {{
  e.preventDefault();
  document.getElementById('uploadArea').classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) readFile(file);
}}
function onFileSelect(e) {{
  const file = e.target.files[0];
  if (file) readFile(file);
}}
function readFile(file) {{
  const reader = new FileReader();
  reader.onload = ev => {{
    document.getElementById('pasteArea').value = ev.target.result;
    parseInput();
  }};
  reader.readAsText(file, 'utf-8');
}}

// ── Parse JSON ──
function parseInput() {{
  const raw = document.getElementById('pasteArea').value.trim();
  const errEl = document.getElementById('errorMsg');
  errEl.style.display = 'none';
  if (!raw) {{ showError('请先粘贴或上传 JSON 文件'); return; }}

  let data;
  try {{ data = JSON.parse(raw); }} catch(e) {{ showError('JSON 格式错误：' + e.message); return; }}

  // Detect format
  let pulls = [];
  if (data.hkrpg) {{
    // UIGF v4.0
    for (const uid_data of data.hkrpg) {{
      pulls = pulls.concat((uid_data.list || []).map(p => ({{...p, uid: uid_data.uid}})));
    }}
  }} else if (data.list) {{
    // SRGF v1.0 or older UIGF
    pulls = data.list;
  }} else {{
    showError('无法识别格式。请确认是 SRGF v1.0 或 UIGF v4.0 格式。');
    return;
  }}

  if (!pulls.length) {{ showError('记录为空'); return; }}

  allData = pulls;
  renderResults(pulls);
}}

function showError(msg) {{
  const el = document.getElementById('errorMsg');
  el.textContent = '⚠ ' + msg;
  el.style.display = 'block';
}}

// ── Main render ──
function renderResults(pulls) {{
  // Group by gacha_type
  const byType = {{}};
  pulls.forEach(p => {{
    const t = p.gacha_type || '1';
    (byType[t] = byType[t] || []).push(p);
  }});

  // Sort pulls within each type by time (oldest first)
  Object.values(byType).forEach(arr => arr.sort((a,b) => a.time < b.time ? -1 : 1));

  // Build tabs
  const tabs = document.getElementById('bannerTabs');
  const knownTypes = ['11','12','1','2'];
  const presentTypes = knownTypes.filter(t => byType[t]);
  const allTotal = pulls.length;

  const allTotal2 = pulls.length;
  tabs.innerHTML = '<button class="banner-tab active" onclick="switchBanner(\'all\',this)" style="background:var(--bg3);color:var(--text)">全部 (' + allTotal2 + ')</button>' + presentTypes.map(t => {{
    const info = GACHA_INFO[t] || {{}};
    const cnt = (byType[t]||[]).length;
    return `<button class="banner-tab" onclick="switchBanner('${{t}}',this)"
      style="border-color:${{info.color||'#888'}}55">
      ${{info.name||t}} (${{cnt}})
    </button>`;
  }}).join('');

  activeBanner = 'all';
  renderBanner('all', byType, presentTypes);
  document.getElementById('results').style.display = 'block';
}}

function switchBanner(type, btn) {{
  activeBanner = type;
  document.querySelectorAll('.banner-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  if (btn.style.borderColor) btn.style.background = btn.style.borderColor.replace('55','22');
  const byType = {{}};
  allData.forEach(p => {{ const t = p.gacha_type||'1'; (byType[t]=byType[t]||[]).push(p); }});
  Object.values(byType).forEach(arr => arr.sort((a,b) => a.time<b.time?-1:1));
  const knownTypes = ['11','12','1','2'];
  renderBanner(type, byType, knownTypes.filter(t=>byType[t]));
}}

function renderBanner(type, byType, presentTypes) {{
  const typesToShow = type === 'all' ? presentTypes : [type];
  let html = '';
  for (const t of typesToShow) {{
    const pulls = byType[t] || [];
    if (!pulls.length) continue;
    html += renderOneBanner(t, pulls);
  }}
  document.getElementById('bannerContent').innerHTML = html;
}}

function renderOneBanner(type, pulls) {{
  const info = GACHA_INFO[type] || {{name: type, hard_pity: 90, soft_pity: 74, color: '#888', guarantee: '?'}};

  // Compute stats
  const total5 = pulls.filter(p => p.rank_type === '5').length;
  const total4 = pulls.filter(p => p.rank_type === '4').length;
  const total  = pulls.length;
  const avgPer5 = total5 > 0 ? (total / total5).toFixed(1) : '—';
  const jadeEst = total * 160;

  // 5★ pity windows
  const fiveStarHistory = [];
  let pityCount = 0;
  let guaranteed = false; // track 50/50 guarantee for banner type 11
  for (const p of pulls) {{
    pityCount++;
    if (p.rank_type === '5') {{
      fiveStarHistory.push({{
        name: p.name,
        pulls: pityCount,
        time: p.time,
        guaranteed,
        item_type: p.item_type,
      }});
      // For AvatarUp: track guarantee
      if (type === '11') {{
        // If this wasn't a guaranteed (we don't have featured info), mark next as guaranteed if they lost 50/50
        // Simplified: just track pity count
      }}
      pityCount = 0;
    }}
  }}

  // Current pity (pulls since last 5★)
  const currentPity = pityCount;
  const pitySoftPct = Math.max(0, Math.min(100, (currentPity - info.soft_pity) / (info.hard_pity - info.soft_pity) * 100));
  const pityBarPct = Math.min(100, currentPity / info.hard_pity * 100);
  const softPityPos = Math.round(info.soft_pity / info.hard_pity * 100);

  // Luck rating
  const globalAvg = type === '11' ? 62 : type === '12' ? 55 : 60;
  const luck = total5 > 0 ? (globalAvg / (total / total5) * 100) : 100;
  const luckEmoji = luck >= 115 ? '🌟' : luck >= 100 ? '😊' : luck >= 85 ? '😐' : '😢';
  const luckText = luck >= 115 ? '运气极佳！比平均少抽很多' : luck >= 100 ? '运气不错，高于平均水平' : luck >= 85 ? '运气一般，接近平均水平' : '运气欠佳，需要更多抽数';

  // Timeline (per-pull, mark 5★ and 4★)
  const timelineHtml = buildTimeline(pulls);

  const pityDangerClass = currentPity >= info.soft_pity ? (currentPity >= 80 ? 'var(--red)' : 'var(--gold)') : info.color;

  return `
  <div style="border:1px solid ${{info.color}}44;border-radius:12px;padding:1.2rem;margin-bottom:1.5rem;background:${{info.color}}08">
    <h2 style="font-size:1rem;font-weight:700;margin-bottom:1rem;color:${{info.color}}">${{info.name}}</h2>

    <div class="luck-meter">
      <div class="luck-dial">${{luckEmoji}}</div>
      <div class="luck-text">
        <h4>运气评价</h4>
        <p>${{luckText}}（相对平均 ${{(luck-100).toFixed(0)}}%）</p>
      </div>
    </div>

    <div class="overview-row">
      <div class="ov-card">
        <div class="ov-num">${{total}}</div>
        <div class="ov-label">总抽数</div>
        <div class="ov-sub" style="color:var(--muted)">≈ ${{(jadeEst).toLocaleString()}} 星琼</div>
      </div>
      <div class="ov-card">
        <div class="ov-num" style="color:var(--gold)">${{total5}}</div>
        <div class="ov-label">5★ 获得</div>
        <div class="ov-sub" style="color:var(--gold)">平均 ${{avgPer5}} 抽/个</div>
      </div>
      <div class="ov-card">
        <div class="ov-num" style="color:var(--purple)">${{total4}}</div>
        <div class="ov-label">4★ 获得</div>
        <div class="ov-sub" style="color:var(--muted)">${{(total4/total*100).toFixed(1)}}% 比例</div>
      </div>
      <div class="ov-card">
        <div class="ov-num" style="color:${{pityDangerClass}}">${{currentPity}}</div>
        <div class="ov-label">当前保底进度</div>
        <div class="ov-sub" style="color:var(--muted)">距硬保底 ${{info.hard_pity - currentPity}} 抽</div>
      </div>
    </div>

    <div class="pity-section">
      <h3>保底进度</h3>
      <div class="pity-gauge">
        <div class="pity-label">
          <span>当前：${{currentPity}} 抽</span>
          <span style="color:${{pityDangerClass}}">${{currentPity >= info.soft_pity ? '⚠ 进入软保底区间' : ''}}</span>
          <span>硬保底：${{info.hard_pity}} 抽</span>
        </div>
        <div class="pity-bar-outer">
          <div class="pity-bar-inner" style="width:${{pityBarPct}}%;background:${{pityDangerClass}}"></div>
          <div class="pity-bar-soft" style="left:${{softPityPos}}%"></div>
        </div>
        <div class="pity-text">软保底从 ${{info.soft_pity}} 抽开始 · 保底类型：${{info.guarantee}}</div>
      </div>
    </div>

    ${{fiveStarHistory.length > 0 ? `
    <div class="pity-section">
      <h3>5★ 历史记录</h3>
      <div class="five-star-list">
        ${{fiveStarHistory.map(f => {{
          const charInfo = CHAR_DATA[f.name] || {{}};
          const eCol = ELEM_COLOR[charInfo.element] || '#888';
          const pullClass = f.pulls <= 40 ? 'pull-count-lucky' : f.pulls <= 70 ? 'pull-count-normal' : 'pull-count-unlucky';
          return `<div class="five-star-item">
            <div class="five-star-name" style="color:${{eCol}}">${{f.name}}</div>
            <div style="font-size:.75rem;color:var(--muted)">${{f.time ? f.time.slice(0,10) : ''}}</div>
            <div class="five-star-pulls ${{pullClass}}">${{f.pulls}} 抽</div>
          </div>`;
        }}).join('')}}
      </div>
    </div>` : ''}}

    <div class="timeline-wrap">
      <h3>抽取时间线（每格=10抽，金=5★，紫=4★）</h3>
      ${{timelineHtml}}
    </div>
  </div>`;
}}

function buildTimeline(pulls) {{
  // Group into blocks of 10, show 5★ and 4★ density
  const BLOCK = 10;
  const blocks = [];
  for (let i = 0; i < pulls.length; i += BLOCK) {{
    const chunk = pulls.slice(i, i + BLOCK);
    const fives = chunk.filter(p => p.rank_type === '5').map(p => p.name);
    const fours = chunk.filter(p => p.rank_type === '4').length;
    blocks.push({{start: i+1, fives, fours, total: chunk.length}});
  }}
  const maxFives = Math.max(1, ...blocks.map(b => b.fives.length));
  const bars = blocks.map(b => {{
    const col = b.fives.length > 0 ? 'var(--gold)' : b.fours >= 3 ? 'var(--purple)' : 'var(--bg3)';
    const h = b.fives.length > 0 ? Math.max(20, b.fives.length / maxFives * 70) : b.fours >= 3 ? 15 : 6;
    const tip = b.fives.length > 0 ? b.fives.join(', ') : b.fours > 0 ? `${{b.fours}}个4★` : '';
    return `<div class="t-bar" style="height:${{h}}px;background:${{col}};width:${{Math.max(5,Math.floor(600/blocks.length))}}px">
      ${{tip ? `<div class="t-tip">#${{b.start}}: ${{tip}}</div>` : ''}}
    </div>`;
  }}).join('');
  return `<div class="timeline">${{bars}}</div>`;
}}
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="..")
    parser.add_argument("--output",    default="hsr_gacha.html")
    args = parser.parse_args()

    print("加载角色数据…")
    tm = load_json(f"{args.data_root}/TextMap/TextMapCHS.json")
    chars = build_characters(args.data_root, tm)
    print(f"  {len(chars)} 名角色（用于5★展示增强）")

    html = render_html(chars)
    out = args.output if os.path.isabs(args.output) else os.path.join(os.path.dirname(__file__), args.output)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ 生成完毕 → {out}  ({os.path.getsize(out)//1024} KB)")


if __name__ == "__main__":
    main()
