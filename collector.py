# -*- coding: utf-8 -*-
"""ETF 구성종목(PDF) 수집기

소스:
  1. 네이버 ETF 전체 목록  : finance.naver.com/api/sise/etfItemList.nhn (시세/시총 포함)
  2. wisereport CU 구성종목 : navercomp.wisereport.co.kr/v2/ETF/index.aspx?cmp_cd= (페이지 내장 CU_data)
  3. 네이버 top10 비중 보완 : m.stock.naver.com/api/stock/{code}/etfAnalysis (해외ETF 비중 None 보완)

출력: data/holdings.json
사용: python collector.py
"""
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126"}
DATA_DIR = Path(__file__).parent / "data"
WORKERS = 8

CASH_NAMES = {"원화현금", "달러현금", "외화현금", "원화 현금", "설정현금액", "USD현금"}


def fetch_etf_list():
    r = requests.get("https://finance.naver.com/api/sise/etfItemList.nhn", headers=UA, timeout=15)
    items = r.json()["result"]["etfItemList"]
    return [
        {
            "code": it["itemcode"],
            "name": it["itemname"],
            "price": it.get("nowVal"),
            "nav": it.get("nav"),
            "marketSum": it.get("marketSum"),  # 억원
        }
        for it in items
    ]


def fetch_cu(session, code):
    """wisereport 페이지에서 CU_data.grid_data 추출"""
    r = session.get(
        f"https://navercomp.wisereport.co.kr/v2/ETF/index.aspx?cmp_cd={code}",
        headers=UA, timeout=15,
    )
    ct = r.headers.get("Content-Type", "").lower()
    r.encoding = "utf-8" if "utf-8" in ct else r.apparent_encoding
    m = re.search(r"var CU_data = (\{.*?\});", r.text, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    rows = data.get("grid_data") or []
    out = []
    for row in rows:
        nm = (row.get("STK_NM_KOR") or "").strip()
        if not nm or nm in CASH_NAMES or "현금" in nm:
            continue
        out.append({
            "name": nm,
            "count": row.get("AGMT_STK_CNT"),
            "weight": row.get("ETF_WEIGHT"),
            "date": row.get("TRD_DT"),
        })
    return out


def fetch_top10(session, code):
    """네이버 모바일 API: top10 비중(해외ETF 비중 보완용) + top10 종목코드"""
    try:
        r = session.get(
            f"https://m.stock.naver.com/api/stock/{code}/etfAnalysis",
            headers=UA, timeout=15,
        )
        d = r.json()
        out = {}
        for it in d.get("etfTop10MajorConstituentAssets") or []:
            nm = (it.get("itemName") or "").strip()
            w = (it.get("etfWeight") or "").replace("%", "").replace(",", "")
            try:
                out[nm] = {"weight": float(w), "itemCode": it.get("itemCode")}
            except ValueError:
                continue
        return out
    except Exception:
        return {}


def collect_one(session, etf):
    code = etf["code"]
    holdings = fetch_cu(session, code)
    if holdings is None:
        return code, None
    # 비중 None 이 있으면 top10 으로 보완
    if any(h["weight"] is None for h in holdings):
        top10 = fetch_top10(session, code)
        for h in holdings:
            t = top10.get(h["name"])
            if t and h["weight"] is None:
                h["weight"] = t["weight"]
    return code, holdings


def main():
    t0 = time.time()
    etfs = fetch_etf_list()
    print(f"ETF list: {len(etfs)}")

    results = {}
    failed = []

    def worker(etf):
        s = requests.Session()
        try:
            return collect_one(s, etf)
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(worker, e): e for e in etfs}
        done = 0
        for fut in as_completed(futures):
            etf = futures[fut]
            try:
                code, holdings = fut.result()
            except Exception as exc:
                failed.append(etf["code"])
                code, holdings = etf["code"], None
                print(f"  ! {etf['code']} {etf['name']}: {exc}")
            if holdings is not None:
                results[code] = holdings
            else:
                failed.append(code)
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(etfs)} ({time.time()-t0:.0f}s)")

    # 기준일: 가장 흔한 날짜
    from collections import Counter
    dates = Counter(h["date"] for hs in results.values() for h in hs if h.get("date"))
    base_date = dates.most_common(1)[0][0] if dates else None

    DATA_DIR.mkdir(exist_ok=True)
    out = {
        "baseDate": base_date,
        "collectedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "etfs": {e["code"]: e for e in etfs},
        "holdings": results,
        "failed": sorted(set(failed)),
    }
    path = DATA_DIR / "holdings.json"
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    n_rows = sum(len(v) for v in results.values())
    print(f"\nDONE in {time.time()-t0:.0f}s")
    print(f"  ETFs with holdings: {len(results)}/{len(etfs)} (failed: {len(set(failed))})")
    print(f"  total holding rows: {n_rows}")
    print(f"  base date: {base_date}")
    print(f"  saved: {path}")


if __name__ == "__main__":
    main()
