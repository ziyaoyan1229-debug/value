#!/usr/bin/env python3
"""驗證：用證交所 OpenAPI 個股資料自己算大盤本益比、淨值比、殖利率，跟證交所月報公布值比。只印結果。"""
import json, urllib.request
def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))
B = "https://openapi.twse.com.tw/v1"
bw = get(B + "/exchangeReport/BWIBBU_ALL")
px = get(B + "/exchangeReport/STOCK_DAY_ALL")
co = get(B + "/opendata/t187ap03_L")
print("BWIBBU_ALL", len(bw), bw[0]); print("STOCK_DAY_ALL", len(px), px[0]); print("t187ap03_L", len(co), {k: co[0][k] for k in list(co[0])[:25]})
def f(x):
    try: return float(str(x).replace(",", ""))
    except: return None
close = {r["Code"]: f(r.get("ClosingPrice")) for r in px}
skey = next(k for k in co[0] if "已發行普通股數" in k)
shares = {r["公司代號"]: f(r[skey]) for r in co}
cap = earn = earn_all = book = div = 0.0; n = npos = 0
for r in bw:
    c = r["Code"]; p = close.get(c); s = shares.get(c)
    if not p or not s: continue
    m = p * s; n += 1; cap += m
    pe, pb, dy = f(r.get("PEratio")), f(r.get("PBratio")), f(r.get("DividendYield"))
    if pe and pe > 0: earn += m / pe; npos += 1
    if pb and pb > 0: book += m / pb
    if dy is not None: div += m * dy / 100
print("date", bw[0].get("Date"), "n", n, "npos", npos, "cap(億)", round(cap / 1e8))
print("PE(只算有獲利)", round(cap / earn, 2))
capp = sum(close[r["Code"]] * shares[r["Code"]] for r in bw if close.get(r["Code"]) and shares.get(r["Code"]) and (f(r.get("PEratio")) or 0) > 0)
print("PE(有獲利的市值/盈餘)", round(capp / earn, 2))
print("PB", round(cap / book, 2), "yield%", round(div / cap * 100, 2))
