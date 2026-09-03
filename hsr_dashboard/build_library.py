"""
星穹铁道 · 游戏内藏书馆
提取 1018 本游戏内书籍全文，生成可搜索、可阅读的静态图书馆 HTML。

用法: python build_library.py [--data-root ..] [--output hsr_library.html]
"""

import json
import os
import re
import argparse


WORLD_ZH = {
    1: "星穹列车 / 贝洛伯格",
    2: "仙舟「罗浮」",
    3: "匹诺康尼",
    4: "翁法罗斯 / 赤霞旧土",
    5: "阿米兰星系 / 其他",
    6: "无主荒星 / 外宇宙",
    0: "未分类",
}
WORLD_COLOR = {
    1: "#5bb8d4", 2: "#e3b341", 3: "#c07de0",
    4: "#e05c5c", 5: "#4db89b", 6: "#7b68ee", 0: "#8b949e",
}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def clean_text(s: str) -> str:
    """Remove rich-text markup and normalize whitespace."""
    s = re.sub(r"<align[^>]*>|</align>", "", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = re.sub(r"\\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def build_library(data_root: str, tm: dict) -> list:
    lb = load_json(f"{data_root}/ExcelOutput/LocalbookConfig.json")
    bs = load_json(f"{data_root}/ExcelOutput/BookSeriesConfig.json")

    series_map = {}
    for s in bs:
        sid = s["BookSeriesID"]
        name_h = s.get("BookSeries", {})
        if isinstance(name_h, dict):
            name_h = name_h.get("Hash", 0)
        name = tm.get(str(name_h), "")
        series_map[sid] = {
            "name":  name,
            "world": s.get("BookSeriesWorld", 0),
            "num":   s.get("BookSeriesNum", 0),
        }

    books_by_series: dict = {}
    for b in lb:
        sid = b["BookSeriesID"]
        content_h = b.get("BookContent", {})
        if isinstance(content_h, dict):
            content_h = content_h.get("Hash", 0)
        content = clean_text(tm.get(str(content_h), ""))
        if not content:
            continue

        inside_name_h = b.get("BookInsideName", {})
        if isinstance(inside_name_h, dict):
            inside_name_h = inside_name_h.get("Hash", 0)
        inside_name = tm.get(str(inside_name_h), "")

        books_by_series.setdefault(sid, []).append({
            "id":       b["BookID"],
            "vol":      b.get("BookSeriesInsideID", 1),
            "title":    inside_name,
            "content":  content,
            "length":   len(content),
        })

    # Sort volumes within each series
    result = []
    for sid, books in books_by_series.items():
        s = series_map.get(sid, {})
        if not s.get("name"):
            # Use first book title as series name
            books.sort(key=lambda b: b["vol"])
            s["name"] = books[0]["title"] or f"书籍 #{sid}"
        books.sort(key=lambda b: b["vol"])
        total_len = sum(b["length"] for b in books)
        result.append({
            "seriesID": sid,
            "name":     s["name"],
            "world":    s.get("world", 0),
            "volumes":  len(books),
            "length":   total_len,
            "books":    books,
        })

    result.sort(key=lambda s: (s["world"], s["name"]))
    return result


def render_html(library: list) -> str:
    lib_json       = json.dumps(library,    ensure_ascii=False)
    world_zh_json  = json.dumps(WORLD_ZH,   ensure_ascii=False)
    world_col_json = json.dumps(WORLD_COLOR, ensure_ascii=False)

    total_books  = sum(s["volumes"] for s in library)
    total_chars  = sum(s["length"]  for s in library)
    total_series = len(library)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>星穹铁道 · 游戏内藏书馆</title>
<style>
:root {{
  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;
  --border:#30363d;--text:#e6edf3;--muted:#8b949e;--accent:#58a6ff;
  --gold:#e3b341;
  font-family:'Segoe UI',system-ui,sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);min-height:100vh}}

/* ── Layout ── */
.layout{{display:grid;grid-template-columns:320px 1fr;min-height:100vh}}
@media(max-width:700px){{.layout{{grid-template-columns:1fr}}}}

/* ── Sidebar ── */
.sidebar{{
  background:var(--bg2);border-right:1px solid var(--border);
  display:flex;flex-direction:column;height:100vh;position:sticky;top:0;overflow:hidden;
}}
.sidebar-header{{padding:1.2rem 1rem .8rem;border-bottom:1px solid var(--border)}}
.sidebar-header h1{{
  font-size:1.1rem;font-weight:800;
  background:linear-gradient(135deg,#e3b341,#58a6ff);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
}}
.sidebar-stats{{font-size:.75rem;color:var(--muted);margin-top:.3rem}}
.search-wrap{{padding:.75rem 1rem;border-bottom:1px solid var(--border)}}
.search-input{{
  width:100%;padding:.45rem .8rem;background:var(--bg3);
  border:1px solid var(--border);border-radius:8px;color:var(--text);
  font-size:.88rem;outline:none;transition:border-color .15s
}}
.search-input:focus{{border-color:var(--accent)}}
.world-filters{{display:flex;flex-wrap:wrap;gap:.3rem;padding:.5rem 1rem;border-bottom:1px solid var(--border)}}
.world-btn{{
  font-size:.7rem;padding:.2rem .5rem;border-radius:10px;cursor:pointer;
  border:1px solid transparent;transition:all .15s;background:var(--bg3);color:var(--muted)
}}
.world-btn.active{{font-weight:600}}
.book-list{{flex:1;overflow-y:auto;padding:.5rem 0}}
.series-item{{
  padding:.5rem 1rem;cursor:pointer;border-left:3px solid transparent;
  transition:all .15s;
}}
.series-item:hover{{background:var(--bg3)}}
.series-item.active{{background:var(--bg3);border-left-color:var(--accent)}}
.series-name{{font-size:.85rem;font-weight:500;line-height:1.3}}
.series-meta{{font-size:.72rem;color:var(--muted);margin-top:.15rem}}
.series-world-dot{{
  display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:.3rem
}}

/* ── Reader ── */
.reader{{padding:2rem;max-width:760px}}
.reader-placeholder{{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  height:60vh;color:var(--muted);text-align:center;gap:.5rem
}}
.reader-placeholder .icon{{font-size:3rem}}
.reader-header{{margin-bottom:1.5rem}}
.reader-header h2{{font-size:1.4rem;font-weight:700;line-height:1.3;margin-bottom:.4rem}}
.reader-meta{{font-size:.82rem;color:var(--muted);display:flex;flex-wrap:wrap;gap:.5rem}}
.meta-badge{{
  display:inline-block;padding:.2rem .5rem;border-radius:8px;
  font-size:.72rem;font-weight:600;
}}
.vol-tabs{{display:flex;gap:.4rem;margin-bottom:1.5rem;flex-wrap:wrap}}
.vol-tab{{
  padding:.35rem .75rem;border-radius:8px;border:1px solid var(--border);
  background:var(--bg2);color:var(--muted);cursor:pointer;font-size:.82rem;
  transition:all .15s
}}
.vol-tab:hover{{border-color:var(--accent)}}
.vol-tab.active{{background:var(--accent);border-color:var(--accent);color:#0d1117;font-weight:600}}
.book-text{{
  font-size:.95rem;line-height:1.9;color:#cdd6e0;
  white-space:pre-wrap;word-break:break-word;
}}
.book-text em{{color:var(--muted);font-style:italic}}
.book-text strong{{color:var(--gold)}}

/* ── Scrollbar ── */
::-webkit-scrollbar{{width:6px}}
::-webkit-scrollbar-track{{background:var(--bg2)}}
::-webkit-scrollbar-thumb{{background:var(--border);border-radius:3px}}

/* ── Search highlight ── */
mark{{background:rgba(227,179,65,.3);color:var(--gold);border-radius:2px;padding:0 1px}}
</style>
</head>
<body>

<div class="layout">
  <!-- Sidebar -->
  <div class="sidebar">
    <div class="sidebar-header">
      <h1>📚 星穹藏书馆</h1>
      <div class="sidebar-stats">{total_series} 个系列 · {total_books} 册 · 约 {total_chars // 500} 页</div>
    </div>
    <div class="search-wrap">
      <input type="search" class="search-input" id="searchInput"
        placeholder="搜索书名或正文内容…" oninput="onSearch()">
    </div>
    <div class="world-filters" id="worldFilters"></div>
    <div class="book-list" id="bookList"></div>
  </div>

  <!-- Reader -->
  <div class="reader" id="reader">
    <div class="reader-placeholder">
      <div class="icon">✦</div>
      <div style="font-size:1.1rem;font-weight:600">星穹藏书馆</div>
      <div style="font-size:.85rem">从左侧选择一本书开始阅读</div>
      <div style="font-size:.78rem;margin-top:.5rem">{total_chars:,} 字的星际见闻在此等候</div>
    </div>
  </div>
</div>

<script>
const LIB       = {lib_json};
const WORLD_ZH  = {world_zh_json};
const WORLD_COL = {world_col_json};

let activeWorld  = 'all';
let activeSearch = '';
let activeSeries = null;
let activeVol    = 0;

// ── World filter buttons ──
const worlds = [...new Set(LIB.map(s => s.world))].sort();
const wf = document.getElementById('worldFilters');
wf.innerHTML = '<button class="world-btn active" data-world="all" onclick="setWorld(\'all\',this)">全部</button>' +
  worlds.map(w => {{
    const col = WORLD_COL[w] || '#888';
    const cnt = LIB.filter(s => s.world === w).length;
    return `<button class="world-btn" data-world="${{w}}" onclick="setWorld(${{w}},this)"
      style="border-color:${{col}}44;color:${{col}}">${{WORLD_ZH[w]||w}} (${{cnt}})</button>`;
  }}).join('');

function setWorld(w, btn) {{
  activeWorld = w;
  document.querySelectorAll('.world-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderList();
}}

// ── Search ──
function onSearch() {{
  activeSearch = document.getElementById('searchInput').value.toLowerCase();
  renderList();
}}

// ── Book list ──
function renderList() {{
  const q = activeSearch;
  const filtered = LIB.filter(s =>
    (activeWorld === 'all' || s.world === activeWorld) &&
    (!q || s.name.toLowerCase().includes(q) ||
      s.books.some(b => b.title.toLowerCase().includes(q) || b.content.toLowerCase().includes(q)))
  );

  const list = document.getElementById('bookList');
  if (!filtered.length) {{
    list.innerHTML = '<div style="padding:1rem;color:var(--muted);font-size:.85rem">未找到匹配的书籍</div>';
    return;
  }}

  list.innerHTML = filtered.map(s => {{
    const col = WORLD_COL[s.world] || '#888';
    const isActive = activeSeries && activeSeries.seriesID === s.seriesID;
    const pagesEst = Math.round(s.length / 500);
    return `<div class="series-item ${{isActive?'active':''}}" onclick="openSeries(${{s.seriesID}})">
      <div class="series-name">
        <span class="series-world-dot" style="background:${{col}}"></span>${{s.name}}
      </div>
      <div class="series-meta">${{s.volumes > 1 ? s.volumes + ' 册 · ' : ''}}约 ${{pagesEst}} 页</div>
    </div>`;
  }}).join('');
}}

// ── Open series ──
function openSeries(seriesID) {{
  activeSeries = LIB.find(s => s.seriesID === seriesID);
  if (!activeSeries) return;
  activeVol = 0;
  renderReader();
  // Update sidebar highlight
  document.querySelectorAll('.series-item').forEach(el => el.classList.remove('active'));
  const items = document.querySelectorAll('.series-item');
  // Re-render list to update active state
  renderList();
  document.getElementById('reader').scrollTop = 0;
}}

// ── Reader ──
function renderReader() {{
  if (!activeSeries) return;
  const s  = activeSeries;
  const b  = s.books[activeVol];
  const col = WORLD_COL[s.world] || '#888';
  const q   = activeSearch;

  const volTabs = s.books.length > 1
    ? `<div class="vol-tabs">${{s.books.map((bk,i) =>
        `<button class="vol-tab ${{i===activeVol?'active':''}}" onclick="setVol(${{i}})">${{bk.title || '第'+(i+1)+'册'}}</button>`
      ).join('')}}</div>` : '';

  // Highlight search terms
  let text = escHtml(b.content);
  if (q) {{
    const re = new RegExp(q.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&'), 'gi');
    text = text.replace(re, m => `<mark>${{m}}</mark>`);
  }}
  // Style italics (*...*)
  text = text.replace(/\\*([^*\\n]+)\\*/g, '<em>$1</em>');
  // Style 【headers】
  text = text.replace(/【([^】]+)】/g, '<strong>【$1】</strong>');

  document.getElementById('reader').innerHTML = `
    <div class="reader-header">
      <h2>${{escHtml(s.name)}}</h2>
      <div class="reader-meta">
        <span class="meta-badge" style="background:${{col}}22;color:${{col}};border:1px solid ${{col}}44">${{WORLD_ZH[s.world]||s.world}}</span>
        <span style="color:var(--muted)">${{s.volumes}} 册 · ${{s.length.toLocaleString()}} 字</span>
        ${{b.title && b.title !== s.name ? `<span style="color:var(--muted)">${{escHtml(b.title)}}</span>` : ''}}
      </div>
    </div>
    ${{volTabs}}
    <div class="book-text">${{text}}</div>`;
}}

function setVol(i) {{
  activeVol = i;
  renderReader();
  document.getElementById('reader').scrollTop = 0;
}}

function escHtml(s) {{
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}}

// ── Init ──
renderList();
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="..")
    parser.add_argument("--output",    default="hsr_library.html")
    args = parser.parse_args()

    print("加载 TextMap…")
    tm = load_json(f"{args.data_root}/TextMap/TextMapCHS.json")
    print("构建书库数据…")
    library = build_library(args.data_root, tm)
    total_books  = sum(s["volumes"] for s in library)
    total_chars  = sum(s["length"]  for s in library)
    print(f"  {len(library)} 个系列 · {total_books} 册 · {total_chars:,} 字")

    html = render_html(library)
    out = args.output if os.path.isabs(args.output) else os.path.join(os.path.dirname(__file__), args.output)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ 生成完毕 → {out}  ({os.path.getsize(out)//1024} KB)")


if __name__ == "__main__":
    main()
