#!/usr/bin/env python3
"""每天收盤後：向證交所抓全市場盤後資料（MI_INDEX、BWIBBU_d），只取網站上的股票，交給 update_live.py daily。
在 GitHub Actions 上跑（.github/workflows/daily.yml）。數字照證交所原樣，抓不到就跳過。"""
import datetime, json, os, re, pathlib, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from twse import get, col, roc_report

ROOT = pathlib.Path(__file__).resolve().parent.parent
codes = set(json.loads((ROOT / "bands.json").read_text(encoding="utf-8")).keys())
tz = datetime.timezone(datetime.timedelta(hours=8))
today = datetime.date.fromisoformat(os.environ["DATE"]) if os.environ.get("DATE") else datetime.datetime.now(tz).date()  # DATE＝測試用
d8 = f"{today:%Y%m%d}"
inp = {"today": f"{today:%Y-%m-%d}", "date": None, "rows": {}}

a = get(f"MI_INDEX?date={d8}&type=ALLBUT0999&response=json")  # 每日收盤行情（全部，不含權證）
t = next((t for t in (a or {}).get("tables", []) if "證券代號" in (t.get("fields") or []) and col(t.get("fields"), "收盤價") is not None), None)
if a and a.get("stat") == "OK" and t and t.get("data"):
    dd = str(a.get("date") or (a.get("params") or {}).get("date") or "")
    inp["date"] = f"{dd[:4]}-{dd[4:6]}-{dd[6:8]}" if len(dd) == 8 else None
    f = t["fields"]
    ic, iv, io, ih, il, icl = col(f, "證券代號"), col(f, "成交股數"), col(f, "開盤價"), col(f, "最高價"), col(f, "最低價"), col(f, "收盤價")
    isg, ich = col(f, "漲跌(+/-)"), col(f, "漲跌價差")
    for r in t["data"]:
        if r[ic] in codes:
            sign = "-" if isg is not None and "-" in re.sub(r"<[^>]*>", "", str(r[isg])) else ""
            inp["rows"][r[ic]] = {"open": r[io], "high": r[ih], "low": r[il], "close": r[icl], "change": sign + str(r[ich]).replace(",", ""), "volume_shares": r[iv]}
    if "TAIEX" in codes:  # 加權指數：在同一份資料的「價格指數」表
        for t2 in a.get("tables", []):
            f2 = t2.get("fields") or []
            i2, c2, s2, p2 = col(f2, "指數"), col(f2, "收盤指數"), col(f2, "漲跌(+/-)"), col(f2, "漲跌點數")
            if None in (i2, c2, p2):
                continue
            for r in t2.get("data") or []:
                if str(r[i2]).strip() == "發行量加權股價指數":
                    sign = "-" if s2 is not None and "-" in re.sub(r"<[^>]*>", "", str(r[s2])) else ""
                    inp["rows"]["TAIEX"] = {"close": r[c2], "change": sign + str(r[p2]).replace(",", "")}
    b = get(f"BWIBBU_d?date={d8}&selectType=ALL&response=json")
    if b and b.get("stat") == "OK" and b.get("data"):
        f = b["fields"]
        ic, ipe, ipb, iy, ir = col(f, "證券代號"), col(f, "本益比"), col(f, "股價淨值比"), col(f, "殖利率"), col(f, "財報")
        for r in b["data"]:
            if r[ic] in inp["rows"]:
                pe = r[ipe]
                inp["rows"][r[ic]].update({"pe": None if str(pe).strip() in ("-", "") else pe, "pb": r[ipb], "yield": r[iy], "report": roc_report(r[ir]) if ir is not None else None})
# 個股比較的漲跌起點：1、3、5 年前那天（遇假日往前找）的收盤價，和加權報酬指數（含息）最近的每日值
def closes_on(day):
    for k in range(8):
        dt = day - datetime.timedelta(days=k)
        if dt.weekday() >= 5:
            continue
        j = get(f"MI_INDEX?date={dt:%Y%m%d}&type=ALLBUT0999&response=json")
        tb = next((t for t in (j or {}).get("tables", []) if "證券代號" in (t.get("fields") or []) and col(t.get("fields"), "收盤價") is not None), None)
        if not (j and j.get("stat") == "OK" and tb and tb.get("data")):
            continue
        f = tb["fields"]; ic, icl = col(f, "證券代號"), col(f, "收盤價")
        out = {r[ic]: str(r[icl]).replace(",", "") for r in tb["data"] if r[ic] in codes}
        for t2 in j.get("tables", []):
            f2 = t2.get("fields") or []; i2, c2 = col(f2, "指數"), col(f2, "收盤指數")
            if None not in (i2, c2):
                for r in t2.get("data") or []:
                    if str(r[i2]).strip() == "發行量加權股價指數":
                        out["TAIEX"] = str(r[c2]).replace(",", "")
        return {"date": f"{dt:%Y-%m-%d}", "closes": out}
    return None


inp["base"] = {}
for yrs in (1, 3, 5):
    try:
        day = today.replace(year=today.year - yrs)
    except ValueError:  # 2/29
        day = today.replace(year=today.year - yrs, day=28)
    b0 = closes_on(day)
    if b0:
        inp["base"][f"{yrs}y"] = b0
inp["tr"] = []
for m0 in sorted({today.replace(day=1), (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)}):
    j = get(f"https://www.twse.com.tw/rwd/zh/TAIEX/MFI94U?date={m0:%Y%m}01&response=json")
    if j and j.get("stat") == "OK" and j.get("data"):
        f = j["fields"]; i0, iv = 0, col(f, "報酬指數", "指數")
        for r in j["data"]:
            y, mm, dd2 = [int(x) for x in str(r[i0]).strip().split("/")]
            inp["tr"].append([f"{y + 1911:04d}-{mm:02d}-{dd2:02d}", str(r[iv]).replace(",", "")])
print("漲跌起點", {k: (v["date"], len(v["closes"])) for k, v in inp["base"].items()}, "報酬指數", inp["tr"][-1:] , flush=True)

x = get("https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL")  # 除權除息預告（休市也抓）
if isinstance(x, list):
    inp["exdiv"] = []
    for r in x:
        c, dt = str(r.get("Code", "")).strip(), str(r.get("Date", "")).strip()
        if c in codes and len(dt) == 7:
            inp["exdiv"].append({"code": c, "name": r.get("Name"), "date": f"{int(dt[:3]) + 1911}-{dt[3:5]}-{dt[5:]}",
                                 "type": r.get("Exdividend"), "cash": r.get("CashDividend") or None,
                                 "stock": r.get("StockDividendRatio") or None})
    print("除權息預告", len(x), "筆，網站股票", len(inp["exdiv"]), flush=True)
print("資料日期", inp["date"], "抓到", len(inp["rows"]), "/", len(codes), "缺", sorted(codes - set(inp["rows"])), flush=True)
p = pathlib.Path("/tmp/in.json"); p.write_text(json.dumps(inp, ensure_ascii=False), encoding="utf-8")
subprocess.run([sys.executable, str(ROOT / "tools" / "update_live.py"), "daily", str(p)], check=True)
if os.environ.get("DATE"):
    lv = json.loads((ROOT / "live.json").read_text(encoding="utf-8"))
    print("測試：quotes", len((lv.get("quotes") or {}).get("items", {})), "valuation", len(lv.get("valuation", {})), "events", [e["id"] for e in lv.get("events", []) if e["date"] == inp["date"]])
