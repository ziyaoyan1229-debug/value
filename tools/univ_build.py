#!/usr/bin/env python3
"""從 data/u/m/ 的月資料整理出每一檔股票的河流圖資料（給網站「任何股票都能查」用）。
  python3 tools/univ_build.py          → data/u/s/{代號}.json（每檔一份，算法和網站內建的 49 檔相同）＋ data/u/all.json、data/u/recent.json
  python3 tools/univ_build.py --index  → 只更新 data/u/all.json（名稱、市場、產業、最新收盤、本益比）和 data/u/recent.json（近 20 日收盤）
網站內建的股票（bands.json）不在這裡重做。
"""
import datetime, json, pathlib, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
U = ROOT / "data" / "u"
M, S = U / "m", U / "s"
S.mkdir(parents=True, exist_ok=True)
tz = datetime.timezone(datetime.timedelta(hours=8))
today = datetime.datetime.now(tz).date()
ONLY_INDEX = "--index" in sys.argv
CURATED = set(json.loads((ROOT / "bands.json").read_text(encoding="utf-8")).keys())
MKT = {"twse": "上市", "tpex": "上櫃"}
# 證交所、櫃買中心共用的產業代碼
IND = {"01": "水泥工業", "02": "食品工業", "03": "塑膠工業", "04": "紡織纖維", "05": "電機機械", "06": "電器電纜", "08": "玻璃陶瓷",
       "09": "造紙工業", "10": "鋼鐵工業", "11": "橡膠工業", "12": "汽車工業", "14": "建材營造業", "15": "航運業", "16": "觀光餐旅",
       "17": "金融保險業", "18": "貿易百貨業", "19": "綜合", "20": "其他業", "21": "化學工業", "22": "生技醫療業", "23": "油電燃氣業",
       "24": "半導體業", "25": "電腦及週邊設備業", "26": "光電業", "27": "通信網路業", "28": "電子零組件業", "29": "電子通路業",
       "30": "資訊服務業", "31": "其他電子業", "32": "文化創意業", "33": "農業科技業", "34": "電子商務", "35": "綠能環保",
       "36": "數位雲端", "37": "運動休閒", "38": "居家生活", "80": "管理股票"}


def get(url):
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print("retry", url, e, flush=True)
    return []


def industries():
    out = {}
    for r in get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L"):
        c, k = r.get("公司代號"), str(r.get("產業別") or "").strip()
        if c:
            out[c] = IND.get(k.zfill(2), k or None)
    for r in get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"):
        c, k = r.get("SecuritiesCompanyCode"), str(r.get("SecuritiesIndustryCode") or "").strip()
        if c:
            out[c] = IND.get(k.zfill(2), k or None)
    return out


def pct(vals, q):
    v = sorted(vals)
    k = (len(v) - 1) * q
    f = int(k); c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


files = sorted(M.glob("*.json"))
months = [json.loads(p.read_text(encoding="utf-8")) for p in files]
by = {}  # 代號 → {"mkt", "name", "monthly": {ym: [...]}, "snaps": [...]}
for mo in months:
    for c, (h, l, a, v, cl, nm) in mo["rows"].items():
        x = by.setdefault(c, {"mkt": mo["market"], "name": nm, "monthly": {}, "snaps": [], "last": None})
        x["monthly"][mo["ym"]] = {"ym": mo["ym"], "high": h, "low": l, "avg": round(a / v, 2) if v else None, "close": cl}
        if x["last"] is None or mo["ym"] >= x["last"]:
            x["last"], x["name"], x["mkt"] = mo["ym"], nm, mo["market"]
        pe = (mo.get("pe") or {}).get(c)
        if pe and pe[1]:
            x["snaps"].append({"date": mo["peDate"], "close": cl, "pe": pe[0], "pb": pe[1], "yield": pe[2], "report": pe[3]})
# 近 20 日收盤：最近兩個月的每日收盤
recent = {}
for mo in sorted(months, key=lambda m: m["ym"])[-4:]:
    for c, arr in (mo.get("closes") or {}).items():
        for d, v in zip(mo["days"], arr):
            if v:
                recent.setdefault(c, {})[d] = v
latest_ym = max(m["ym"] for m in months)
now_pe = {}
for mo in months:
    if mo["ym"] == latest_ym:
        for c, v in (mo.get("peNow") or {}).items():
            now_pe[c] = (mo.get("peNowDate"), v)
ind = industries()

alli, rec_out, built = {}, {"days": None, "items": {}}, 0
for c, x in sorted(by.items()):
    if x["last"] < (today.replace(day=1) - datetime.timedelta(days=40)).strftime("%Y-%m"):
        continue  # 已經下市或停止交易
    rc = sorted(recent.get(c, {}).items())[-20:]
    close = rc[-1][1] if rc else None
    prev = rc[-2][1] if len(rc) > 1 else None
    pe = now_pe.get(c, (None, [None, None, None, None]))
    industry = ind.get(c)
    alli[c] = [x["name"], MKT[x["mkt"]], industry, close, round(close - prev, 2) if close and prev else None,
               pe[1][0], pe[1][1], pe[1][2], rc[-1][0] if rc else None]
    rec_out["items"][c] = [[d, v] for d, v in rc]
    if ONLY_INDEX or c in CURATED:
        continue
    monthly = [m for m in sorted(x["monthly"].values(), key=lambda m: m["ym"]) if m["avg"]][-70:]
    snaps = sorted(x["snaps"], key=lambda s: s["date"])
    fin = industry == "金融保險業"
    method = "pb" if fin or any(s.get("pe") is None for s in snaps) else "pe"
    out = {"code": c, "name": x["name"], "sector": f"{industry or '產業無資料'}（{MKT[x['mkt']]}）", "method": method, "univ": True,
           "market": MKT[x["mkt"]], "industry": industry, "failures": [], "news": [],
           "recent": [{"date": d, "close": v} for d, v in rc], "monthly": [{k: m[k] for k in ("ym", "high", "low", "avg")} for m in monthly],
           "snapshots": snaps, "latest": {"date": rc[-1][0], "close": close} if rc else None}
    for key, bk in (("pe", "eps"), ("pb", "bvps")):
        pts = [(s["date"], s["close"] / s[key], s[key]) for s in snaps if s.get(key)]
        if len(pts) < 4:
            out[key] = None
            continue
        mults = [p[2] for p in pts]
        q = {"min": min(mults), "p25": pct(mults, .25), "p50": pct(mults, .5), "p75": pct(mults, .75), "max": max(mults)}
        series = []
        for m in monthly:
            basis = None
            for p in pts:
                if p[0] <= m["ym"] + "-31":
                    basis = p[1]
            series.append({"ym": m["ym"], "base": round(basis if basis is not None else pts[0][1], 4)})
        cur = pts[-1]
        out[key] = {"quantiles": {k: round(v, 2) for k, v in q.items()}, "series": series, "n": len(pts),
                    "current": {"date": cur[0], "multiple": cur[2], bk: round(cur[1], 4)}}
    m = out.get(method)
    last = snaps[-1] if snaps else None
    if m and close:
        qq, b = m["quantiles"], m["current"]["eps" if method == "pe" else "bvps"]
        cm = close / b
        out["verdict"] = {"zone": "低估" if cm < qq["p25"] else ("高估" if cm > qq["p75"] else "合理"), "price": close, "priceDate": rc[-1][0],
                          "multiple": round(cm, 2), "base": b, "buyBelow": round(b * qq["p25"], 1), "fair": round(b * qq["p50"], 1),
                          "sellAbove": round(b * qq["p75"], 1), "floor": round(b * qq["min"], 1), "ceiling": round(b * qq["max"], 1),
                          "rank": round(sum(1 for s in snaps if s.get(method) and s[method] < cm) / max(1, m["n"]) * 100)}
    else:
        out["verdict"] = {"zone": None, "price": close, "priceDate": rc[-1][0]} if close else None
        out["method"] = None if not m else method
    out["yield"] = last.get("yield") if last else None
    out["report"] = last.get("report") if last else None
    (S / f"{c}.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    built += 1

src = "臺灣證券交易所（每日收盤行情、個股本益比、公司基本資料）、證券櫃檯買賣中心（上櫃股票行情、本益比、公司基本資料）"
(U / "all.json").write_text(json.dumps({"updated": datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M"), "source": src,
                                        "fields": ["名稱", "市場", "產業", "收盤", "漲跌", "本益比", "淨值比", "殖利率", "日期"],
                                        "items": alli}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
(U / "recent.json").write_text(json.dumps({"updated": datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M"), "items": rec_out["items"]},
                                          ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
# 每日收盤只留最近兩個月，舊月份拿掉省空間
keep = (today.replace(day=1) - datetime.timedelta(days=40)).strftime("%Y-%m")
for p, mo in zip(files, months):
    if mo.get("closes") and mo["ym"] < keep and mo.get("complete"):
        mo.pop("closes")
        p.write_text(json.dumps(mo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("全部", len(alli), "重做河流圖", built, "最新月份", latest_ym, flush=True)
