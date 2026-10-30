#!/usr/bin/env python3
"""全部上市櫃股票的歷史資料（每天盤後 daily.yml 也會跑今年，只補新的交易日）（給網站「任何股票都能查」用），一個市場、一年一次跑：
  python3 tools/univ_hist.py twse 2023     （上市：證交所每日收盤行情 MI_INDEX、個股本益比 BWIBBU_d）
  python3 tools/univ_hist.py tpex 2023     （上櫃：櫃買中心上櫃股票行情 dailyQuotes、本益比 peQryDate）
每天抓一次全市場收盤行情，整理成每月一份：data/u/m/{年-月}.{市場}.json
  rows[代號] = [最高, 最低, 成交金額, 成交股數, 月底收盤, 名稱]   → 月均價＝成交金額 ÷ 成交股數（和證交所「加權平均價」同算法）
  1、4、7、10 月另外存月底那天的本益比、淨值比、殖利率（河流圖的季快照）
  最近兩個月另外存每天的收盤（closes），給近 20 日走勢用
只收 4 位數字代號的普通股（不含 ETF、權證、特別股）。已經完整抓過的月份會跳過，可以重跑。
"""
import datetime, json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from twse import get, col, num, roc_report

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "u" / "m"
OUT.mkdir(parents=True, exist_ok=True)
mkt, year = sys.argv[1], int(sys.argv[2])
tz = datetime.timezone(datetime.timedelta(hours=8))
today = datetime.datetime.now(tz).date()
STOCK = re.compile(r"^[1-9]\d{3}$")
TP = "https://www.tpex.org.tw/www/zh-tw/afterTrading/"


def day_rows(d):
    """一天的全市場行情：{代號: (名稱, 收盤, 最高, 最低, 成交股數, 成交金額)}"""
    out = {}
    if mkt == "twse":
        j = get(f"MI_INDEX?date={d:%Y%m%d}&type=ALLBUT0999&response=json")
        if not (j and j.get("stat") == "OK"):
            return None
        tables = j.get("tables") or [{"fields": j.get(k.replace("data", "fields")), "data": j.get(k)} for k in j if re.fullmatch(r"data\d+", k)]
        t = next((t for t in tables if "證券代號" in (t.get("fields") or []) and col(t.get("fields"), "收盤價") is not None), None)
        if not t:
            return None
        f = t["fields"]; ic, inm, iv, ia, ih, il, icl = col(f, "證券代號"), col(f, "證券名稱"), col(f, "成交股數"), col(f, "成交金額"), col(f, "最高價"), col(f, "最低價"), col(f, "收盤價")
    else:
        j = get(f"{TP}dailyQuotes?date={d:%Y}%2F{d:%m}%2F{d:%d}&type=EW&response=json")
        t = ((j or {}).get("tables") or [{}])[0]
        if not t.get("data") or str((j or {}).get("date")) != f"{d:%Y%m%d}":
            return None
        f = t["fields"]; ic, inm, iv, ia, ih, il, icl = col(f, "代號"), col(f, "名稱"), col(f, "成交股數"), col(f, "成交金額"), col(f, "最高"), col(f, "最低"), col(f, "收盤")
    for r in t["data"]:
        c = str(r[ic]).strip()
        if not STOCK.match(c):
            continue
        cl, h, l, v, a = num(r[icl]), num(r[ih]), num(r[il]), num(r[iv]), num(r[ia])
        if cl and h and l and v and a:
            out[c] = (str(r[inm]).strip(), cl, h, l, v, a)
    return out


def pe_rows(d):
    """月底那天的本益比表：{代號: [本益比, 淨值比, 殖利率, 財報年/季]}"""
    out = {}
    if mkt == "twse":
        j = get(f"BWIBBU_d?date={d:%Y%m%d}&selectType=ALL&response=json")
        if not (j and j.get("stat") == "OK" and j.get("data")):
            return None
        f = j["fields"]; ic, ipe, ipb, iy, ir = col(f, "證券代號"), col(f, "本益比"), col(f, "股價淨值比"), col(f, "殖利率"), col(f, "財報")
        for r in j["data"]:
            c = str(r[ic]).strip()
            if STOCK.match(c):
                out[c] = [num(r[ipe]), num(r[ipb]), num(r[iy]), roc_report(r[ir]) if ir is not None else None]
    else:
        j = get(f"{TP}peQryDate?date={d:%Y}%2F{d:%m}%2F{d:%d}&response=json")
        t = ((j or {}).get("tables") or [{}])[0]
        if not t.get("data"):
            return None
        f = t["fields"]; ic, ipe, ipb, iy = col(f, "股票代號"), col(f, "本益比"), col(f, "股價淨值比"), col(f, "殖利率")
        for r in t["data"]:
            c = str(r[ic]).strip()
            if STOCK.match(c):
                out[c] = [num(r[ipe]), num(r[ipb]), num(r[iy]), None]
    return out


recent_from = (today.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)  # 上個月起存每天收盤
for m in range(1, 13):
    first = datetime.date(year, m, 1)
    if first > today:
        break
    nxt = (first.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    p = OUT / f"{first:%Y-%m}.{mkt}.json"
    if p.exists() and json.loads(p.read_text(encoding="utf-8")).get("complete"):
        print("已完成", p.name, flush=True)
        continue
    rows, days, closes, d = {}, [], {}, first
    if p.exists():  # 這個月抓過一部分（每天盤後更新）：從上次最後一天的隔天接著抓
        o = json.loads(p.read_text(encoding="utf-8"))
        if o.get("days"):
            days = o["days"]
            rows = {c: [x[0], x[1], x[2], x[3], x[4], x[5]] for c, x in o["rows"].items()}
            closes = {c: {dd: v for dd, v in zip(days, arr) if v} for c, arr in (o.get("closes") or {}).items()}
            d = datetime.date.fromisoformat(days[-1]) + datetime.timedelta(days=1)
    n0 = len(days)
    while d < nxt and d <= today:
        if d.weekday() < 5:
            r = day_rows(d)
            if r:
                days.append(f"{d:%Y-%m-%d}")
                for c, (nm, cl, h, l, v, a) in r.items():
                    x = rows.get(c)
                    if x is None:
                        rows[c] = [h, l, a, v, cl, nm]
                    else:
                        x[0] = max(x[0], h); x[1] = min(x[1], l); x[2] += a; x[3] += v; x[4] = cl; x[5] = nm
                    if first >= recent_from:
                        closes.setdefault(c, {})[days[-1]] = cl
        d += datetime.timedelta(days=1)
    if n0 and len(days) == n0 and not nxt <= today:
        print("沒有新的交易日", p.name, flush=True)
        continue
    out = {"ym": f"{first:%Y-%m}", "market": mkt, "days": days, "complete": nxt <= today,
           "rows": {c: [x[0], x[1], round(x[2]), round(x[3]), x[4], x[5]] for c, x in rows.items()}}
    if closes:
        out["closes"] = {c: [v.get(dd) for dd in days] for c, v in closes.items()}
    if days and (m in (1, 4, 7, 10) or not out["complete"]):
        last = datetime.date.fromisoformat(days[-1])
        pe = pe_rows(last)
        if pe is not None:
            if m in (1, 4, 7, 10):
                out["pe"], out["peDate"] = pe, days[-1]
            if not out["complete"]:  # 這個月還沒過完：最新一天的本益比，網站顯示現況用
                out["peNow"], out["peNowDate"] = pe, days[-1]
    p.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(p.name, "交易日", len(days), "股票", len(rows), "本益比", len(out.get("pe", {})), flush=True)
