#!/usr/bin/env python3
"""財務資料（證交所 OpenAPI，政府開放資料）：月營收、毛利率／營業利益率、負債比，加上各產業中位數，寫到 fund.json。
用法：python3 tools/fetch_fund.py   （GitHub Actions：.github/workflows/fund.yml，每週六與每月 11 日）
- 月營收：t187ap05_L 上市公司每月營業收入彙總表（含證交所產業別）
- 毛利率、營業利益率：t187ap17_L 營益分析（今年累計到最近一季）
- 負債比：t187ap07_L_* 資產負債表（一般業、金控、銀行、證券、保險、其他）負債總計 ÷ 資產總計
- 本益比、殖利率、淨值比的產業中位數：BWIBBU_ALL
同業中位數＝同一個證交所產業別裡、市值最大的 20 家上市公司（不只本站的股票；不到 20 家就全部）。
市值＝收盤價（STOCK_DAY_ALL）× 已發行普通股數（t187ap03_L）。金融保險業再依資產負債表的格式分成金控、銀行、證券、保險。
毛利率、營業利益率：每家公司記下自己是哪一季的資料；中位數只用和這家公司同一期的同業。
"""
import datetime, json, pathlib, statistics, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
B = "https://openapi.twse.com.tw/v1/"
tz = datetime.timezone(datetime.timedelta(hours=8))


def get(path):
    for i in range(3):
        try:
            req = urllib.request.Request(B + path, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print("retry", path, e, flush=True)
    return []


def num(x):
    try:
        s = str(x).replace(",", "").strip()
        return float(s) if s not in ("", "-", "--") else None
    except ValueError:
        return None


def roc_ym(s):  # 11509 → 2026-09
    s = str(s).strip()
    return f"{int(s[:-2]) + 1911}-{s[-2:]}" if len(s) >= 4 else None


codes = list(json.loads((ROOT / "bands.json").read_text(encoding="utf-8")).keys())
rev = get("opendata/t187ap05_L")
ind = {r["公司代號"]: r.get("產業別") for r in rev}
items, allv = {}, {}
def put(c, k, v):
    if v is None:
        return
    allv.setdefault(c, {})[k] = v
    if c in codes:
        items.setdefault(c, {})[k] = v

rev_ym = None
for r in rev:
    c = r["公司代號"]; rev_ym = rev_ym or roc_ym(r.get("資料年月"))
    put(c, "revYoY", num(r.get("營業收入-去年同月增減(%)")))
    put(c, "revMoM", num(r.get("營業收入-上月比較增減(%)")))
    put(c, "revCumYoY", num(r.get("累計營業收入-前期比較增減(%)")))
    put(c, "rev", num(r.get("營業收入-當月營收")))
    put(c, "revYm", roc_ym(r.get("資料年月")))
period = None
for r in get("opendata/t187ap17_L"):
    c = r["公司代號"]; pr = f"{int(r['年度']) + 1911} 年前 {r['季別']} 季累計"; period = max(period or pr, pr)
    put(c, "gmPeriod", pr)
    put(c, "gm", num(next((v for k, v in r.items() if k.startswith("毛利率")), None)))
    put(c, "om", num(next((v for k, v in r.items() if k.startswith("營業利益率")), None)))
    put(c, "nm", num(next((v for k, v in r.items() if k.startswith("稅後純益率")), None)))
bs_period = None
FIN = {"fh": "金控", "basi": "銀行", "bd": "證券", "ins": "保險"}
fin_kind = {}
for kind in ("ci", "fh", "basi", "bd", "ins", "mim"):
    for r in get(f"opendata/t187ap07_L_{kind}"):
        if kind in FIN:
            fin_kind[r["公司代號"]] = FIN[kind]
        a = num(r.get("資產總計") or r.get("資產總額")); l = num(r.get("負債總計") or r.get("負債總額"))
        if a and l is not None:
            put(r["公司代號"], "debt", round(l / a * 100, 2))
            bs_period = bs_period or f"{int(r['年度']) + 1911} 年第 {r['季別']} 季底"
for r in get("exchangeReport/BWIBBU_ALL"):
    c = r.get("Code")
    put(c, "pe", num(r.get("PEratio")) or None)  # 虧損時是空的，不算
    put(c, "pb", num(r.get("PBratio")))
    put(c, "yield", num(r.get("DividendYield")))
for c, v in list(ind.items()):  # 金融保險業分成金控、銀行、證券、保險
    if v == "金融保險業" and c in fin_kind:
        ind[c] = f"金融保險業（{fin_kind[c]}）"
for c in codes:
    if c in items:
        items[c]["industry"] = ind.get(c)
# 市值：收盤價 × 已發行普通股數，用來挑同業裡的大公司
px = {r.get("Code"): num(r.get("ClosingPrice")) for r in get("exchangeReport/STOCK_DAY_ALL")}
co = get("opendata/t187ap03_L")
skey = next((k for k in (co[0] if co else {}) if "已發行普通股數" in k), None)
cap = {}
for r in co:
    c = r.get("公司代號"); sh = num(r.get(skey)) if skey else None
    if px.get(c) and sh:
        cap[c] = px[c] * sh
for c in codes:
    if c in items and c in cap:
        items[c]["cap"] = round(cap[c] / 1e8, 1)  # 億元
TOP = 20

keys = ["revYoY", "revCumYoY", "gm", "om", "debt", "pe", "pb", "yield"]
med = {}
for name in sorted({ind.get(c) for c in codes if ind.get(c)}):
    allp = [c for c, v in ind.items() if v == name]
    peers = sorted(allp, key=lambda c: -cap.get(c, 0))[:TOP] if cap else allp
    m = {"n": len(peers), "all": len(allp)}
    for k in keys:
        vals = [allv[c][k] for c in peers if c in allv and allv[c].get(k) is not None and (k != "pe" or allv[c][k] > 0)]
        m[k] = round(statistics.median(vals), 2) if len(vals) >= 3 else None
    for k in ("gm", "om"):  # 毛利率、營業利益率依期別分開算
        byp = {}
        for c in peers:
            v = allv.get(c, {})
            if v.get(k) is not None and v.get("gmPeriod"):
                byp.setdefault(v["gmPeriod"], []).append(v[k])
        m[k + "ByPeriod"] = {pr: round(statistics.median(vs), 2) for pr, vs in byp.items() if len(vs) >= 3}
    med[name] = m

out = {"updated": datetime.datetime.now(tz).strftime("%Y-%m-%d %H:%M"), "revYm": rev_ym, "period": period, "bsPeriod": bs_period,
       "source": "臺灣證券交易所 OpenAPI（政府資料開放平臺）：上市公司每月營業收入彙總表、營益分析、資產負債表、個股本益比殖利率及股價淨值比、每日收盤行情、公司基本資料", "peerTop": TOP,
       "items": items, "industry": med}
(ROOT / "fund.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print("items", len(items), "industries", len(med), rev_ym, period, bs_period)
for c in ("2330", "2881", "2412"):
    print(c, items.get(c), med.get((items.get(c) or {}).get("industry")))
