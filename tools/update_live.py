"""把排程抓到的證交所盤後資料併進 live.json（網頁讀這個檔）。

用法：
  python3 tools/update_live.py daily  input.json
    input = {"today":"YYYY-MM-DD","date":"YYYY-MM-DD" 或 null,
             "rows":{"2330":{"open","high","low","close","change","volume_shares","pe","pb","yield","report"}, ...}}
    date 是證交所資料的交易日；null 或不是 today 代表今天休市。
  python3 tools/update_live.py monthly input.json
    input = {"ym":"YYYY-MM","rows":{"2330":{"high","low","avg","snap":{"date","close","pe","pb","yield","report"}}, ...}}
    snap 只在 01、04、07、10 月加進 snapshots。
"""
import json, sys, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIVE = ROOT / "live.json"
BANDS = ROOT / "bands.json"  # 網站建置時寫入的五年評價區間（p25／p75 倍數）
# 要更新的股票＝網站上有五年資料的那些（bands.json 的鍵）
CODES = list(json.loads(BANDS.read_text(encoding="utf-8")).keys()) if BANDS.exists() else []


def num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return x
    s = str(x).replace(",", "").strip()
    if s in ("", "-", "--", "0", "0.00"):
        return None
    return float(s)


def chg(x):  # 漲跌價差可以是 0
    try:
        return float(str(x).replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return None


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")


def by_month(items, key, new):
    m = {x[key][:7]: x for x in items if x.get(key)}
    m[new[key][:7]] = new
    return [m[k] for k in sorted(m)]


def by_date(items, new):
    m = {x["date"]: x for x in items if x.get("date")}
    m[new["date"]] = new
    return [m[k] for k in sorted(m)]


def exdiv(live, new, today):
    """除權息行事曆：證交所預告（TWT48U）。已過的日子留 30 天，讓剛除息的也看得到。"""
    keep = (datetime.date.fromisoformat(today) - datetime.timedelta(days=30)).isoformat()
    old = [x for x in (live.get("exdiv") or {}).get("items", []) if keep <= x["date"] < today]
    seen = {(x["code"], x["date"]) for x in new}
    items = [x for x in old if (x["code"], x["date"]) not in seen] + new
    for x in items:
        for k in ("cash", "stock"):
            x[k] = num(x.get(k)) or None
    live["exdiv"] = {"updatedAt": now(), "source": "臺灣證券交易所 除權除息預告表（TWT48U）",
                     "items": sorted(items, key=lambda x: (x["date"], x["code"]))}


def daily(live, inp):
    today, date = inp["today"], inp.get("date")
    early = date != today and datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).hour < 14
    if not early:  # 收盤前手動跑、還沒資料，不要把今天標成休市
        live["market"] = {"date": today, "open": bool(date) and date == today}
    if inp.get("exdiv") is not None:
        exdiv(live, inp["exdiv"], today)
    if not date or date != today:
        return "休市或證交所還沒有今天的資料，只更新開盤狀態"
    q = live.get("quotes") or {}
    items = q.get("items") or {}
    val = live.setdefault("valuation", {})
    done = []
    for code in CODES:
        r = inp["rows"].get(code)
        close = num(r.get("close")) if r else None
        if not close:
            continue
        old = items.get(code) or {}
        rec = [x for x in old.get("recent", []) if x["date"] != date] + [{"date": date, "close": close}]
        vol = num(r.get("volume_shares"))
        items[code] = {"date": date, "time": "收盤", "price": close, "open": num(r.get("open")),
                       "high": num(r.get("high")), "low": num(r.get("low")),
                       "volumeLots": round(vol / 1000) if vol else None,
                       "change": chg(r.get("change")),
                       "recent": sorted(rec, key=lambda x: x["date"])[-20:]}
        pb = num(r.get("pb"))
        if pb:
            v = val.setdefault(code, {"monthly": [], "snapshots": []})
            v["current"] = {"date": date, "close": close, "pe": num(r.get("pe")), "pb": pb,
                            "yield": num(r.get("yield")), "report": r.get("report")}
        done.append(code)
    if done:
        ts = now()
        live["quotes"] = {"updatedAt": ts, "source": "臺灣證券交易所 每日收盤行情、個股本益比／淨值比（盤後）", "items": items}
        live["updatedAt"] = ts
    if done:
        events(live, inp, date, done)
    missing = [c for c in CODES if c not in done]
    return f"{date} 更新 {len(done)} 檔" + (f"，缺 {','.join(missing)}" if missing else "")


MN = {"pe": "本益比", "pb": "淨值比", "pd": "本利比"}


def events(live, inp, date, codes):
    """比對前一次的評價區，產生要推播的通知（推播由 GitHub Actions 的 notify 送出）。"""
    bands = json.loads(BANDS.read_text(encoding="utf-8")) if BANDS.exists() else {}
    zones, out = live.setdefault("zones", {}), []
    for code in codes:
        b, r, it = bands.get(code), inp["rows"][code], live["quotes"]["items"][code]
        if not b:
            continue
        name, price = b["name"], it["price"]
        if not b.get("method"):  # 加權指數：沒有評價區
            mult = None
        elif b["method"] == "pd" or code == "TAIEX":  # ETF：本利比＝收盤 ÷ 近 12 個月配息；指數：點數 ÷ 隱含每股盈餘
            mult = round(price / b["base"], 2) if b.get("base") else None
        else:
            mult = num(r.get(b["method"]))
        zone = None if mult is None else ("低估" if mult < b["p25"] else "高估" if mult > b["p75"] else "合理")
        prev = zones.get(code, {}).get("zone") or b.get("zone")
        def add(kind, title, body):
            out.append({"id": f"{code}-{kind}-{date}", "date": date, "code": code, "kind": kind,
                        "title": f"{name} {code}　{title}", "body": body, "url": f"./#s{code}"})
        if zone and zone != prev and zone == "低估":
            add("buy", "進入參考買進區", f"收盤 {price:g}，{MN[b['method']]} {mult:g} 倍，低於五年區間的下四分之一。")
        if zone and zone != prev and zone == "高估":
            add("over", "進入高估區", f"收盤 {price:g}，{MN[b['method']]} {mult:g} 倍，高於五年區間的上四分之一。")
        chg = it.get("change")
        if chg is not None and price - chg > 0:
            pct = chg / (price - chg) * 100
            if abs(pct) >= 9.5:
                add("limit" if pct > 0 else "limitdn", "收盤漲停" if pct > 0 else "收盤跌停", f"收盤 {price:g}，{'+' if pct > 0 else ''}{pct:.2f}%。")
            elif abs(pct) >= 5:
                add("move", "單日大漲" if pct > 0 else "單日大跌", f"收盤 {price:g}，{'+' if pct > 0 else ''}{pct:.2f}%。")
        if zone:
            zones[code] = {"zone": zone, "date": date}
    old = [e for e in live.get("events", []) if e["id"] not in {x["id"] for x in out}]
    live["events"] = (out + old)[:60]


def monthly(live, inp):
    ym = inp["ym"]
    val = live.setdefault("valuation", {})
    done = []
    for code, r in inp["rows"].items():
        if code not in CODES:
            continue
        v = val.setdefault(code, {"monthly": [], "snapshots": []})
        h, l, a = num(r.get("high")), num(r.get("low")), num(r.get("avg"))
        if h and l and a:
            row = {"ym": ym, "high": h, "low": l, "avg": a}
            if r.get("source"):
                row["source"] = r["source"]
            v["monthly"] = by_month(v.get("monthly", []), "ym", row)
        for d in r.get("divs") or []:  # ETF 除息
            v["dividends"] = by_date(v.get("dividends", []), d)
        if r.get("mkt"):  # 加權指數的大盤本益比
            v["mkt"] = by_month(v.get("mkt", []), "ym", r["mkt"])
        s = r.get("snap")
        if s and num(s.get("close")) and num(s.get("pb")) and ym[5:] in ("01", "04", "07", "10"):
            snap = {"date": s["date"], "close": num(s["close"]), "pe": num(s.get("pe")), "pb": num(s["pb"]),
                    "yield": num(s.get("yield")), "report": s.get("report")}
            v["snapshots"] = by_month(v.get("snapshots", []), "date", snap)
        done.append(code)
    live["updatedAt"] = now()
    return f"{ym} 月資料更新 {len(done)} 檔"


if __name__ == "__main__":
    mode, path = sys.argv[1], sys.argv[2]
    live = json.loads(LIVE.read_text(encoding="utf-8")) if LIVE.exists() else {}
    inp = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    msg = daily(live, inp) if mode == "daily" else monthly(live, inp)
    LIVE.write_text(json.dumps(live, ensure_ascii=False, indent=1), encoding="utf-8")
    print(msg)
