# -*- coding: utf-8 -*-
"""ETF 파인더 — 개별 종목을 가장 많이 담은 ETF 검색

실행: uvicorn server:app --host 0.0.0.0 --port 8400
데이터: data/holdings.json (collector.py 가 생성)
"""
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

DATA_PATH = Path(__file__).parent / "data" / "holdings.json"

app = FastAPI(title="ETF Finder")

_cache = {"mtime": None, "data": None, "index": None, "names": None}


def load():
    """holdings.json 로드 + 종목명 역인덱스 빌드 (파일 변경시 자동 리로드)"""
    mtime = DATA_PATH.stat().st_mtime
    if _cache["mtime"] == mtime:
        return
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    index = {}  # 종목명 -> [ {etf코드, 비중, 수량} ]
    for etf_code, holdings in data["holdings"].items():
        for h in holdings:
            index.setdefault(h["name"], []).append(
                {"etf": etf_code, "weight": h["weight"], "count": h["count"]}
            )
    _cache.update(
        mtime=mtime, data=data, index=index,
        names=sorted(index.keys(), key=lambda n: -len(index[n])),
    )


@app.get("/api/meta")
def meta():
    load()
    d = _cache["data"]
    return {
        "baseDate": d["baseDate"],
        "collectedAt": d["collectedAt"],
        "etfCount": len(d["holdings"]),
        "stockCount": len(_cache["index"]),
    }


@app.get("/api/suggest")
def suggest(q: str = ""):
    load()
    q = q.strip().lower()
    if not q:
        return []
    names = _cache["names"]
    starts = [n for n in names if n.lower().startswith(q)]
    contains = [n for n in names if q in n.lower() and not n.lower().startswith(q)]
    return [
        {"name": n, "etfCount": len(_cache["index"][n])}
        for n in (starts + contains)[:15]
    ]


@app.get("/api/stock")
def stock(name: str):
    load()
    rows = _cache["index"].get(name)
    if rows is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    etfs = _cache["data"]["etfs"]
    out = []
    for r in rows:
        e = etfs.get(r["etf"], {})
        market_sum = e.get("marketSum")  # 억원
        amount = None
        if r["weight"] is not None and market_sum:
            amount = round(r["weight"] / 100 * market_sum, 1)  # 억원
        out.append({
            "etfCode": r["etf"],
            "etfName": e.get("name", r["etf"]),
            "weight": r["weight"],
            "count": r["count"],
            "marketSum": market_sum,
            "amount": amount,
        })
    # 비중순 → 비중 없으면(해외) 보유수량순
    out.sort(key=lambda x: (x["weight"] is None, -(x["weight"] or 0), -(x["count"] or 0)))
    return {"name": name, "baseDate": _cache["data"]["baseDate"], "etfs": out}


HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ETF 파인더</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:'Segoe UI','Malgun Gothic',sans-serif; background:#0f1419; color:#e7e9ea; min-height:100vh; }
  .wrap { max-width:860px; margin:0 auto; padding:24px 16px; }
  h1 { font-size:22px; margin-bottom:4px; }
  .meta { color:#71767b; font-size:12px; margin-bottom:20px; }
  .searchbox { position:relative; margin-bottom:20px; }
  #q { width:100%; padding:14px 16px; font-size:17px; border-radius:12px; border:1px solid #333;
       background:#1c2128; color:#e7e9ea; outline:none; }
  #q:focus { border-color:#1d9bf0; }
  #sug { position:absolute; top:100%; left:0; right:0; background:#1c2128; border:1px solid #333;
         border-radius:0 0 12px 12px; z-index:10; display:none; max-height:360px; overflow-y:auto; }
  .sug-item { padding:10px 16px; cursor:pointer; display:flex; justify-content:space-between; }
  .sug-item:hover, .sug-item.active { background:#273340; }
  .sug-item .cnt { color:#71767b; font-size:12px; }
  .result-head { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px; flex-wrap:wrap; gap:8px; }
  .result-head h2 { font-size:18px; }
  .result-head .sub { color:#71767b; font-size:13px; }
  .sortbtns button { background:#1c2128; color:#9aa0a6; border:1px solid #333; padding:5px 12px;
                     border-radius:16px; cursor:pointer; font-size:12px; margin-left:4px; }
  .sortbtns button.on { background:#1d9bf0; color:#fff; border-color:#1d9bf0; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th { text-align:right; color:#71767b; font-weight:600; font-size:12px; padding:8px 10px;
       border-bottom:1px solid #333; white-space:nowrap; }
  th:first-child, td:first-child { text-align:left; }
  td { padding:9px 10px; border-bottom:1px solid #21262d; text-align:right; white-space:nowrap; }
  td.name { text-align:left; max-width:340px; overflow:hidden; text-overflow:ellipsis; }
  td.name a { color:#e7e9ea; text-decoration:none; }
  td.name a:hover { color:#1d9bf0; }
  .rank { color:#71767b; font-size:12px; }
  .w { color:#00ba7c; font-weight:700; }
  .bar { display:inline-block; height:4px; background:#00ba7c; border-radius:2px; vertical-align:middle; margin-left:6px; opacity:.6; }
  .dim { color:#71767b; }
  .empty { color:#71767b; text-align:center; padding:60px 0; }
  @media (max-width:600px){ .hide-m{display:none;} td,th{padding:8px 6px;} }
</style>
</head>
<body>
<div class="wrap">
  <h1>📊 ETF 파인더</h1>
  <div class="meta" id="meta">로딩중…</div>
  <div class="searchbox">
    <input id="q" placeholder="종목명 입력 (예: 삼성전자, 한미반도체, NVIDIA)" autocomplete="off">
    <div id="sug"></div>
  </div>
  <div id="result"><div class="empty">종목을 검색하면 해당 종목을 담고 있는 모든 ETF가 비중순으로 표시됩니다.</div></div>
</div>
<script>
let curName = null, curData = null, sortKey = 'weight', selIdx = -1;

fetch('/api/meta').then(r=>r.json()).then(m=>{
  document.getElementById('meta').textContent =
    '기준일 ' + (m.baseDate||'-') + ' · ETF ' + m.etfCount.toLocaleString() + '개 · 종목 ' + m.stockCount.toLocaleString() + '개 수록';
});

const q = document.getElementById('q'), sug = document.getElementById('sug');
let timer = null;

q.addEventListener('input', () => {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const v = q.value.trim();
    if (!v) { sug.style.display='none'; return; }
    const items = await (await fetch('/api/suggest?q='+encodeURIComponent(v))).json();
    selIdx = -1;
    if (!items.length) { sug.style.display='none'; return; }
    sug.innerHTML = items.map(it =>
      '<div class="sug-item" data-name="'+it.name+'"><span>'+it.name+'</span><span class="cnt">'+it.etfCount+'개 ETF</span></div>'
    ).join('');
    sug.style.display='block';
    sug.querySelectorAll('.sug-item').forEach(el =>
      el.addEventListener('click', () => pick(el.dataset.name)));
  }, 150);
});

q.addEventListener('keydown', e => {
  const items = sug.querySelectorAll('.sug-item');
  if (e.key === 'ArrowDown' && items.length) { selIdx = Math.min(selIdx+1, items.length-1); paint(items); e.preventDefault(); }
  else if (e.key === 'ArrowUp' && items.length) { selIdx = Math.max(selIdx-1, 0); paint(items); e.preventDefault(); }
  else if (e.key === 'Enter') {
    if (selIdx >= 0 && items[selIdx]) pick(items[selIdx].dataset.name);
    else if (items.length) pick(items[0].dataset.name);
  } else if (e.key === 'Escape') sug.style.display='none';
});
function paint(items){ items.forEach((el,i)=>el.classList.toggle('active', i===selIdx)); }
document.addEventListener('click', e => { if (!e.target.closest('.searchbox')) sug.style.display='none'; });

async function pick(name){
  sug.style.display='none'; q.value = name;
  const r = await fetch('/api/stock?name='+encodeURIComponent(name));
  if (!r.ok) return;
  curName = name; curData = await r.json();
  render();
}

function render(){
  const d = curData;
  const rows = [...d.etfs];
  if (sortKey === 'weight') rows.sort((a,b)=>((b.weight??-1)-(a.weight??-1)) || ((b.count??0)-(a.count??0)));
  else rows.sort((a,b)=>((b.amount??-1)-(a.amount??-1)) || ((b.count??0)-(a.count??0)));
  const noWeight = rows.length && rows.every(r=>r.weight==null);
  const maxW = Math.max(...rows.map(r=>r.weight??0), 0.001);
  const html = ['<div class="result-head">',
    '<div><h2>'+d.name+'</h2><span class="sub">'+rows.length+'개 ETF 보유 · 기준일 '+(d.baseDate||'-')+'</span></div>',
    '<div class="sortbtns">',
    '<button id="sw" class="'+(sortKey==='weight'?'on':'')+'">비중순</button>',
    '<button id="sa" class="'+(sortKey==='amount'?'on':'')+'">금액순</button>',
    '</div></div>',
    noWeight ? '<div class="meta" style="margin-bottom:8px">⚠️ 해외 종목은 비중(%)이 제공되지 않아 1CU당 보유수량 순으로 표시됩니다.</div>' : '',
    '<table><tr><th>ETF</th><th>비중</th><th class="hide-m">보유수량/1CU</th><th>평가금액(억)</th><th class="hide-m">ETF시총(억)</th></tr>'];
  rows.forEach((r,i)=>{
    const w = r.weight==null ? '<span class="dim">-</span>'
      : '<span class="w">'+r.weight.toFixed(2)+'%</span><span class="bar" style="width:'+Math.round(r.weight/maxW*40)+'px"></span>';
    html.push('<tr>',
      '<td class="name"><span class="rank">'+(i+1)+'</span> <a href="https://finance.naver.com/item/main.naver?code='+r.etfCode+'" target="_blank">'+r.etfName+'</a></td>',
      '<td>'+w+'</td>',
      '<td class="hide-m dim">'+(r.count==null?'-':Number(r.count).toLocaleString())+'</td>',
      '<td>'+(r.amount==null?'<span class="dim">-</span>':r.amount.toLocaleString())+'</td>',
      '<td class="hide-m dim">'+(r.marketSum==null?'-':Number(r.marketSum).toLocaleString())+'</td>',
      '</tr>');
  });
  html.push('</table>');
  document.getElementById('result').innerHTML = html.join('');
  document.getElementById('sw').onclick = ()=>{ sortKey='weight'; render(); };
  document.getElementById('sa').onclick = ()=>{ sortKey='amount'; render(); };
}
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML
