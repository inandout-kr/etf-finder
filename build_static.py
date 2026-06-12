# -*- coding: utf-8 -*-
"""정적 사이트 빌드: data/holdings.json -> dist/

dist/
  index.html          메인 페이지 (검색 UI)
  about.html          사이트 소개/사용법
  privacy.html        개인정보처리방침
  meta.json           기준일/통계
  names.json          자동완성용 전체 종목명 [[이름, ETF수], ...]
  shard/{00..ff}.json 종목명 FNV-1a 해시 256분할 { 이름: [[etf코드,etf명,비중,수량,시총,평가액], ...] }

사용: python build_static.py  (collector.py 실행 후)
배포: npx wrangler pages deploy dist --project-name etf-finder
"""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
SHARDS = 256


def fnv1a(s: str) -> int:
    h = 2166136261
    for b in s.encode("utf-8"):
        h ^= b
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def build():
    t0 = time.time()
    data = json.loads((ROOT / "data" / "holdings.json").read_text(encoding="utf-8"))
    etfs = data["etfs"]

    # 역인덱스: 종목명 -> [(etf코드, etf명, 비중, 수량, 시총, 평가액)]
    index = {}
    for etf_code, holdings in data["holdings"].items():
        e = etfs.get(etf_code, {})
        market_sum = e.get("marketSum")
        for h in holdings:
            w = h["weight"]
            amount = round(w / 100 * market_sum, 1) if (w is not None and market_sum) else None
            index.setdefault(h["name"], []).append(
                [etf_code, e.get("name", etf_code), w, h["count"], market_sum, amount]
            )
    # 비중순 -> 수량순 정렬
    for rows in index.values():
        rows.sort(key=lambda r: (r[2] is None, -(r[2] or 0), -(r[3] or 0)))

    # Windows에서 폴더 핸들 잠금으로 rmdir이 실패할 수 있어 폴더는 재사용하고 파일만 삭제
    if DIST.exists():
        for f in sorted(DIST.rglob("*"), reverse=True):
            if f.is_file():
                f.unlink()
    (DIST / "shard").mkdir(parents=True, exist_ok=True)

    # 샤드 분할
    shards = [{} for _ in range(SHARDS)]
    for name, rows in index.items():
        shards[fnv1a(name) % SHARDS][name] = rows
    for i, sh in enumerate(shards):
        (DIST / "shard" / f"{i:02x}.json").write_text(
            json.dumps(sh, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # 자동완성: ETF수 내림차순
    names = sorted(index.items(), key=lambda kv: -len(kv[1]))
    (DIST / "names.json").write_text(
        json.dumps([[n, len(r)] for n, r in names], ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")

    (DIST / "meta.json").write_text(json.dumps({
        "baseDate": data["baseDate"],
        "collectedAt": data["collectedAt"],
        "etfCount": len(data["holdings"]),
        "stockCount": len(index),
    }, ensure_ascii=False), encoding="utf-8")

    # 정적 페이지
    for fname, content in PAGES.items():
        (DIST / fname).write_text(content, encoding="utf-8")

    total = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    print(f"DONE in {time.time()-t0:.1f}s")
    print(f"  stocks: {len(index)}, shards: {SHARDS}")
    print(f"  dist size: {total/1e6:.1f} MB, files: {sum(1 for f in DIST.rglob('*') if f.is_file())}")


# ---------------------------------------------------------------- HTML -----

STYLE = """
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,'Segoe UI','Malgun Gothic','Apple SD Gothic Neo',sans-serif;
         background:#fff; color:#212529; min-height:100vh; }
  .wrap { max-width:860px; margin:0 auto; padding:32px 16px; }
  h1 { font-size:21px; font-weight:700; margin-bottom:4px; letter-spacing:-0.3px; }
  h1 a { color:#212529; text-decoration:none; }
  .meta { color:#868e96; font-size:12px; margin-bottom:24px; }
  .searchbox { position:relative; margin-bottom:24px; }
  #q { width:100%; padding:13px 16px; font-size:16px; border-radius:8px; border:1px solid #ced4da;
       background:#fff; color:#212529; outline:none; }
  #q:focus { border-color:#1c64d9; box-shadow:0 0 0 3px rgba(28,100,217,.1); }
  #sug { position:absolute; top:calc(100% + 4px); left:0; right:0; background:#fff; border:1px solid #dee2e6;
         border-radius:8px; z-index:10; display:none; max-height:360px; overflow-y:auto;
         box-shadow:0 4px 16px rgba(0,0,0,.08); }
  .sug-item { padding:10px 16px; cursor:pointer; display:flex; justify-content:space-between; }
  .sug-item:hover, .sug-item.active { background:#f1f3f5; }
  .sug-item .cnt { color:#868e96; font-size:12px; }
  .result-head { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:10px; flex-wrap:wrap; gap:8px; }
  .result-head h2 { font-size:18px; font-weight:700; }
  .result-head .sub { color:#868e96; font-size:13px; }
  .sortbtns button { background:#fff; color:#495057; border:1px solid #ced4da; padding:5px 12px;
                     border-radius:6px; cursor:pointer; font-size:12px; margin-left:4px; }
  .sortbtns button.on { background:#1c64d9; color:#fff; border-color:#1c64d9; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th { text-align:right; color:#868e96; font-weight:600; font-size:12px; padding:8px 10px;
       border-bottom:1px solid #dee2e6; white-space:nowrap; }
  th:first-child, td:first-child { text-align:left; }
  td { padding:10px; border-bottom:1px solid #f1f3f5; text-align:right; white-space:nowrap; }
  td.name { text-align:left; max-width:340px; overflow:hidden; text-overflow:ellipsis; }
  td.name a { color:#212529; text-decoration:none; }
  td.name a:hover { color:#1c64d9; text-decoration:underline; }
  .rank { color:#adb5bd; font-size:12px; }
  .w { color:#1c64d9; font-weight:700; }
  .bar { display:inline-block; height:4px; background:#a5c4f3; border-radius:2px; vertical-align:middle; margin-left:6px; }
  .dim { color:#adb5bd; }
  .empty { color:#868e96; text-align:center; padding:60px 0; font-size:14px; }
  .notice { color:#868e96; font-size:12px; margin-bottom:8px; }
  .adslot { margin:20px 0; min-height:0; text-align:center; }
  footer { margin-top:48px; padding-top:16px; border-top:1px solid #f1f3f5; color:#adb5bd;
           font-size:12px; display:flex; gap:16px; flex-wrap:wrap; }
  footer a { color:#868e96; }
  .doc { line-height:1.8; font-size:14px; }
  .doc h2 { font-size:16px; margin:24px 0 8px; }
  .doc p, .doc li { color:#495057; margin-bottom:8px; }
  .doc ul { padding-left:20px; }
  @media (max-width:600px){ .hide-m{display:none;} td,th{padding:8px 6px;} }
"""

FOOTER = """
<footer>
  <a href="./">홈</a>
  <a href="about.html">사이트 소개</a>
  <a href="privacy.html">개인정보처리방침</a>
  <span>데이터: 전일 종가 기준, 정보 제공 목적이며 투자 권유가 아닙니다.</span>
</footer>
"""

# 애드센스 발급 후 아래 주석을 실제 코드로 교체
AD_HEAD = "<!-- ADSENSE: <script async src=\"https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-XXXX\" crossorigin=\"anonymous\"></script> -->"
AD_SLOT = '<div class="adslot"><!-- ADSENSE SLOT --></div>'

INDEX_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ETF 파인더 — 내 종목을 가장 많이 담은 ETF 찾기</title>
<meta name="description" content="종목명을 검색하면 그 종목을 담고 있는 모든 국내 상장 ETF를 보유 비중 순으로 보여줍니다. 매일 전일 종가 기준 업데이트.">
__AD_HEAD__
<style>__STYLE__</style>
</head>
<body>
<div class="wrap">
  <h1><a href="./">ETF 파인더</a></h1>
  <div class="meta" id="meta">로딩중…</div>
  <div class="searchbox">
    <input id="q" placeholder="종목명 입력 (예: 삼성전자, 한미반도체, NVIDIA)" autocomplete="off">
    <div id="sug"></div>
  </div>
  __AD_SLOT__
  <div id="result"><div class="empty">종목을 검색하면 해당 종목을 담고 있는 모든 ETF가 비중순으로 표시됩니다.</div></div>
  __FOOTER__
</div>
<script>
let names = null, curData = null, sortKey = 'weight', selIdx = -1;
const shardCache = {};

function fnv1a(s){
  const b = new TextEncoder().encode(s);
  let h = 2166136261;
  for (const x of b){ h ^= x; h = Math.imul(h, 16777619) >>> 0; }
  return h >>> 0;
}

fetch('meta.json').then(r=>r.json()).then(m=>{
  document.getElementById('meta').textContent =
    '기준일 ' + (m.baseDate||'-') + ' · ETF ' + m.etfCount.toLocaleString() + '개 · 종목 ' + m.stockCount.toLocaleString() + '개 수록';
});

async function loadNames(){
  if (!names) names = await (await fetch('names.json')).json();
  return names;
}

const q = document.getElementById('q'), sug = document.getElementById('sug');
let timer = null;

q.addEventListener('input', () => {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const v = q.value.trim().toLowerCase();
    if (!v) { sug.style.display='none'; return; }
    const all = await loadNames();
    const starts = [], contains = [];
    for (const [n, c] of all) {
      const ln = n.toLowerCase();
      if (ln.startsWith(v)) starts.push([n, c]);
      else if (ln.includes(v)) contains.push([n, c]);
      if (starts.length >= 15) break;
    }
    const items = starts.concat(contains).slice(0, 15);
    selIdx = -1;
    if (!items.length) { sug.style.display='none'; return; }
    sug.innerHTML = items.map(([n, c]) =>
      '<div class="sug-item" data-name="'+n+'"><span>'+n+'</span><span class="cnt">'+c+'개 ETF</span></div>'
    ).join('');
    sug.style.display='block';
    sug.querySelectorAll('.sug-item').forEach(el =>
      el.addEventListener('click', () => pick(el.dataset.name)));
  }, 120);
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
  const sh = (fnv1a(name) % 256).toString(16).padStart(2, '0');
  if (!shardCache[sh]) shardCache[sh] = await (await fetch('shard/'+sh+'.json')).json();
  const rows = shardCache[sh][name];
  if (!rows) return;
  curData = { name: name, etfs: rows.map(r => ({
    etfCode: r[0], etfName: r[1], weight: r[2], count: r[3], marketSum: r[4], amount: r[5]
  })) };
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
    '<div><h2>'+d.name+'</h2><span class="sub">'+rows.length+'개 ETF 보유</span></div>',
    '<div class="sortbtns">',
    '<button id="sw" class="'+(sortKey==='weight'?'on':'')+'">비중순</button>',
    '<button id="sa" class="'+(sortKey==='amount'?'on':'')+'">금액순</button>',
    '</div></div>',
    noWeight ? '<div class="notice">해외 종목은 비중(%)이 제공되지 않아 1CU당 보유수량 순으로 표시됩니다.</div>' : '',
    '<table><tr><th>ETF</th><th>비중</th><th class="hide-m">보유수량/1CU</th><th>평가금액(억)</th><th class="hide-m">ETF시총(억)</th></tr>'];
  rows.forEach((r,i)=>{
    const w = r.weight==null ? '<span class="dim">-</span>'
      : '<span class="w">'+r.weight.toFixed(2)+'%</span><span class="bar" style="width:'+Math.round(r.weight/maxW*40)+'px"></span>';
    html.push('<tr>',
      '<td class="name"><span class="rank">'+(i+1)+'</span> <a href="https://finance.naver.com/item/main.naver?code='+r.etfCode+'" target="_blank" rel="noopener">'+r.etfName+'</a></td>',
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

DOC_TMPL = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ — ETF 파인더</title>
<style>__STYLE__</style>
</head>
<body>
<div class="wrap doc">
  <h1><a href="./">ETF 파인더</a></h1>
  <div class="meta">__TITLE__</div>
  __BODY__
  __FOOTER__
</div>
</body>
</html>"""

ABOUT_BODY = """
<h2>ETF 파인더란?</h2>
<p>관심 있는 종목을 검색하면, 그 종목을 담고 있는 <b>모든 국내 상장 ETF</b>를 보유 비중이 높은 순서로 보여주는 서비스입니다.
국내 상장 ETF 전체(1,100개 이상)의 구성종목(PDF)을 매일 전일 종가 기준으로 수집합니다.</p>

<h2>이런 분께 유용합니다</h2>
<ul>
  <li>특정 종목에 투자하고 싶은데 개별주 대신 ETF로 분산 투자하고 싶은 분</li>
  <li>내가 보유한 ETF에 특정 종목이 얼마나 들어있는지 비교하고 싶은 분</li>
  <li>같은 테마의 ETF 중 원하는 종목의 비중이 가장 높은 상품을 고르고 싶은 분</li>
</ul>

<h2>사용법</h2>
<ul>
  <li>검색창에 종목명을 입력하세요 (예: 삼성전자, 한미반도체). 해외 주식은 영문명으로 검색합니다 (예: NVIDIA).</li>
  <li><b>비중순</b>: ETF 자산에서 해당 종목이 차지하는 비율 순 / <b>금액순</b>: 비중 × ETF 시가총액로 추정한 평가금액 순</li>
  <li>해외 종목은 비중(%) 데이터가 제공되지 않아 1CU(설정단위)당 보유수량 순으로 표시됩니다.</li>
</ul>

<h2>유의사항</h2>
<p>본 사이트의 정보는 전일 종가 기준이며, 정보 제공 목적으로만 제공됩니다.
투자 권유가 아니며, 데이터의 정확성을 보장하지 않습니다. 투자 판단과 책임은 이용자 본인에게 있습니다.</p>
"""

PRIVACY_BODY = """
<h2>개인정보처리방침</h2>
<p>ETF 파인더(이하 "사이트")는 이용자의 개인정보를 중요시하며, 관련 법령을 준수합니다.</p>

<h2>1. 수집하는 개인정보</h2>
<p>사이트는 회원가입 없이 이용 가능하며, 이름·이메일 등 개인 식별 정보를 직접 수집하지 않습니다.</p>

<h2>2. 쿠키 및 광고</h2>
<p>사이트는 Google AdSense 등 제3자 광고 서비스를 사용할 수 있습니다.
광고 사업자는 쿠키를 사용하여 이용자의 사이트 방문 기록에 기반한 맞춤형 광고를 제공할 수 있습니다.</p>
<ul>
  <li>Google의 광고 쿠키 사용에 대한 자세한 내용: <a href="https://policies.google.com/technologies/ads?hl=ko" target="_blank" rel="noopener">Google 광고 정책</a></li>
  <li>이용자는 <a href="https://adssettings.google.com" target="_blank" rel="noopener">Google 광고 설정</a>에서 맞춤 광고를 비활성화할 수 있습니다.</li>
</ul>

<h2>3. 접속 기록</h2>
<p>호스팅 제공자(Cloudflare)는 서비스 운영을 위해 IP 주소 등 접속 로그를 자동으로 수집할 수 있습니다.
이는 통계 및 보안 목적으로만 사용됩니다.</p>

<h2>4. 문의</h2>
<p>개인정보 관련 문의는 사이트 운영자에게 연락해 주시기 바랍니다.</p>

<p class="dim">시행일: 2026-06-12</p>
"""


def page(title, body):
    return (DOC_TMPL
            .replace("__TITLE__", title)
            .replace("__STYLE__", STYLE)
            .replace("__BODY__", body)
            .replace("__FOOTER__", FOOTER))


PAGES = {
    "index.html": (INDEX_HTML
                   .replace("__AD_HEAD__", AD_HEAD)
                   .replace("__AD_SLOT__", AD_SLOT)
                   .replace("__STYLE__", STYLE)
                   .replace("__FOOTER__", FOOTER)),
    "about.html": page("사이트 소개", ABOUT_BODY),
    "privacy.html": page("개인정보처리방침", PRIVACY_BODY),
    "robots.txt": "User-agent: *\nAllow: /\n",
    ".nojekyll": "",  # GitHub Pages에서 Jekyll 처리 비활성화
}

if __name__ == "__main__":
    build()
