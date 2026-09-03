"""
星穹铁道 · 台词语言学实验室
利用 15.9 万条带说话人标注的台词，做角色「语言指纹」分析、风格相似度、
「谁说的」竞猜，以及开拓者全部可选台词的语料统计。

用法: python build_linguistics.py [--data-root ..] [--output hsr_linguistics.html]
"""

import argparse
import collections
import glob
import json
import math
import os
import random
import re

MIN_LINES = 150          # 进入指纹分析的最低台词数
QUIZ_TOP_N = 40          # 竞猜题库使用台词最多的前 N 名角色
SIM_TOP_N = 30           # 相似度矩阵展示前 N 名
EXCLUDE_SPEAKERS = {"模拟宇宙", "？？？", "{NICKNAME}", "旁白", "系统", "众人"}

LAUGH_RE = re.compile(r"哈哈|呵呵|嘿嘿|嘻嘻|哼哼|噗")
ELLIPSIS_RE = re.compile(r"…|\.\.\.")
PAREN_RE = re.compile(r"^[（(].*[)）]$")
BIGRAM_STOP = re.compile(r"[\s，。！？、；：「」『』（）《》〈〉…—\-\.,!?\"'#\[\]{}<>/|:;_0-9a-zA-Z]")

ADDRESS_TERMS = ["{NICKNAME}", "开拓者", "旅客", "小家伙", "朋友", "各位", "先生", "小姐", "大人", "阁下"]


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("\\n", " ").replace("\n", " ")
    return s.strip()


def bigrams(s: str):
    s = BIGRAM_STOP.sub("", s)
    return [s[i:i + 2] for i in range(len(s) - 1)]


def build(data_root: str):
    tm = load_json(f"{data_root}/TextMap/TextMapCHS.json")

    def T(h):
        if isinstance(h, dict):
            return tm.get(str(h.get("Hash", 0)), "")
        return ""

    talk = load_json(f"{data_root}/ExcelOutput/TalkSentenceConfig.json")
    by_id = {}
    lines_by_speaker = collections.defaultdict(list)
    for t in talk:
        text = clean(T(t.get("TalkSentenceText")))
        if not text:
            continue
        by_id[t["TalkSentenceID"]] = text
        name = T(t.get("TextmapTalkSentenceName")).strip()
        if name:
            lines_by_speaker[name].append(text)

    # ── 开拓者可选台词：所有脚本里 OptionTalkInfo 引用的 TalkSentenceID ──
    option_ids = set()
    pattern = re.compile(r'OptionTalkInfo"[^}]*?"TalkSentenceID":\s*(\d+)', re.S)
    files = glob.glob(f"{data_root}/Story/**/*.json", recursive=True) + \
            glob.glob(f"{data_root}/Config/Level/**/*.json", recursive=True)
    for f in files:
        try:
            txt = open(f, encoding="utf-8").read()
        except Exception:
            continue
        if "OptionTalkInfo" not in txt:
            continue
        for m in pattern.finditer(txt):
            option_ids.add(int(m.group(1)))
    option_lines = sorted({by_id[i] for i in option_ids if i in by_id})

    # ── 角色语言指纹 ──
    avatar_names = set()
    for av in load_json(f"{data_root}/ExcelOutput/AvatarConfig.json"):
        n = T(av.get("AvatarName"))
        if n and "{" not in n:
            avatar_names.add(n)

    speakers = {k: v for k, v in lines_by_speaker.items()
                if len(v) >= MIN_LINES and k not in EXCLUDE_SPEAKERS}

    global_bg = collections.Counter()
    speaker_bg = {}
    for name, lines in speakers.items():
        c = collections.Counter()
        for l in lines:
            c.update(bigrams(l))
        speaker_bg[name] = c
        global_bg.update(c)
    total_bg = sum(global_bg.values())

    profiles = []
    for name, lines in speakers.items():
        n = len(lines)
        chars = sum(len(l) for l in lines)
        c = speaker_bg[name]
        tot = sum(c.values()) or 1
        # 特征词：在该角色出现频率 / 全局频率 的对数比，且出现至少 6 次
        distinct = []
        for bg, cnt in c.items():
            if cnt < 6:
                continue
            p_s = cnt / tot
            p_g = global_bg[bg] / total_bg
            score = math.log(p_s / p_g) * math.log(1 + cnt)
            distinct.append((score, bg, cnt))
        distinct.sort(reverse=True)
        addr = {term: sum(l.count(term) for l in lines) for term in ADDRESS_TERMS}
        addr = {k: v for k, v in addr.items() if v > 0}
        profiles.append({
            "name": name,
            "isAvatar": name in avatar_names,
            "lines": n,
            "chars": chars,
            "avgLen": round(chars / n, 1),
            "ellipsis": round(sum(1 for l in lines if ELLIPSIS_RE.search(l)) / n * 100, 1),
            "exclaim": round(sum(1 for l in lines if "！" in l or "!" in l) / n * 100, 1),
            "question": round(sum(1 for l in lines if "？" in l or "?" in l) / n * 100, 1),
            "laugh": round(sum(1 for l in lines if LAUGH_RE.search(l)) / n * 100, 1),
            "paren": round(sum(1 for l in lines if PAREN_RE.match(l)) / n * 100, 1),
            "longest": max(lines, key=len)[:120],
            "shortest": min((l for l in lines if len(l) >= 2), key=len),
            "distinct": [[bg, cnt] for _, bg, cnt in distinct[:10]],
            "address": addr,
        })
    profiles.sort(key=lambda p: -p["lines"])

    # ── 风格相似度（bigram 频率向量余弦） ──
    top_names = [p["name"] for p in profiles if p["isAvatar"]][:SIM_TOP_N]
    vocab = [bg for bg, _ in global_bg.most_common(4000)]
    idx = {bg: i for i, bg in enumerate(vocab)}
    vecs = {}
    for name in top_names:
        c = speaker_bg[name]
        tot = sum(c.values()) or 1
        v = [0.0] * len(vocab)
        for bg, cnt in c.items():
            if bg in idx:
                v[idx[bg]] = cnt / tot
        norm = math.sqrt(sum(x * x for x in v)) or 1
        vecs[name] = [x / norm for x in v]
    sim = []
    for a in top_names:
        row = []
        for b in top_names:
            row.append(round(sum(x * y for x, y in zip(vecs[a], vecs[b])), 4))
        sim.append(row)

    # ── 竞猜题库 ──
    random.seed(42)
    quiz_names = [p["name"] for p in profiles if p["isAvatar"]][:QUIZ_TOP_N]
    quiz = []
    for name in quiz_names:
        cands = [l for l in speakers[name]
                 if 14 <= len(l) <= 60 and name not in l and "{NICKNAME}" not in l
                 and not PAREN_RE.match(l)]
        random.shuffle(cands)
        for l in cands[:25]:
            quiz.append({"s": name, "t": l})
    random.shuffle(quiz)

    # ── 开拓者语料统计 ──
    tb_lines = option_lines
    tb_n = len(tb_lines) or 1
    tb_bg = collections.Counter()
    for l in tb_lines:
        tb_bg.update(bigrams(l))
    tb_stats = {
        "total": len(tb_lines),
        "avgLen": round(sum(len(l) for l in tb_lines) / tb_n, 1),
        "ellipsis": sum(1 for l in tb_lines if ELLIPSIS_RE.search(l)),
        "paren": sum(1 for l in tb_lines if PAREN_RE.match(l)),
        "trash": sum(1 for l in tb_lines if "垃圾桶" in l),
        "question": sum(1 for l in tb_lines if "？" in l),
        "exclaim": sum(1 for l in tb_lines if "！" in l),
        "topBigrams": tb_bg.most_common(30),
        "trashLines": [l for l in tb_lines if "垃圾桶" in l][:40],
        "sample": random.sample(tb_lines, min(600, len(tb_lines))),
    }

    return {
        "profiles": profiles,
        "simNames": top_names,
        "sim": sim,
        "quiz": quiz,
        "tb": tb_stats,
        "totalLines": sum(len(v) for v in lines_by_speaker.values()),
        "totalSpeakers": len(lines_by_speaker),
    }


def render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>星穹铁道 · 台词语言学实验室</title>
<style>
:root{{--bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--border:#30363d;--text:#e6edf3;--muted:#8b949e;--accent:#58a6ff;--gold:#e3b341;--green:#3fb950;--red:#f85149;--purple:#c07de0;font-family:'Segoe UI',system-ui,sans-serif}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);min-height:100vh}}
nav{{position:sticky;top:0;z-index:10;background:rgba(13,17,23,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:.2rem;padding:0 1.2rem;overflow-x:auto}}
.brand{{font-weight:800;color:var(--gold);padding:.9rem 1rem .9rem 0;white-space:nowrap}}
.tab{{padding:.9rem 1rem;color:var(--muted);cursor:pointer;border-bottom:3px solid transparent;white-space:nowrap;font-size:.9rem}}
.tab.active{{color:var(--accent);border-color:var(--accent)}}
.page{{display:none;max-width:1200px;margin:0 auto;padding:1.5rem}}
.page.active{{display:block}}
h2{{font-size:1.1rem;margin-bottom:.4rem}}
.sub{{color:var(--muted);font-size:.85rem;margin-bottom:1.2rem;line-height:1.6}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:.8rem}}
.card{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1rem}}
.card h3{{font-size:1rem;display:flex;justify-content:space-between;align-items:baseline}}
.card h3 small{{color:var(--muted);font-weight:400;font-size:.75rem}}
.bar{{display:flex;align-items:center;gap:.5rem;font-size:.75rem;margin:.25rem 0}}
.bar span:first-child{{width:48px;color:var(--muted);text-align:right}}
.bar .o{{flex:1;height:8px;background:var(--bg3);border-radius:4px;overflow:hidden}}
.bar .i{{height:100%;border-radius:4px}}
.bar span:last-child{{width:44px}}
.chips{{display:flex;flex-wrap:wrap;gap:.25rem;margin-top:.5rem}}
.chip{{font-size:.72rem;padding:.12rem .45rem;border-radius:10px;background:rgba(88,166,255,.12);color:var(--accent);border:1px solid rgba(88,166,255,.25)}}
.chip.gold{{background:rgba(227,179,65,.12);color:var(--gold);border-color:rgba(227,179,65,.3)}}
.quote{{font-size:.78rem;color:var(--muted);margin-top:.5rem;line-height:1.5;border-left:2px solid var(--border);padding-left:.5rem}}
input[type=search]{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;color:var(--text);padding:.45rem .9rem;font-size:.9rem;outline:none;width:260px;margin-bottom:1rem}}
select{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;color:var(--text);padding:.45rem .6rem;font-size:.85rem;margin-left:.5rem}}
/* heatmap */
.heat{{overflow:auto;background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1rem}}
.heat table{{border-collapse:collapse;font-size:.68rem}}
.heat th{{color:var(--muted);font-weight:500;padding:2px;white-space:nowrap}}
.heat th.v{{writing-mode:vertical-rl;transform:rotate(180deg);height:64px}}
.heat td{{width:22px;height:22px;text-align:center;cursor:default}}
.pairs{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:.6rem;margin-top:1rem}}
.pair{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:.7rem .9rem;font-size:.85rem;display:flex;justify-content:space-between}}
/* quiz */
.qbox{{max-width:640px;margin:0 auto}}
.qtext{{background:var(--bg2);border:1px solid var(--border);border-radius:14px;padding:1.4rem;font-size:1.05rem;line-height:1.7;margin-bottom:1rem;min-height:110px}}
.opts{{display:grid;grid-template-columns:1fr 1fr;gap:.6rem}}
.opt{{padding:.75rem;border-radius:10px;border:1px solid var(--border);background:var(--bg3);color:var(--text);cursor:pointer;font-size:.95rem}}
.opt:hover{{border-color:var(--accent)}}
.opt.ok{{border-color:var(--green);background:rgba(63,185,80,.15)}}
.opt.bad{{border-color:var(--red);background:rgba(248,81,73,.12)}}
.score{{text-align:center;color:var(--muted);font-size:.85rem;margin:.8rem 0}}
.btn{{padding:.55rem 1.2rem;border:none;border-radius:8px;background:var(--accent);color:#0d1117;font-weight:700;cursor:pointer}}
/* tb */
.stats{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:.7rem;margin-bottom:1.2rem}}
.stat{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:.9rem;text-align:center}}
.stat b{{display:block;font-size:1.5rem;color:var(--accent)}}
.stat span{{font-size:.75rem;color:var(--muted)}}
.tbline{{background:var(--bg2);border:1px solid var(--border);border-radius:12px;padding:1.2rem;font-size:1.05rem;line-height:1.7;min-height:80px;margin-bottom:.8rem}}
.list{{columns:2;column-gap:1.5rem;font-size:.82rem;color:var(--muted);line-height:1.7}}
@media(max-width:640px){{.opts{{grid-template-columns:1fr}}.list{{columns:1}}}}
</style>
</head>
<body>
<nav>
  <div class="brand">✦ 台词语言学实验室</div>
  <div class="tab active" onclick="go('fp',this)">语言指纹</div>
  <div class="tab" onclick="go('sim',this)">谁和谁最像</div>
  <div class="tab" onclick="go('quiz',this)">谁说的？</div>
  <div class="tab" onclick="go('tb',this)">开拓者语料</div>
</nav>

<div class="page active" id="p-fp">
  <h2>角色语言指纹</h2>
  <div class="sub" id="fpSub"></div>
  <input type="search" id="fpSearch" placeholder="搜索角色…" oninput="renderFP()">
  <select id="fpSort" onchange="renderFP()">
    <option value="lines">按台词数</option><option value="avgLen">按平均句长</option>
    <option value="ellipsis">按省略号率</option><option value="exclaim">按感叹号率</option>
    <option value="question">按疑问句率</option><option value="laugh">按笑声率</option>
  </select>
  <label style="font-size:.82rem;color:var(--muted);margin-left:.6rem"><input type="checkbox" id="fpAvatarOnly" checked onchange="renderFP()"> 仅可玩角色</label>
  <div class="grid" id="fpGrid"></div>
</div>

<div class="page" id="p-sim">
  <h2>说话风格相似度</h2>
  <div class="sub">对每位角色的全部台词做字符二元组频率向量，计算余弦相似度。颜色越亮越相似。下方列出最像与最不像的组合。</div>
  <div class="heat" id="heat"></div>
  <h2 style="margin-top:1.4rem">风格最接近的搭档</h2>
  <div class="pairs" id="pairsHi"></div>
  <h2 style="margin-top:1.4rem">风格差异最大的组合</h2>
  <div class="pairs" id="pairsLo"></div>
</div>

<div class="page" id="p-quiz">
  <div class="qbox">
    <h2>这句话是谁说的？</h2>
    <div class="sub">题库来自游戏内真实台词（已去除含角色名的句子）。</div>
    <div class="qtext" id="qText"></div>
    <div class="opts" id="qOpts"></div>
    <div class="score" id="qScore"></div>
    <div style="text-align:center"><button class="btn" onclick="nextQ()">下一题 →</button></div>
  </div>
</div>

<div class="page" id="p-tb">
  <h2>开拓者到底能说什么？</h2>
  <div class="sub">遍历全部剧情脚本，收集所有玩家可选择的对话选项。这是「你」在整个游戏里能说出的所有话。</div>
  <div class="stats" id="tbStats"></div>
  <h2>随机一句开拓者语录</h2>
  <div class="tbline" id="tbLine"></div>
  <button class="btn" onclick="tbRandom()">再来一句</button>
  <h2 style="margin-top:1.6rem">开拓者与垃圾桶</h2>
  <div class="list" id="tbTrash"></div>
</div>

<script>
const D = {payload};
const P = D.profiles;
function go(id,el){{document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.getElementById('p-'+id).classList.add('active');el.classList.add('active');}}

// ── 指纹 ──
document.getElementById('fpSub').textContent = `全游戏 ${{D.totalLines.toLocaleString()}} 条带说话人的台词，${{D.totalSpeakers.toLocaleString()}} 位说话者；以下为台词 ≥ {MIN_LINES} 条的 ${{P.length}} 位。`;
const MAXV = {{avgLen:Math.max(...P.map(p=>p.avgLen)),ellipsis:Math.max(...P.map(p=>p.ellipsis)),exclaim:Math.max(...P.map(p=>p.exclaim)),question:Math.max(...P.map(p=>p.question)),laugh:Math.max(...P.map(p=>p.laugh))}};
function bar(label,v,max,col,unit){{return `<div class="bar"><span>${{label}}</span><div class="o"><div class="i" style="width:${{Math.min(100,v/max*100)}}%;background:${{col}}"></div></div><span>${{v}}${{unit}}</span></div>`;}}
function renderFP(){{
  const q=document.getElementById('fpSearch').value.trim();
  const key=document.getElementById('fpSort').value;
  const onlyAv=document.getElementById('fpAvatarOnly').checked;
  const list=P.filter(p=>(!onlyAv||p.isAvatar)&&(!q||p.name.includes(q))).sort((a,b)=>b[key]-a[key]);
  document.getElementById('fpGrid').innerHTML=list.map(p=>`<div class="card">
    <h3>${{p.name}}<small>${{p.lines.toLocaleString()}} 句 · ${{(p.chars/10000).toFixed(1)}} 万字</small></h3>
    ${{bar('句长',p.avgLen,MAXV.avgLen,'#58a6ff','字')}}
    ${{bar('省略号',p.ellipsis,MAXV.ellipsis,'#8b949e','%')}}
    ${{bar('感叹',p.exclaim,MAXV.exclaim,'#e8533e','%')}}
    ${{bar('疑问',p.question,MAXV.question,'#c07de0','%')}}
    ${{bar('笑声',p.laugh,MAXV.laugh,'#e3b341','%')}}
    <div class="chips">${{p.distinct.map(([w,c])=>`<span class="chip" title="出现 ${{c}} 次">${{w}}</span>`).join('')}}</div>
    ${{Object.keys(p.address).length?`<div class="chips">${{Object.entries(p.address).sort((a,b)=>b[1]-a[1]).slice(0,4).map(([k,v])=>`<span class="chip gold">称呼「${{k==='{{NICKNAME}}'?'你的名字':k}}」×${{v}}</span>`).join('')}}</div>`:''}}
    <div class="quote">最短：「${{p.shortest}}」<br>最长：「${{p.longest}}${{p.longest.length>=120?'…':''}}」</div>
  </div>`).join('');
}}
renderFP();

// ── 相似度 ──
(function(){{
  const N=D.simNames, S=D.sim;
  let html='<table><tr><th></th>'+N.map(n=>`<th class="v">${{n}}</th>`).join('')+'</tr>';
  const vals=[];S.forEach((r,i)=>r.forEach((v,j)=>{{if(i!==j)vals.push(v)}}));
  const lo=Math.min(...vals),hi=Math.max(...vals);
  S.forEach((row,i)=>{{html+=`<tr><th style="text-align:right">${{N[i]}}</th>`+row.map((v,j)=>{{const t=i===j?1:(v-lo)/(hi-lo);const c=`rgba(88,166,255,${{(0.08+t*0.92).toFixed(2)}})`;return `<td style="background:${{c}}" title="${{N[i]}} × ${{N[j]}} = ${{v}}"></td>`}}).join('')+'</tr>'}});
  document.getElementById('heat').innerHTML=html+'</table>';
  const pairs=[];for(let i=0;i<N.length;i++)for(let j=i+1;j<N.length;j++)pairs.push([N[i],N[j],S[i][j]]);
  pairs.sort((a,b)=>b[2]-a[2]);
  const f=p=>`<div class="pair"><span>${{p[0]}} × ${{p[1]}}</span><b>${{p[2].toFixed(3)}}</b></div>`;
  document.getElementById('pairsHi').innerHTML=pairs.slice(0,12).map(f).join('');
  document.getElementById('pairsLo').innerHTML=pairs.slice(-12).reverse().map(f).join('');
}})();

// ── 竞猜 ──
const NAMES=[...new Set(D.quiz.map(q=>q.s))];
let qi=0,qScore=0,qTotal=0,answered=false;
function nextQ(){{
  answered=false;const q=D.quiz[qi++%D.quiz.length];
  const opts=new Set([q.s]);while(opts.size<4)opts.add(NAMES[Math.floor(Math.random()*NAMES.length)]);
  const arr=[...opts].sort(()=>Math.random()-.5);
  document.getElementById('qText').textContent='「'+q.t+'」';
  document.getElementById('qOpts').innerHTML=arr.map(n=>`<button class="opt" onclick="answer(this,'${{n}}','${{q.s}}')">${{n}}</button>`).join('');
  document.getElementById('qScore').textContent=qTotal?`已答 ${{qTotal}} 题，正确 ${{qScore}}（${{Math.round(qScore/qTotal*100)}}%）`:'';
}}
function answer(btn,n,s){{if(answered)return;answered=true;qTotal++;if(n===s){{qScore++;btn.classList.add('ok')}}else{{btn.classList.add('bad');[...document.querySelectorAll('.opt')].find(b=>b.textContent===s).classList.add('ok')}}document.getElementById('qScore').textContent=`已答 ${{qTotal}} 题，正确 ${{qScore}}（${{Math.round(qScore/qTotal*100)}}%）`;}}
nextQ();

// ── 开拓者 ──
const TB=D.tb;
document.getElementById('tbStats').innerHTML=[
 [TB.total.toLocaleString(),'可选台词总数'],[TB.avgLen+' 字','平均长度'],[TB.paren.toLocaleString(),'括号内心独白'],[TB.ellipsis.toLocaleString(),'带省略号'],[TB.question.toLocaleString(),'反问/疑问'],[TB.exclaim.toLocaleString(),'感叹句'],[TB.trash,'提到垃圾桶']
].map(([v,l])=>`<div class="stat"><b>${{v}}</b><span>${{l}}</span></div>`).join('');
function tbRandom(){{document.getElementById('tbLine').textContent='「'+TB.sample[Math.floor(Math.random()*TB.sample.length)]+'」';}}
tbRandom();
document.getElementById('tbTrash').innerHTML=TB.trashLines.map(l=>`<div>· ${{l}}</div>`).join('')||'<div>（无）</div>';
</script>
</body>
</html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="..")
    ap.add_argument("--output", default="hsr_linguistics.html")
    args = ap.parse_args()
    print("分析台词语料…")
    data = build(args.data_root)
    print(f"  {data['totalLines']:,} 条带说话人台词，{len(data['profiles'])} 位角色进入指纹分析")
    print(f"  开拓者可选台词 {data['tb']['total']:,} 条，竞猜题 {len(data['quiz'])} 题")
    out = args.output if os.path.isabs(args.output) else os.path.join(os.path.dirname(__file__), args.output)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render_html(data))
    print(f"✓ 生成完毕 → {out}  ({os.path.getsize(out) // 1024} KB)")


if __name__ == "__main__":
    main()
