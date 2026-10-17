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
print("資料日期", inp["date"], "抓到", len(inp["rows"]), "/", len(codes), "缺", sorted(codes - set(inp["rows"])), flush=True)
p = pathlib.Path("/tmp/in.json"); p.write_text(json.dumps(inp, ensure_ascii=False), encoding="utf-8")
subprocess.run([sys.executable, str(ROOT / "tools" / "update_live.py"), "daily", str(p)], check=True)
if os.environ.get("DATE"):
    lv = json.loads((ROOT / "live.json").read_text(encoding="utf-8"))
    print("測試：quotes", len((lv.get("quotes") or {}).get("items", {})), "valuation", len(lv.get("valuation", {})), "events", [e["id"] for e in lv.get("events", []) if e["date"] == inp["date"]])
