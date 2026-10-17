#!/usr/bin/env python3
"""ETF 配息與加權指數歷史（證交所），寫到 data/hist/。
用法：python3 tools/fetch_etf.py 0050 0056 ...   （GitHub Actions：.github/workflows/etf.yml）
- data/hist/div-{代號}.json：除權除息計算結果表 TWT49U，2021 起每次除息的日期與息值
- data/hist/TAIEX.json：發行量加權股價指數 MI_5MINS_HIST，2021-01 起每月最高、最低、月平均收盤，及最近 20 個交易日
"""
import datetime, json, pathlib, sys, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from twse import get, num, roc_date, col

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "hist"
OUT.mkdir(parents=True, exist_ok=True)
W = "https://www.twse.com.tw/rwd/zh/"
tz = datetime.timezone(datetime.timedelta(hours=8))
today = datetime.datetime.now(tz).date()
codes = sys.argv[1:]

# 配息：每年一次查全市場的除權息結果，只留要的 ETF
divs = {c: [] for c in codes}
for y in range(2021, today.year + 1):
    j = get(f"{W}exRight/TWT49U?startDate={y}0101&endDate={min(datetime.date(y, 12, 31), today):%Y%m%d}&response=json")
    if not (j and j.get("stat") == "OK" and j.get("data")):
        print("TWT49U", y, j and j.get("stat")); continue
    f = j["fields"]; print("TWT49U", y, len(j["data"]), f, flush=True)
    i0, ic, iv, it = col(f, "資料日期"), col(f, "股票代號"), col(f, "權值+息值", "權值"), col(f, "權/息")
    for r in j["data"]:
        c = str(r[ic]).strip()
        if c in divs and (it is None or "息" in str(r[it])):
            divs[c].append({"date": roc_date(r[i0]) if "/" in str(r[i0]) else str(r[i0]), "cash": num(r[iv]), "type": r[it] if it is not None else None})
for c, v in divs.items():
    (OUT / f"div-{c}.json").write_text(json.dumps({"code": c, "source": "臺灣證券交易所 除權除息計算結果表（TWT49U）", "dividends": v}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("div", c, len(v), v[-3:], flush=True)

# 加權指數：每月一次
monthly, days = [], []
m = datetime.date(2021, 1, 1)
while m <= today:
    j = get(f"{W}TAIEX/MI_5MINS_HIST?date={m:%Y%m}01&response=json")
    if j and j.get("stat") == "OK" and j.get("data"):
        f = j["fields"]; i0, io, ih, il, ic = col(f, "日期"), col(f, "開盤"), col(f, "最高"), col(f, "最低"), col(f, "收盤")
        rows = [{"date": roc_date(r[i0]), "open": num(r[io]), "high": num(r[ih]), "low": num(r[il]), "close": num(r[ic])} for r in j["data"] if num(r[ic])]
        if rows:
            monthly.append({"ym": f"{m:%Y-%m}", "high": max(r["high"] for r in rows), "low": min(r["low"] for r in rows),
                            "avg": round(sum(r["close"] for r in rows) / len(rows), 2)})
            days += rows
    else:
        print("MI_5MINS_HIST", m, j and j.get("stat"))
    m = (m.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
(OUT / "TAIEX.json").write_text(json.dumps({"code": "TAIEX", "name": "加權指數", "monthly": monthly,
    "recent": [{"date": r["date"], "close": r["close"]} for r in days[-20:]], "latest": days[-1] if days else None,
    "source": "臺灣證券交易所 發行量加權股價指數歷史資料（MI_5MINS_HIST）"}, ensure_ascii=False, indent=1), encoding="utf-8")
print("TAIEX months", len(monthly), "latest", days[-1:] if days else None)

# 網頁能不能直接抓（CORS）
for u in [f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={today:%Y%m}01&stockNo=0050",
          f"https://www.twse.com.tw/indicesReport/MI_5MINS_HIST?response=json&date={today:%Y%m}01",
          f"{W}TAIEX/MI_5MINS_HIST?date={today:%Y%m}01&response=json"]:
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Origin": "https://ziyaoyan1229-debug.github.io"})
        with urllib.request.urlopen(req, timeout=30) as r:
            print("CORS", u, r.status, r.headers.get("Access-Control-Allow-Origin"), r.read(120))
    except Exception as e:
        print("CORS", u, e)
