#!/usr/bin/env python3
"""每月 3 日：補上個月的河流圖月資料（FMSRFK 最高、最低、加權平均價），1、4、7、10 月再加季快照（BWIBBU_d），交給 update_live.py monthly。
在 GitHub Actions 上跑（.github/workflows/monthly.yml）。"""
import datetime, json, pathlib, subprocess, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from twse import get, col, num, roc_report

ROOT = pathlib.Path(__file__).resolve().parent.parent
codes = list(json.loads((ROOT / "bands.json").read_text(encoding="utf-8")).keys())
tz = datetime.timezone(datetime.timedelta(hours=8))
first = datetime.datetime.now(tz).date().replace(day=1)
last = first - datetime.timedelta(days=1)          # 上個月最後一天
ym = f"{last:%Y-%m}"
inp = {"ym": ym, "rows": {}}
for c in codes:
    j = get(f"FMSRFK?date={last.year}0101&stockNo={c}&response=json")
    if not (j and j.get("stat") == "OK"):
        print("FMSRFK 失敗", c, j and j.get("stat"), flush=True); continue
    f = j["fields"]; iy, im, ih, il, ia = col(f, "年度"), col(f, "月份"), col(f, "最高"), col(f, "最低"), col(f, "加權")
    for r in j["data"]:
        if int(r[iy]) + 1911 == last.year and int(r[im]) == last.month:
            inp["rows"][c] = {"high": r[ih], "low": r[il], "avg": r[ia]}
if last.month in (1, 4, 7, 10):
    day = last
    for _ in range(12):
        b = get(f"BWIBBU_d?date={day:%Y%m%d}&selectType=ALL&response=json")
        if b and b.get("stat") == "OK" and b.get("data"):
            f = b["fields"]
            ic, ipe, ipb, iy, ir, ip = col(f, "證券代號"), col(f, "本益比"), col(f, "股價淨值比"), col(f, "殖利率"), col(f, "財報"), col(f, "收盤價")
            for r in b["data"]:
                if r[ic] in inp["rows"] and ip is not None and num(r[ip]):
                    pe = r[ipe]
                    inp["rows"][r[ic]]["snap"] = {"date": f"{day:%Y-%m-%d}", "close": r[ip], "pe": None if str(pe).strip() in ("-", "") else pe,
                                                  "pb": r[ipb], "yield": r[iy], "report": roc_report(r[ir]) if ir is not None else None}
            break
        day -= datetime.timedelta(days=1)
print(ym, "月資料", len(inp["rows"]), "/", len(codes), "季快照", sum(1 for r in inp["rows"].values() if "snap" in r), flush=True)
p = pathlib.Path("/tmp/in.json"); p.write_text(json.dumps(inp, ensure_ascii=False), encoding="utf-8")
subprocess.run([sys.executable, str(ROOT / "tools" / "update_live.py"), "monthly", str(p)], check=True)
