"""
星穹铁道 · 命途性格测验
根据 10 道场景题匹配你的命途与最相似角色，完全基于游戏内角色/命途数据生成结果页。

用法: python build_quiz.py [--data-root ..] [--output hsr_quiz.html]
"""

import json
import os
import argparse


PATH_ZH = {
    "Knight": "存护", "Rogue": "巡猎", "Mage": "智识",
    "Warrior": "毁灭", "Priest": "丰饶", "Warlock": "虚无",
    "Shaman": "同谐", "Elation": "欢愉", "Memory": "记忆",
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
PATH_FLAVOR = {
    "Knight":  "守护是你的本能。你深知，比破坏世界更难的是保护它——即便那意味着以一己之力承载所有重量。",
    "Rogue":   "你的世界里只有目标和路径。没有多余的情绪，没有迟疑——弓弦拉满的瞬间，你已然抵达终点。",
    "Mage":    "知识是你唯一可信赖的火炬。你相信，宇宙的每一个秘密都值得穷尽一生去追问，哪怕它从不给出答案。",
    "Warrior": "力量是诚实的。你不借助绕路，不依赖技巧，只是把全部的意志化为一击——直至世界被你重塑。",
    "Priest":  "你是每片土地上沉默的雨水。你知道给予不需要被看见，繁荣本身就是最好的回答。",
    "Warlock":  "你看穿了世界运转的底层逻辑：熵增、消亡、虚无——但你并不悲观。你只是看得更远。",
    "Shaman":  "你是乐团里那个让所有人都演奏出最好状态的指挥。荣耀在别人身上，但那也是你的荣耀。",
    "Elation": "你把苦难变成节日，把平凡变成舞台。对你来说，痛是一首歌，死亡是最后的高潮。",
    "Memory":  "记忆比现实更真实。你活在无数层叠的过去与可能之中，而那些忘却的碎片，才是你真正的财富。",
}

QUESTIONS = [
    {
        "q": "面对一个即将崩溃的局面，你的第一反应是？",
        "opts": [
            ("挡在最前面，让其他人先撤。", {"Knight": 3, "Priest": 1}),
            ("分析原因，找到最有效率的破局点。", {"Rogue": 2, "Mage": 2}),
            ("直接对准问题的源头，用最大的力把它终结。", {"Warrior": 3}),
            ("悄悄让局面朝着你预期的方向滑落。", {"Warlock": 3, "Elation": 1}),
        ],
    },
    {
        "q": "如果你能随身携带宇宙中的一样东西，你会选择？",
        "opts": [
            ("能保护你在乎的人的盾牌。", {"Knight": 3}),
            ("永远射得准的弓。", {"Rogue": 3}),
            ("记录宇宙一切知识的书。", {"Mage": 3}),
            ("让所有人都不再疼痛的药。", {"Priest": 3}),
        ],
    },
    {
        "q": "一段旅程结束，你最常回想起的是？",
        "opts": [
            ("那些你保护下来的人，他们现在怎么样了。", {"Knight": 2, "Priest": 2}),
            ("那些没有完成的目标和被错过的猎物。", {"Rogue": 3}),
            ("那些你来不及搞懂的谜题。", {"Mage": 3}),
            ("自己消失之后，世界会不会还有人记得。", {"Memory": 3, "Warlock": 1}),
        ],
    },
    {
        "q": "你的朋友形容你是那种……",
        "opts": [
            ("无论什么时候打电话，都会第一个赶到的人。", {"Knight": 3, "Priest": 1}),
            ("独自解决了事，不爱多说的人。", {"Rogue": 2, "Warrior": 2}),
            ("说起某件事能一直讲两个小时的人。", {"Mage": 3, "Elation": 1}),
            ("让每个人都感觉自己是最重要的那个人。", {"Shaman": 3, "Priest": 1}),
        ],
    },
    {
        "q": "你怎么看待「规则」？",
        "opts": [
            ("规则是保护弱者的防线，值得坚守。", {"Knight": 2, "Priest": 2}),
            ("规则只是路标，目标比规则更重要。", {"Rogue": 3, "Warrior": 1}),
            ("规则背后有更深层的逻辑，要先搞懂为什么。", {"Mage": 3, "Warlock": 1}),
            ("规则是别人定的游戏，我更擅长玩另一种游戏。", {"Warlock": 2, "Elation": 2}),
        ],
    },
    {
        "q": "如果你身处一个失去所有记忆的世界，你最想找回的是？",
        "opts": [
            ("你守护过的人和你对他们的承诺。", {"Knight": 2, "Memory": 2}),
            ("你努力追逐的那个目标，是什么让你奔跑。", {"Rogue": 2, "Warrior": 2}),
            ("你用一生积累的知识和方法论。", {"Mage": 3}),
            ("你在意的人们的名字。", {"Priest": 2, "Shaman": 2}),
        ],
    },
    {
        "q": "一场表演就要开始，你更可能是……",
        "opts": [
            ("站在台下确认后台安全的工作人员。", {"Knight": 2, "Shaman": 2}),
            ("已经想好中途离场路线的观众。", {"Rogue": 2, "Warlock": 2}),
            ("悄悄记下布景细节的研究者。", {"Mage": 3}),
            ("台上唯一不需要剧本的那个演员。", {"Elation": 3, "Warrior": 1}),
        ],
    },
    {
        "q": "面对一个无法改变的命运，你选择？",
        "opts": [
            ("把能改变的那一部分做到极致。", {"Knight": 2, "Warrior": 2}),
            ("研究它的结构，看看有没有漏洞。", {"Mage": 2, "Rogue": 2}),
            ("接受它，然后帮助身边的人也接受它。", {"Priest": 2, "Shaman": 2}),
            ("它本来就是命运的一部分——虚无才是真正的终点。", {"Warlock": 3, "Memory": 1}),
        ],
    },
    {
        "q": "对你来说，「力量」意味着什么？",
        "opts": [
            ("能够保护你在乎的人的能力。", {"Knight": 3}),
            ("绝对命中目标的精准度。", {"Rogue": 3}),
            ("摧毁一切阻碍的爆发力。", {"Warrior": 3}),
            ("让别人发挥出最好状态的能力。", {"Shaman": 3}),
        ],
    },
    {
        "q": "旅途中遭遇了一个与你观念截然不同的人，你会……",
        "opts": [
            ("保持距离，但在他需要帮助时出手。", {"Knight": 2, "Priest": 1}),
            ("试图理解他，也许他掌握了你没有的信息。", {"Mage": 2, "Shaman": 2}),
            ("不多说，继续走自己的路。", {"Rogue": 3}),
            ("把他纳入你的计划——不同的棋子各有用处。", {"Warlock": 3}),
        ],
    },
]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_characters(data_root, tm):
    raw = load_json(f"{data_root}/ExcelOutput/AvatarConfig.json")
    promo_raw = load_json(f"{data_root}/ExcelOutput/AvatarPromotionConfig.json")
    skill_raw = load_json(f"{data_root}/ExcelOutput/AvatarSkillConfig.json")

    promo_max = {}
    for p in promo_raw:
        aid = p["AvatarID"]
        if aid not in promo_max or p["MaxLevel"] > promo_max[aid]["MaxLevel"]:
            promo_max[aid] = p

    skill_map = {}
    for s in skill_raw:
        sid = s["SkillID"]
        if sid not in skill_map or s["Level"] == 1:
            skill_map[sid] = s

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
        if sp < 90:
            continue

        stars = 5 if "Type5" in av["Rarity"] else 4
        path = av["AvatarBaseType"]
        element = av["DamageType"]

        spd = 0
        p = promo_max.get(av["AvatarID"])
        if p and "SpeedBase" in p:
            spd = round(p["SpeedBase"]["Value"])

        skill_tags = []
        for sid in av.get("SkillList", [])[:4]:
            s = skill_map.get(sid)
            if s:
                tag = tm.get(str(s.get("SkillTypeDesc", {}).get("Hash", 0) if isinstance(s.get("SkillTypeDesc"), dict) else 0), "")
                if tag:
                    skill_tags.append(tag)

        chars.append({
            "id":        av["AvatarID"],
            "name":      name,
            "path":      path,
            "element":   element,
            "stars":     stars,
            "sp":        int(sp),
            "spd":       spd,
            "skillTags": skill_tags,
        })

    chars.sort(key=lambda c: c["name"])
    return chars


def render_html(characters, questions) -> str:
    chars_json      = json.dumps(characters,   ensure_ascii=False)
    q_json          = json.dumps(questions,    ensure_ascii=False)
    path_zh_json    = json.dumps(PATH_ZH,      ensure_ascii=False)
    elem_zh_json    = json.dumps(ELEMENT_ZH,   ensure_ascii=False)
    elem_color_json = json.dumps(ELEMENT_COLOR, ensure_ascii=False)
    path_color_json = json.dumps(PATH_COLOR,   ensure_ascii=False)
    path_flavor_json = json.dumps(PATH_FLAVOR,  ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>星穹铁道 · 命途性格测验</title>
<style>
:root {{
  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;
  --border:#30363d;--text:#e6edf3;--muted:#8b949e;--accent:#58a6ff;--gold:#e3b341;
  font-family:'Segoe UI',system-ui,sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);min-height:100vh;
      display:flex;flex-direction:column;align-items:center;padding:2rem 1rem}}

/* ── Card ── */
.card{{
  background:var(--bg2);border:1px solid var(--border);border-radius:16px;
  padding:2rem;max-width:640px;width:100%;
}}

/* ── Intro ── */
.intro-page h1{{
  font-size:1.8rem;font-weight:800;text-align:center;
  background:linear-gradient(135deg,#e3b341,#58a6ff,#c07de0);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  margin-bottom:.5rem;
}}
.intro-page p{{font-size:.95rem;color:var(--muted);text-align:center;line-height:1.7;margin-bottom:.5rem}}
.start-btn{{
  display:block;width:100%;padding:.85rem;margin-top:1.5rem;
  background:linear-gradient(135deg,#e3b341,#c07de0);
  border:none;border-radius:12px;color:#0d1117;font-size:1rem;font-weight:700;
  cursor:pointer;transition:opacity .15s;
}}
.start-btn:hover{{opacity:.85}}

/* ── Quiz ── */
.progress-bar-outer{{background:var(--bg3);border-radius:4px;height:6px;margin-bottom:1.5rem;overflow:hidden}}
.progress-bar-inner{{height:100%;background:linear-gradient(90deg,#e3b341,#58a6ff);border-radius:4px;transition:width .4s}}
.q-counter{{font-size:.78rem;color:var(--muted);margin-bottom:.4rem}}
.q-text{{font-size:1.05rem;font-weight:600;line-height:1.5;margin-bottom:1.2rem}}
.options{{display:flex;flex-direction:column;gap:.6rem}}
.option-btn{{
  padding:.75rem 1rem;background:var(--bg3);border:1px solid var(--border);
  border-radius:10px;color:var(--text);font-size:.9rem;text-align:left;cursor:pointer;
  transition:all .15s;line-height:1.4;
}}
.option-btn:hover{{border-color:var(--accent);background:rgba(88,166,255,.08)}}
.option-btn.selected{{border-color:var(--accent);background:rgba(88,166,255,.15);color:var(--accent)}}

/* ── Results ── */
.result-header{{text-align:center;margin-bottom:1.5rem}}
.result-header h2{{font-size:1.5rem;font-weight:800;margin-bottom:.3rem}}
.path-badge{{
  display:inline-block;font-size:1.1rem;font-weight:700;
  padding:.4rem 1.2rem;border-radius:20px;margin:.4rem 0;
}}
.flavor-text{{
  font-size:.9rem;color:var(--muted);line-height:1.7;
  background:var(--bg3);border-radius:10px;padding:.9rem 1rem;
  margin:.8rem 0 1.2rem;border-left:3px solid var(--accent);
}}
.section-label{{
  font-size:.75rem;font-weight:700;text-transform:uppercase;
  letter-spacing:.08em;color:var(--muted);margin-bottom:.6rem;
}}
.char-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:.6rem;margin-bottom:1.2rem}}
.char-card{{
  background:var(--bg3);border-radius:10px;padding:.7rem .5rem;
  text-align:center;border:1px solid transparent;
}}
.char-name{{font-size:.88rem;font-weight:600;margin-bottom:.2rem}}
.char-meta{{font-size:.72rem;color:var(--muted)}}
.path-bars{{margin-bottom:1.2rem}}
.path-bar-row{{display:flex;align-items:center;gap:.5rem;margin-bottom:.35rem;font-size:.82rem}}
.path-bar-label{{width:48px;text-align:right;color:var(--muted);flex-shrink:0}}
.path-bar-outer{{flex:1;background:var(--bg3);border-radius:3px;height:14px;overflow:hidden}}
.path-bar-inner{{height:100%;border-radius:3px;transition:width .6s}}
.path-bar-num{{width:24px;color:var(--text);flex-shrink:0}}
.retry-btn{{
  width:100%;padding:.7rem;border:none;border-radius:10px;
  background:var(--bg3);color:var(--text);font-size:.95rem;cursor:pointer;
  border:1px solid var(--border);margin-top:.5rem;
}}
.retry-btn:hover{{border-color:var(--accent)}}
.share-text{{
  background:var(--bg3);border-radius:8px;padding:.6rem .8rem;
  font-size:.82rem;color:var(--muted);margin-top:.5rem;
  border:1px dashed var(--border);cursor:pointer;transition:border-color .15s;
}}
.share-text:hover{{border-color:var(--accent)}}
</style>
</head>
<body>

<!-- INTRO -->
<div class="card intro-page" id="introPage">
  <h1>✦ 命途测验</h1>
  <p>10 道场景题，找出你在星穹宇宙中所对应的命途</p>
  <p style="font-size:.82rem;margin-top:.75rem">以及与你最相似的旅伴</p>
  <button class="start-btn" onclick="startQuiz()">开始测验 →</button>
</div>

<!-- QUIZ -->
<div class="card" id="quizPage" style="display:none">
  <div class="progress-bar-outer"><div class="progress-bar-inner" id="progressBar"></div></div>
  <div class="q-counter" id="qCounter"></div>
  <div class="q-text" id="qText"></div>
  <div class="options" id="options"></div>
</div>

<!-- RESULT -->
<div class="card" id="resultPage" style="display:none">
  <div id="resultContent"></div>
</div>

<script>
const CHARS       = {chars_json};
const QUESTIONS   = {q_json};
const PATH_ZH     = {path_zh_json};
const ELEM_ZH     = {elem_zh_json};
const ELEM_COLOR  = {elem_color_json};
const PATH_COLOR  = {path_color_json};
const PATH_FLAVOR = {path_flavor_json};

let current = 0;
let scores = {{}};
let answers = []; // selected option index per question

function startQuiz() {{
  document.getElementById('introPage').style.display = 'none';
  document.getElementById('quizPage').style.display = 'block';
  scores = {{}};
  answers = [];
  current = 0;
  renderQuestion();
}}

function renderQuestion() {{
  const q = QUESTIONS[current];
  const n = QUESTIONS.length;
  document.getElementById('progressBar').style.width = (current / n * 100) + '%';
  document.getElementById('qCounter').textContent = `第 ${{current+1}} / ${{n}} 题`;
  document.getElementById('qText').textContent = q.q;
  document.getElementById('options').innerHTML = q.opts.map((o,i) =>
    `<button class="option-btn ${{answers[current]===i?'selected':''}}" onclick="selectOption(${{i}})">${{o[0]}}</button>`
  ).join('');
}}

function selectOption(i) {{
  answers[current] = i;
  // Update display
  document.querySelectorAll('.option-btn').forEach((btn,idx) => {{
    btn.classList.toggle('selected', idx === i);
  }});
  // Auto-advance after short delay
  setTimeout(() => {{
    const q = QUESTIONS[current];
    const weights = q.opts[i][1];
    Object.entries(weights).forEach(([path, pts]) => {{
      scores[path] = (scores[path] || 0) + pts;
    }});
    current++;
    if (current < QUESTIONS.length) {{
      renderQuestion();
    }} else {{
      showResult();
    }}
  }}, 350);
}}

function showResult() {{
  // Sort paths by score
  const sorted = Object.entries(scores).sort((a,b) => b[1]-a[1]);
  const topPath = sorted[0]?.[0] || 'Knight';
  const secondPath = sorted[1]?.[0] || 'Priest';
  const topScore = sorted[0]?.[1] || 0;

  // Find matching characters (same path, prefer 5★)
  const samePathChars = CHARS.filter(c => c.path === topPath && c.stars === 5);
  const samePathChars4 = CHARS.filter(c => c.path === topPath && c.stars === 4);
  const matchChars = [...samePathChars, ...samePathChars4].slice(0, 3);
  // If fewer than 3, fill with secondary path
  if (matchChars.length < 3) {{
    const fill = CHARS.filter(c => c.path === secondPath && !matchChars.includes(c));
    matchChars.push(...fill.slice(0, 3 - matchChars.length));
  }}

  const pCol = PATH_COLOR[topPath] || '#58a6ff';
  const flavor = PATH_FLAVOR[topPath] || '';

  // Char cards
  const charHtml = matchChars.map(c => {{
    const eCol = ELEM_COLOR[c.element] || '#888';
    const pc   = PATH_COLOR[c.path] || '#888';
    const starColor = c.stars===5 ? '#e3b341' : '#a78bfa';
    return `<div class="char-card" style="border-color:${{pc}}33">
      <div class="char-name">${{c.name}}</div>
      <div class="char-meta" style="color:${{eCol}}">${{ELEM_ZH[c.element]||c.element}}</div>
      <div class="char-meta" style="color:${{starColor}}">${{'★'.repeat(c.stars)}}</div>
    </div>`;
  }}).join('');

  // Path bar chart
  const allPaths = Object.keys(PATH_ZH);
  const maxScore = Math.max(...Object.values(scores), 1);
  const barHtml = allPaths
    .map(p => [p, scores[p] || 0])
    .sort((a,b) => b[1]-a[1])
    .map(([p, s]) => {{
      const col = PATH_COLOR[p] || '#888';
      const w = Math.round(s / maxScore * 100);
      return `<div class="path-bar-row">
        <div class="path-bar-label">${{PATH_ZH[p]||p}}</div>
        <div class="path-bar-outer"><div class="path-bar-inner" style="width:${{w}}%;background:${{col}}"></div></div>
        <div class="path-bar-num">${{s}}</div>
      </div>`;
    }}).join('');

  const shareText = `✦ 我的命途是「${{PATH_ZH[topPath]||topPath}}」\\n与我最相似的角色：${{matchChars.map(c=>c.name).join('、')}}\\n\\n#星穹铁道 #命途测验`;

  document.getElementById('quizPage').style.display = 'none';
  document.getElementById('resultPage').style.display = 'block';
  document.getElementById('resultContent').innerHTML = `
    <div class="result-header">
      <div style="font-size:.85rem;color:var(--muted);margin-bottom:.3rem">你的命途是</div>
      <h2>${{PATH_ZH[topPath]||topPath}}</h2>
      <span class="path-badge" style="background:${{pCol}}22;color:${{pCol}};border:1px solid ${{pCol}}55">
        ${{PATH_ZH[topPath]||topPath}} · ${{PATH_ZH[secondPath]||secondPath}} 倾向
      </span>
    </div>
    <div class="flavor-text">${{flavor}}</div>

    <div class="section-label">与你最相似的旅伴</div>
    <div class="char-grid">${{charHtml}}</div>

    <div class="section-label">命途分布</div>
    <div class="path-bars">${{barHtml}}</div>

    <div class="share-text" onclick="copyShare('${{shareText.replace(/'/g,'&#39;')}}')">
      📋 点击复制测验结果分享文字
    </div>
    <button class="retry-btn" onclick="retryQuiz()">↩ 重新测验</button>
  `;
}}

function copyShare(text) {{
  navigator.clipboard.writeText(text.replace(/\\\\n/g,'\\n')).then(() => {{
    alert('已复制到剪贴板！');
  }});
}}

function retryQuiz() {{
  document.getElementById('resultPage').style.display = 'none';
  startQuiz();
}}
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="..")
    parser.add_argument("--output",    default="hsr_quiz.html")
    args = parser.parse_args()

    print("加载角色数据…")
    tm = json.load(open(f"{args.data_root}/TextMap/TextMapCHS.json", encoding="utf-8"))
    characters = build_characters(args.data_root, tm)
    print(f"  {len(characters)} 名角色")

    html = render_html(characters, QUESTIONS)
    out = args.output if os.path.isabs(args.output) else os.path.join(os.path.dirname(__file__), args.output)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ 生成完毕 → {out}  ({os.path.getsize(out)//1024} KB)")


if __name__ == "__main__":
    main()
