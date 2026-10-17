#!/usr/bin/env python3
"""每天收盤後：向證交所抓全市場盤後資料（STOCK_DAY_ALL、BWIBBU_d），只取網站上的股票，交給 update_live.py daily。
在 GitHub Actions 上跑（.github/workflows/daily.yml）。數字照證交所原樣，抓不到就跳過。"""
import datetime, json, os, pathlib, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from twse import get, col, roc_report

ROOT = pathlib.Path(__file__).resolve().parent.parent
codes = set(json.loads((ROOT / "bands.json").read_text(encoding="utf-8")).keys())
tz = datetime.timezone(datetime.timedelta(hours=8))
today = datetime.date.fromisoformat(os.environ["DATE"]) if os.environ.get("DATE") else datetime.datetime.now(tz).date()  # DATE＝測試用
d8 = f"{today:%Y%m%d}"
inp = {"today": f"{today:%Y-%m-%d}", "date": None, "rows": {}}

a = get(f"STOCK_DAY_ALL?date={d8}&response=json")
if a and a.get("stat") == "OK" and a.get("data"):
    dd = str(a.get("date") or "")
    inp["date"] = f"{dd[:4]}-{dd[4:6]}-{dd[6:8]}" if len(dd) == 8 else None
    f = a["fields"]
    ic, iv, io, ih, il, icl, ich = col(f, "證券代號"), col(f, "成交股數"), col(f, "開盤"), col(f, "最高"), col(f, "最低"), col(f, "收盤"), col(f, "漲跌")
    for r in a["data"]:
        if r[ic] in codes:
            inp["rows"][r[ic]] = {"open": r[io], "high": r[ih], "low": r[il], "close": r[icl], "change": r[ich], "volume_shares": r[iv]}
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
    print("測試：quotes", len(lv["quotes"]["items"]), "valuation", len(lv.get("valuation", {})), "events", [e["id"] for e in lv.get("events", []) if e["date"] == inp["date"]])
