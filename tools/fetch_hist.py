#!/usr/bin/env python3
"""抓新股票五年資料（證交所），格式和網站 data/*.json 一樣，寫到 data/hist/{代號}.json。
用法：python3 tools/fetch_hist.py 2379 3034 ...   （在 GitHub Actions 上跑：.github/workflows/hist.yml）
- monthly：個股月成交資訊 FMSRFK（最高、最低、加權平均價），2021-01 起
- snapshots：每年 1、4、7、10 月最後一個交易日的 BWIBBU_d（本益比、淨值比、殖利率、財報年/季）與收盤價
- recent／latest：個股日成交資訊 STOCK_DAY 最近兩個月
"""
import datetime, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from twse import get, num, roc_date, roc_report, col

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "hist"
OUT.mkdir(parents=True, exist_ok=True)
codes = sys.argv[1:]
tz = datetime.timezone(datetime.timedelta(hours=8))
today = datetime.datetime.now(tz).date()

# 季快照：每季月份最後一個交易日的全市場本益比表（一次涵蓋所有股票）
snap_tables = {}
d = datetime.date(2021, 1, 1)
while d <= today:
    if d.month in (1, 4, 7, 10):
        nxt = (d.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        day = min(nxt - datetime.timedelta(days=1), today)
        for _ in range(12):  # 從月底往前找有資料的交易日
            j = get(f"BWIBBU_d?date={day:%Y%m%d}&selectType=ALL&response=json")
            if j and j.get("stat") == "OK" and j.get("data"):
                f = j["fields"]
                ic, ipe, ipb, iy, ir, ip = col(f, "證券代號"), col(f, "本益比"), col(f, "股價淨值比"), col(f, "殖利率"), col(f, "財報"), col(f, "收盤價")
                snap_tables[d.strftime("%Y-%m")] = {"date": f"{day:%Y-%m-%d}", "rows": {r[ic]: {
                    "close": num(r[ip]) if ip is not None else None, "pe": num(r[ipe]), "pb": num(r[ipb]),
                    "yield": num(r[iy]), "report": roc_report(r[ir]) if ir is not None else None, "name": r[col(f, "證券名稱")]} for r in j["data"]}}
                print("snap", day, len(j["data"]), "fields", f, flush=True)
                break
            day -= datetime.timedelta(days=1)
    d = (d.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)

for code in codes:
    print("==", code, flush=True)
    out = {"code": code, "name": None, "monthly": [], "snapshots": [], "recent": [], "latest": None, "news": [], "failures": [], "notes": []}
    for y in range(2021, today.year + 1):
        j = get(f"FMSRFK?date={y}0101&stockNo={code}&response=json")
        if not (j and j.get("stat") == "OK"):
            out["failures"].append(f"FMSRFK {y}: {j and j.get('stat')}")
            continue
        f = j["fields"]; iy, im, ih, il, ia = col(f, "年度"), col(f, "月份"), col(f, "最高"), col(f, "最低"), col(f, "加權")
        for r in j["data"]:
            h, l, a = num(r[ih]), num(r[il]), num(r[ia])
            if h and l and a:
                out["monthly"].append({"ym": f"{int(r[iy]) + 1911:04d}-{int(r[im]):02d}", "high": h, "low": l, "avg": a})
    rows = []
    m0 = today.replace(day=1)
    for m in ((m0 - datetime.timedelta(days=1)).replace(day=1), m0):
        j = get(f"STOCK_DAY?date={m:%Y%m}01&stockNo={code}&response=json")
        if not (j and j.get("stat") == "OK"):
            out["failures"].append(f"STOCK_DAY {m:%Y-%m}: {j and j.get('stat')}")
            continue
        if not out["name"] and j.get("title"):
            parts = j["title"].split()
            if len(parts) >= 3:
                out["name"] = parts[2]
        f = j["fields"]; i0, io, ih, il, ic, iv = col(f, "日期"), col(f, "開盤"), col(f, "最高"), col(f, "最低"), col(f, "收盤"), col(f, "成交股數")
        for r in j["data"]:
            c = num(r[ic])
            if c:
                rows.append({"date": roc_date(r[i0]), "open": num(r[io]), "high": num(r[ih]), "low": num(r[il]), "close": c, "volume_shares": int(num(r[iv]) or 0)})
    out["recent"] = [{"date": r["date"], "close": r["close"]} for r in rows[-20:]]
    out["latest"] = rows[-1] if rows else None
    for ym, t in sorted(snap_tables.items()):
        r = t["rows"].get(code)
        if not r:
            continue
        out["name"] = out["name"] or r["name"]
        close = r["close"]
        if close is None:  # 舊格式沒有收盤價：用河流圖的月均價以外的資料不可靠，跳過
            out["failures"].append(f"snapshot {t['date']}: 沒有收盤價")
            continue
        if not r["pb"]:
            continue
        out["snapshots"].append({"date": t["date"], "close": close, "pe": r["pe"], "pb": r["pb"], "yield": r["yield"], "report": r["report"]})
    out["notes"].append(f"由 tools/fetch_hist.py 於 {datetime.datetime.now(tz):%Y-%m-%d %H:%M} 從證交所抓取")
    (OUT / f"{code}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(code, out["name"], "monthly", len(out["monthly"]), "snaps", len(out["snapshots"]), "recent", len(out["recent"]), "fail", out["failures"], flush=True)
