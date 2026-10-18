#!/usr/bin/env python3
"""驗證：用證交所個股本益比、淨值比、殖利率（BWIBBU_d）加上發行股數，自己算大盤值，跟證交所月報公布值比。只印結果。
用法：python3 tools/mktpe.py 20260731 20260831 ..."""
import json, sys, time, urllib.request
def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))
def f(x):
    try: return float(str(x).replace(",", ""))
    except: return None
co = get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L")
skey = next(k for k in co[0] if "已發行普通股數" in k)
shares = {r["公司代號"]: f(r[skey]) for r in co}
for d in sys.argv[1:]:
    j = get(f"https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?date={d}&selectType=ALL&response=json")
    fl = j.get("fields", []); rows = j.get("data", [])
    if not rows: print(d, "無資料", j.get("stat")); continue
    ix = {k: i for i, k in enumerate(fl)}
    if d == sys.argv[1]: print("fields", fl)
    cap = capp = earn = book = div = 0.0; n = npos = 0
    for r in rows:
        c = r[ix["證券代號"]]; p = f(r[ix["收盤價"]]); s = shares.get(c)
        if not p or not s: continue
        m = p * s; n += 1; cap += m
        pe, pb, dy = f(r[ix["本益比"]]), f(r[ix["股價淨值比"]]), f(r[ix["殖利率(%)"]])
        if pe and pe > 0: earn += m / pe; capp += m; npos += 1
        if pb and pb > 0: book += m / pb
        if dy is not None: div += m * dy / 100
    print(d, "家數", len(rows), "有股數", n, "有獲利", npos, "市值(百萬)", round(cap / 1e6),
          "PE全部市值/盈餘", round(cap / earn, 2), "PE有獲利", round(capp / earn, 2),
          "PB", round(cap / book, 2), "殖利率%", round(div / cap * 100, 2))
    time.sleep(3)
