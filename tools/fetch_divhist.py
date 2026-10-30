#!/usr/bin/env python3
"""含息報酬用的資料，寫到 divhist.json（網頁的個股比較用）：
- 每檔股票、ETF 過去的除權息：證交所「除權除息計算結果表」TWT49U。還原因子＝除權息參考價 ÷ 除權息前收盤價（現金股利、股票股利都算進去）
- 加權指數的含息版本：證交所「發行量加權股價報酬指數」MFI94U，每月平均、最高、最低，加上最近的每日值
用法：python3 tools/fetch_divhist.py   （GitHub Actions：fund.yml，每週六與每月 11 日）
"""
import datetime, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from twse import get, col, num

ROOT = pathlib.Path(__file__).resolve().parent.parent
tz = datetime.timezone(datetime.timedelta(hours=8))
today = datetime.datetime.now(tz).date()
codes = set(json.loads((ROOT / "bands.json").read_text(encoding="utf-8")).keys())
START = 2021


def ad(s):  # 115年07月21日、115/07/21 → 2026-07-21
    y, m, d = [int(x) for x in str(s).strip().replace("年", "/").replace("月", "/").replace("日", "").split("/")]
    return f"{y + 1911:04d}-{m:02d}-{d:02d}"


events = {}
ok_years = []
for y in range(START, today.year + 1):
    end = min(datetime.date(y, 12, 31), today)
    j = get(f"https://www.twse.com.tw/rwd/zh/exRight/TWT49U?startDate={y}0101&endDate={end:%Y%m%d}&response=json")
    if not (j and j.get("stat") == "OK" and j.get("data")):
        print("TWT49U 抓不到", y, (j or {}).get("stat"), flush=True)
        continue
    f = j["fields"]
    i0, ic, ip, ir, iv, it = col(f, "資料日期"), col(f, "股票代號"), col(f, "除權息前收盤價"), col(f, "除權息參考價"), col(f, "權值+息值", "權值"), col(f, "權/息")
    n = 0
    for r in j["data"]:
        c = str(r[ic]).strip()
        if c not in codes:
            continue
        pc, ref = num(r[ip]), num(r[ir])
        if not pc or not ref or ref >= pc:
            continue
        events.setdefault(c, []).append({"date": ad(r[i0]), "f": round(ref / pc, 6), "v": num(r[iv]), "t": str(r[it]).strip() if it is not None else None})
        n += 1
    ok_years.append(y)
    print("TWT49U", y, "全部", len(j["data"]), "本站", n, flush=True)
for c in events:
    events[c] = sorted({e["date"]: e for e in events[c]}.values(), key=lambda e: e["date"])

# 報酬指數：每月一次
tr_m, tr_d = {}, []
d = datetime.date(START, 1, 1)
while d <= today:
    j = get(f"https://www.twse.com.tw/rwd/zh/TAIEX/MFI94U?date={d:%Y%m}01&response=json")
    if j and j.get("stat") == "OK" and j.get("data"):
        f = j["fields"]; i0, iv = 0, col(f, "報酬指數", "指數")
        rows = [(ad(r[i0]), num(r[iv])) for r in j["data"] if num(r[iv])]
        if rows:
            vals = [v for _, v in rows]
            tr_m[f"{d:%Y-%m}"] = {"avg": round(sum(vals) / len(vals), 2), "high": max(vals), "low": min(vals)}
            tr_d += rows
    else:
        print("MFI94U 抓不到", f"{d:%Y-%m}", flush=True)
    d = (d.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)

# 股票分割當月：月資料前後價格混在一起，用每日收盤重算（分割前的價格除以倍數）
SPLITS = {"0050": ("2025-06", 4)}
split = {}
for c, (ym, k) in SPLITS.items():
    j = get(f"STOCK_DAY?date={ym.replace('-', '')}01&stockNo={c}&response=json")
    if j and j.get("stat") == "OK" and j.get("data"):
        f = j["fields"]; ih, il, icl = col(f, "最高價"), col(f, "最低價"), col(f, "收盤價")
        rows = [[num(r[ih]), num(r[il]), num(r[icl])] for r in j["data"] if num(r[icl])]
        cut = next((i for i in range(1, len(rows)) if rows[i][2] < rows[i - 1][2] * 0.5), None)  # 分割後第一天
        if cut:
            adj = [[x / k for x in r] for r in rows[:cut]] + rows[cut:]
            split[c] = {"ym": ym, "high": round(max(r[0] for r in adj), 4), "low": round(min(r[1] for r in adj), 4),
                        "avg": round(sum(r[2] for r in adj) / len(adj), 4), "days": len(adj), "k": k}
    print("分割當月", c, split.get(c), flush=True)

old = {}
p = ROOT / "divhist.json"
if p.exists():
    old = json.loads(p.read_text(encoding="utf-8"))
if not ok_years and old:  # 全部抓不到就保留舊的
    events = old.get("events", {})
if not split and old:
    split = old.get("split", {})
if not tr_m and old:
    tr_m, tr_d = old.get("tr", {}).get("monthly", {}), old.get("tr", {}).get("daily", [])
out = {"updated": datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M"),
       "source": "臺灣證券交易所「除權除息計算結果表」（還原因子＝除權息參考價 ÷ 除權息前收盤價）、「發行量加權股價報酬指數」",
       "events": events, "tr": {"monthly": tr_m, "daily": [list(x) for x in sorted(tr_d)]}, "split": split}
p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("股票", len(events), "事件", sum(len(v) for v in events.values()), "報酬指數月數", len(tr_m))
for c in ("2330", "0050", "0056", "2317"):
    print(c, events.get(c, [])[-3:])
