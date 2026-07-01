"""
星穹铁道 · 每日猜角色游戏（Wordle 变体）
生成自包含 hsr_wordle.html，每天随机更换答案，无需服务器。

用法: python build_wordle.py [--data-root ..] [--output hsr_wordle.html]
"""

import json
import os
import argparse


PATH_ZH = {
    "Knight":  "存护", "Rogue": "巡猎", "Mage": "智识",
    "Warrior": "毁灭", "Priest": "丰饶", "Warlock": "虚无",
    "Shaman":  "同谐", "Elation": "欢愉", "Memory": "记忆",
}
ELEMENT_ZH = {
    "Fire": "火", "Ice": "冰", "Wind": "风", "Thunder": "雷",
    "Physical": "物理", "Quantum": "量子", "Imaginary": "虚数",
}
ELEMENT_COLOR = {
    "Fire": "#e8533e", "Ice": "#5bb8d4", "Wind": "#4db89b",
    "Thunder": "#c07de0", "Physical": "#a0a0b0",
    "Quantum": "#7b68ee", "Imaginary": "#d4b84a",
}
PATH_COLOR = {
    "Knight": "#5b9bd5", "Rogue": "#70ad47", "Mage": "#4472c4",
    "Warrior": "#e05c5c", "Priest": "#ffd966", "Warlock": "#9966cc",
    "Shaman": "#47b5c8", "Elation": "#ff8c69", "Memory": "#c0a0e0",
}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_characters(data_root, tm):
    raw = load_json(f"{data_root}/ExcelOutput/AvatarConfig.json")
    promo_raw = load_json(f"{data_root}/ExcelOutput/AvatarPromotionConfig.json")

    promo_max = {}
    for p in promo_raw:
        aid = p["AvatarID"]
        if aid not in promo_max or p["MaxLevel"] > promo_max[aid]["MaxLevel"]:
            promo_max[aid] = p

    chars = []
    for av in raw:
        if not av.get("Release", False):
            continue
        name = tm.get(str(av["AvatarName"]["Hash"]), "")
        if not name or "{NICKNAME}" in name:
            continue

        sp = av.get("SPNeed", {})
        if isinstance(sp, dict):
            sp = sp.get("Value", 0)
        sp = int(sp)
        if sp < 90:
            continue

        stars = 5 if "Type5" in av["Rarity"] else 4
        path = av["AvatarBaseType"]
        element = av["DamageType"]

        spd = 0
        p = promo_max.get(av["AvatarID"])
        if p and "SpeedBase" in p:
            spd = round(p["SpeedBase"]["Value"])

        chars.append({
            "id":      av["AvatarID"],
            "name":    name,
            "path":    path,
            "element": element,
            "stars":   stars,
            "sp":      sp,
            "spd":     spd,
        })

    chars.sort(key=lambda c: c["name"])
    return chars


def render_html(characters) -> str:
    chars_json      = json.dumps(characters,    ensure_ascii=False)
    path_zh_json    = json.dumps(PATH_ZH,       ensure_ascii=False)
    elem_zh_json    = json.dumps(ELEMENT_ZH,    ensure_ascii=False)
    elem_color_json = json.dumps(ELEMENT_COLOR, ensure_ascii=False)
    path_color_json = json.dumps(PATH_COLOR,    ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>星穹铁道 · 每日猜角色</title>
<style>
:root {{
  --bg: #0d1117; --bg2: #161b22; --bg3: #21262d;
  --border: #30363d; --text: #e6edf3; --muted: #8b949e;
  --green: #3fb950; --yellow: #e3b341; --red: #f85149;
  --accent: #58a6ff;
  font-family: 'Segoe UI', system-ui, sans-serif;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: var(--bg); color: var(--text); min-height: 100vh;
        display: flex; flex-direction: column; align-items: center; padding: 1.5rem 1rem; }}

header {{ text-align: center; margin-bottom: 1.5rem; }}
header h1 {{ font-size: 1.6rem; font-weight: 800;
  background: linear-gradient(135deg, #e3b341, #58a6ff);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
header p {{ font-size: .85rem; color: var(--muted); margin-top: .3rem; }}
.date-badge {{
  display: inline-block; font-size: .75rem; background: var(--bg3);
  border: 1px solid var(--border); border-radius: 12px; padding: .2rem .7rem;
  color: var(--muted); margin-top: .5rem;
}}

/* ── Input ── */
.input-area {{ width: 100%; max-width: 560px; margin-bottom: 1rem; position: relative; }}
.search-input {{
  width: 100%; padding: .75rem 1rem; font-size: 1rem;
  background: var(--bg2); border: 2px solid var(--border);
  border-radius: 10px; color: var(--text); outline: none;
  transition: border-color .15s;
}}
.search-input:focus {{ border-color: var(--accent); }}
.autocomplete {{
  position: absolute; top: 100%; left: 0; right: 0; z-index: 50;
  background: var(--bg2); border: 1px solid var(--border);
  border-radius: 8px; margin-top: 2px;
  max-height: 240px; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,.5);
}}
.ac-item {{
  padding: .55rem 1rem; cursor: pointer; font-size: .9rem;
  display: flex; align-items: center; gap: .5rem;
}}
.ac-item:hover {{ background: var(--bg3); }}
.ac-badge {{
  font-size: .72rem; padding: .15rem .45rem; border-radius: 8px;
  font-weight: 600; flex-shrink: 0;
}}

/* ── Status ── */
.status {{ font-size: .95rem; margin-bottom: 1rem; min-height: 1.4em; text-align: center; }}
.status.win  {{ color: var(--green); font-weight: 700; }}
.status.lose {{ color: var(--red);   font-weight: 700; }}
.guess-count {{ color: var(--muted); font-size: .85rem; }}

/* ── Column headers ── */
.col-headers {{
  width: 100%; max-width: 700px;
  display: grid; grid-template-columns: 1.4fr 1fr 1fr .8fr .9fr .9fr;
  gap: 4px; margin-bottom: 4px; padding: 0 2px;
}}
.col-header {{
  font-size: .68rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .06em; color: var(--muted); text-align: center;
  padding: .2rem;
}}

/* ── Guess table ── */
.guesses {{ width: 100%; max-width: 700px; display: flex; flex-direction: column; gap: 4px; }}
.guess-row {{
  display: grid; grid-template-columns: 1.4fr 1fr 1fr .8fr .9fr .9fr;
  gap: 4px;
  animation: slideIn .3s ease;
}}
@keyframes slideIn {{ from {{ opacity:0; transform:translateY(-6px) }} to {{ opacity:1; transform:translateY(0) }} }}
.cell {{
  border-radius: 8px; padding: .5rem .3rem;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  font-size: .82rem; font-weight: 600; text-align: center; line-height: 1.3;
  min-height: 52px; border: 2px solid transparent;
}}
.cell.correct {{ background: rgba(63,185,80,.2); border-color: var(--green); color: var(--green); }}
.cell.wrong   {{ background: rgba(248,81,73,.1);  border-color: var(--red);   color: var(--muted); }}
.cell.higher  {{ background: rgba(227,179,65,.1); border-color: var(--yellow); color: var(--yellow); }}
.cell.lower   {{ background: rgba(227,179,65,.1); border-color: var(--yellow); color: var(--yellow); }}
.cell-label {{ font-size: .65rem; font-weight: 400; opacity: .6; margin-bottom: .1rem; }}
.arrow {{ font-size: 1rem; }}

/* ── Buttons ── */
.btn-row {{ display: flex; gap: .75rem; margin-top: 1rem; flex-wrap: wrap; justify-content: center; }}
.btn {{
  padding: .55rem 1.2rem; border-radius: 8px; border: none;
  font-size: .9rem; font-weight: 600; cursor: pointer;
  transition: opacity .15s;
}}
.btn:hover {{ opacity: .85; }}
.btn-share {{ background: var(--green); color: #0d1117; }}
.btn-hint  {{ background: var(--bg3); color: var(--text); border: 1px solid var(--border); }}
.btn-new   {{ background: var(--accent); color: #0d1117; }}

/* ── Hint panel ── */
.hint-panel {{
  display: none; width: 100%; max-width: 560px;
  background: var(--bg2); border: 1px solid var(--border);
  border-radius: 10px; padding: .8rem 1rem; margin-top: .5rem;
  font-size: .85rem; color: var(--muted); line-height: 1.6;
}}
.hint-panel.open {{ display: block; }}

/* ── Win animation ── */
.confetti {{ position: fixed; pointer-events: none; top: 0; left: 0; width: 100%; height: 100%; z-index: 999; }}

/* ── Legend ── */
.legend {{
  display: flex; gap: 1rem; flex-wrap: wrap; justify-content: center;
  margin: 1.25rem 0 .5rem; font-size: .75rem; color: var(--muted);
}}
.legend-item {{ display: flex; align-items: center; gap: .3rem; }}
.legend-dot {{ width: 12px; height: 12px; border-radius: 3px; }}

/* ── Share toast ── */
.toast {{
  position: fixed; bottom: 2rem; left: 50%; transform: translateX(-50%);
  background: var(--bg3); border: 1px solid var(--border);
  border-radius: 8px; padding: .6rem 1.2rem; font-size: .9rem;
  opacity: 0; transition: opacity .3s; pointer-events: none; z-index: 1000;
}}
.toast.show {{ opacity: 1; }}

@media(max-width:500px) {{
  .col-headers, .guess-row {{ grid-template-columns: 1.2fr 1fr 1fr .7fr .8fr .8fr; gap: 3px; }}
  .cell {{ font-size: .75rem; padding: .4rem .2rem; }}
}}
</style>
</head>
<body>

<header>
  <h1>✦ 每日猜角色</h1>
  <p>根据提示猜出今天的星穹铁道角色</p>
  <div class="date-badge" id="dateBadge"></div>
</header>

<div class="input-area" id="inputArea">
  <input type="text" class="search-input" id="searchInput"
    placeholder="输入角色名称…" autocomplete="off"
    oninput="onInput()" onkeydown="onKey(event)">
  <div class="autocomplete" id="acList" style="display:none"></div>
</div>

<div class="status" id="statusMsg"></div>
<div class="guess-count" id="guessCount"></div>

<div class="col-headers">
  <div class="col-header">角色</div>
  <div class="col-header">命途</div>
  <div class="col-header">属性</div>
  <div class="col-header">稀有度</div>
  <div class="col-header">能量值</div>
  <div class="col-header">速度</div>
</div>
<div class="guesses" id="guesses"></div>

<div class="legend">
  <div class="legend-item"><div class="legend-dot" style="background:rgba(63,185,80,.5);border:1px solid #3fb950"></div>完全一致</div>
  <div class="legend-item"><div class="legend-dot" style="background:rgba(227,179,65,.3);border:1px solid #e3b341"></div>数值偏高/偏低</div>
  <div class="legend-item"><div class="legend-dot" style="background:rgba(248,81,73,.2);border:1px solid #f85149"></div>不匹配</div>
</div>

<div class="btn-row" id="btnRow" style="display:none">
  <button class="btn btn-share" onclick="share()">📋 分享结果</button>
  <button class="btn btn-hint"  onclick="toggleHint()">💡 查看答案</button>
</div>

<div class="hint-panel" id="hintPanel"></div>

<div class="toast" id="toast"></div>

<script>
const CHARS      = {chars_json};
const PATH_ZH    = {path_zh_json};
const ELEM_ZH    = {elem_zh_json};
const ELEM_COLOR = {elem_color_json};
const PATH_COLOR = {path_color_json};

// ─── Daily seed ───
function dateKey() {{
  const d = new Date();
  return `${{d.getFullYear()}}-${{String(d.getMonth()+1).padStart(2,'0')}}-${{String(d.getDate()).padStart(2,'0')}}`;
}}
function seededRandom(seed) {{
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = Math.imul(31, h) + seed.charCodeAt(i) | 0;
  return Math.abs(h) % CHARS.length;
}}

const TODAY = dateKey();
const SECRET_IDX = seededRandom(TODAY + "hsr-wordle-v1");
const SECRET = CHARS[SECRET_IDX];

document.getElementById('dateBadge').textContent = `📅 ${{TODAY}} · 第 ${{SECRET_IDX+1}} 题`;

// ─── State ───
let guesses = [];
let gameOver = false;
let acSelected = -1;

// Restore from localStorage
const saveKey = `hsr-wordle-${{TODAY}}`;
const saved = JSON.parse(localStorage.getItem(saveKey) || 'null');
if (saved) {{
  guesses = saved.guesses || [];
  gameOver = saved.gameOver || false;
  guesses.forEach(g => renderGuess(g));
  if (gameOver) showEndState();
}}
updateGuessCount();

// ─── Input / Autocomplete ───
function onInput() {{
  const q = document.getElementById('searchInput').value.trim();
  if (!q) {{ hideAC(); return; }}
  const matches = CHARS.filter(c => c.name.includes(q) && !guesses.find(g => g.name === c.name));
  showAC(matches.slice(0, 8));
}}

function onKey(e) {{
  const items = document.querySelectorAll('.ac-item');
  if (e.key === 'ArrowDown') {{ acSelected = Math.min(acSelected+1, items.length-1); highlightAC(); e.preventDefault(); }}
  else if (e.key === 'ArrowUp') {{ acSelected = Math.max(acSelected-1, -1); highlightAC(); e.preventDefault(); }}
  else if (e.key === 'Enter') {{
    if (acSelected >= 0 && items[acSelected]) {{ items[acSelected].click(); }}
    else {{
      const q = document.getElementById('searchInput').value.trim();
      const exact = CHARS.find(c => c.name === q);
      if (exact) submitGuess(exact);
    }}
  }}
  else if (e.key === 'Escape') hideAC();
}}

function showAC(matches) {{
  const ac = document.getElementById('acList');
  if (!matches.length) {{ hideAC(); return; }}
  acSelected = -1;
  ac.innerHTML = matches.map((c,i) => {{
    const eCol = ELEM_COLOR[c.element] || '#888';
    const pCol = PATH_COLOR[c.path] || '#888';
    return `<div class="ac-item" onclick="submitGuess(CHARS[${{CHARS.indexOf(c)}}])">
      <span style="font-weight:600">${{c.name}}</span>
      <span class="ac-badge" style="background:${{pCol}}22;color:${{pCol}};border:1px solid ${{pCol}}44">${{PATH_ZH[c.path]||c.path}}</span>
      <span class="ac-badge" style="background:${{eCol}}22;color:${{eCol}};border:1px solid ${{eCol}}44">${{ELEM_ZH[c.element]||c.element}}</span>
      <span style="color:#888;font-size:.78rem">${{'★'.repeat(c.stars)}}</span>
    </div>`;
  }}).join('');
  ac.style.display = 'block';
}}

function hideAC() {{
  document.getElementById('acList').style.display = 'none';
  acSelected = -1;
}}

function highlightAC() {{
  document.querySelectorAll('.ac-item').forEach((el,i) => {{
    el.style.background = i === acSelected ? 'var(--bg3)' : '';
  }});
}}

document.addEventListener('click', e => {{
  if (!e.target.closest('.input-area')) hideAC();
}});

// ─── Game logic ───
function submitGuess(char) {{
  if (gameOver) return;
  if (guesses.find(g => g.name === char.name)) {{
    showToast('已经猜过这个角色了！');
    return;
  }}
  hideAC();
  document.getElementById('searchInput').value = '';

  const guess = buildGuessResult(char);
  guesses.push(guess);
  renderGuess(guess);
  updateGuessCount();

  const won = guess.cells.every(c => c.state === 'correct');
  if (won || guesses.length >= 10) {{
    gameOver = true;
    showEndState();
  }}

  // Save state
  localStorage.setItem(saveKey, JSON.stringify({{ guesses, gameOver }}));
}}

function buildGuessResult(char) {{
  const s = SECRET;
  const cells = [
    // Path
    {{ label: PATH_ZH[char.path]||char.path, value: '', state: char.path === s.path ? 'correct' : 'wrong',
       color: PATH_COLOR[char.path], hint: char.path === s.path ? '' : (PATH_ZH[s.path]||s.path) }},
    // Element
    {{ label: ELEM_ZH[char.element]||char.element, value: '', state: char.element === s.element ? 'correct' : 'wrong',
       color: ELEM_COLOR[char.element] }},
    // Stars
    {{ label: '★'.repeat(char.stars), value: '', state: char.stars === s.stars ? 'correct' : 'wrong' }},
    // SP
    {{ label: char.sp, value: char.sp < s.sp ? '↑' : char.sp > s.sp ? '↓' : '',
       state: char.sp === s.sp ? 'correct' : (Math.abs(char.sp - s.sp) <= 20 ? 'higher' : 'wrong') }},
    // Speed
    {{ label: char.spd, value: char.spd < s.spd ? '↑' : char.spd > s.spd ? '↓' : '',
       state: char.spd === s.spd ? 'correct' : (Math.abs(char.spd - s.spd) <= 5 ? 'higher' : 'wrong') }},
  ];
  return {{ name: char.name, element: char.element, cells, isCorrect: char.id === s.id }};
}}

function renderGuess(guess) {{
  const eCol = ELEM_COLOR[guess.element] || '#888';
  const row = document.createElement('div');
  row.className = 'guess-row';

  // Name cell
  const nameCell = document.createElement('div');
  nameCell.className = `cell ${{guess.isCorrect ? 'correct' : 'wrong'}}`;
  nameCell.innerHTML = `<span style="font-size:.9rem;font-weight:700">${{guess.name}}</span>`;
  row.appendChild(nameCell);

  // Data cells
  guess.cells.forEach((c, i) => {{
    const cell = document.createElement('div');
    cell.className = `cell ${{c.state}}`;

    if (i === 0 || i === 1) {{
      // Path / Element - colored badge style
      const bg = (c.color || '#888') + (c.state === 'correct' ? '33' : '15');
      const border = (c.color || '#888') + (c.state === 'correct' ? '88' : '33');
      cell.style.background = bg;
      cell.style.borderColor = border;
      cell.style.color = c.state === 'correct' ? (c.color||'#888') : 'var(--muted)';
      cell.innerHTML = c.label;
    }} else if (i === 2) {{
      // Stars
      cell.style.color = c.state === 'correct' ? (guess.cells[2].label.length === 5 ? '#e3b341' : '#a78bfa') : 'var(--muted)';
      cell.innerHTML = c.label;
    }} else {{
      // Numeric
      cell.innerHTML = `${{c.label}}<span class="arrow">${{c.value}}</span>`;
    }}
    row.appendChild(cell);
  }});

  document.getElementById('guesses').prepend(row);
}}

function updateGuessCount() {{
  const el = document.getElementById('guessCount');
  if (guesses.length > 0) el.textContent = `第 ${{guesses.length}} 次猜测`;
  else el.textContent = '';
}}

function showEndState() {{
  const won = guesses[guesses.length-1]?.isCorrect;
  const msg = document.getElementById('statusMsg');
  const s = SECRET;
  const eCol = ELEM_COLOR[s.element] || '#888';

  if (won) {{
    msg.className = 'status win';
    const funMessages = ['心有灵犀！','星辰指引！','命中注定！','开拓者的直觉！','差点差点～'];
    const msgIdx = Math.min(guesses.length-1, funMessages.length-1);
    msg.textContent = '✓ 答对了！' + funMessages[msgIdx] + '（第 ' + guesses.length + ' 次）';
    triggerConfetti();
  }} else {{
    msg.className = 'status lose';
    msg.textContent = `答案是「${{s.name}}」，明天再来！`;
  }}

  document.getElementById('inputArea').style.display = 'none';
  document.getElementById('btnRow').style.display = 'flex';
  const hint = document.getElementById('hintPanel');
  hint.innerHTML = `<strong>${{s.name}}</strong>（${{PATH_ZH[s.path]||s.path}} · ${{ELEM_ZH[s.element]||s.element}} · ${{s.stars}}★ · 能量${{s.sp}} · 速度${{s.spd}}）`;
}}

// ─── Hint / Share ───
function toggleHint() {{
  const hp = document.getElementById('hintPanel');
  hp.classList.toggle('open');
}}

const EMOJI = {{ correct:'🟩', wrong:'🟥', higher:'🟨', lower:'🟨' }};
function share() {{
  const lines = [`✦ 星穹铁道每日猜角色 ${{TODAY}}`, `猜了 ${{guesses.length}} 次`, ''];
  guesses.forEach(g => {{
    const row = [g.isCorrect ? '🟩' : '🟥', ...g.cells.map(c => EMOJI[c.state])].join('');
    lines.push(row);
  }});
  lines.push('');
  lines.push('命途/属性/稀有度/能量值/速度');
  navigator.clipboard.writeText(lines.join('\n')).then(() => showToast('已复制到剪贴板！'));
}}

function showToast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2000);
}}

// ─── Confetti ───
function triggerConfetti() {{
  const canvas = document.createElement('canvas');
  canvas.className = 'confetti';
  document.body.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;

  const particles = Array.from({{length: 80}}, () => ({{
    x: Math.random() * canvas.width,
    y: -10,
    r: Math.random() * 5 + 3,
    vx: (Math.random() - .5) * 3,
    vy: Math.random() * 3 + 2,
    color: ['#e3b341','#58a6ff','#3fb950','#f85149','#c07de0'][Math.floor(Math.random()*5)],
    rotation: Math.random() * 360,
    spin: (Math.random() - .5) * 6,
  }}));

  let frame;
  function animate() {{
    ctx.clearRect(0,0,canvas.width,canvas.height);
    let alive = false;
    particles.forEach(p => {{
      p.x += p.vx; p.y += p.vy; p.vy += .05; p.rotation += p.spin;
      if (p.y < canvas.height + 20) alive = true;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rotation * Math.PI / 180);
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.r, -p.r/2, p.r*2, p.r);
      ctx.restore();
    }});
    if (alive) frame = requestAnimationFrame(animate);
    else canvas.remove();
  }}
  animate();
  setTimeout(() => {{ cancelAnimationFrame(frame); canvas.remove(); }}, 4000);
}}
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="..")
    parser.add_argument("--output",    default="hsr_wordle.html")
    args = parser.parse_args()

    print("加载 TextMap (CHS)…")
    tm = json.load(open(f"{args.data_root}/TextMap/TextMapCHS.json", encoding="utf-8"))
    print("构建角色数据…")
    characters = build_characters(args.data_root, tm)
    print(f"  {len(characters)} 名可猜角色")

    html = render_html(characters)
    out = args.output if os.path.isabs(args.output) else os.path.join(os.path.dirname(__file__), args.output)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    size_kb = os.path.getsize(out) / 1024
    print(f"✓ 生成完毕 → {out}  ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
