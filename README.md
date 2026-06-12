# ETF 파인더

개별 종목을 가장 많이 담은 ETF를 찾는 웹사이트. 국내 상장 ETF 전체(1,137개)의 구성종목(PDF, 전일 기준)을 수집해 종목명으로 역검색한다.

## 사용법

```powershell
cd etf-finder
python collector.py                                      # 데이터 수집 (~30초, 매일 1회)
python -m uvicorn server:app --host 0.0.0.0 --port 8400  # 서버 실행
```

브라우저에서 http://localhost:8400 접속 → 종목명 검색 (예: 삼성전자, 한미반도체, NVIDIA CORP)

## 데이터 소스 (무료, 로그인 불필요)

| 소스 | 용도 | 비고 |
|---|---|---|
| `finance.naver.com/api/sise/etfItemList.nhn` | ETF 전체 목록 + 시세/시총 | |
| `navercomp.wisereport.co.kr/v2/ETF/index.aspx?cmp_cd=` | CU 구성종목 전체 | 페이지 내장 `CU_data` JS 변수 파싱 |
| `m.stock.naver.com/api/stock/{code}/etfAnalysis` | top10 비중 보완 | |

## 제약사항

- **종목코드 없음**: wisereport CU 데이터는 종목명만 제공 → 종목명 키 검색 (동일 벤더라 이름 일관됨)
- **해외 종목 비중(%) 미제공**: 해외 ETF는 `ETF_WEIGHT`가 null → 1CU당 보유수량 순으로 정렬 (CU 규모가 ETF마다 달라 근사치)
- KRX 정보데이터시스템 API는 2025년부터 로그인 필요 (`pykrx` 1.2.8+ 는 `KRX_ID`/`KRX_PW` 환경변수 요구). KRX 계정을 쓰면 해외 비중 포함 공식 풀 PDF로 업그레이드 가능
- ETF CHECK API는 403 (회원 전용)

## 구조

- `collector.py` — 수집기 (8 워커 병렬, ~30초). `data/holdings.json` 생성
- `server.py` — FastAPI + 인라인 HTML (sector-dashboard와 동일 스타일). 파일 변경 시 자동 리로드
- API: `/api/meta`, `/api/suggest?q=`, `/api/stock?name=`
