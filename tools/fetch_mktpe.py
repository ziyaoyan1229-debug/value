#!/usr/bin/env python3
"""大盤本益比、淨值比、殖利率：每月最後一個交易日，用證交所公開資料自己算，寫到 data/hist/mkt-pe.json。
用法：python3 tools/fetch_mktpe.py   （GitHub Actions：.github/workflows/mkt.yml）
算法（市值加權，跟證交所月報同一種口徑）：
  市值 = 收盤價 × 已發行普通股數（公司基本資料 t187ap03_L）
  大盤本益比 = 全部市值 ÷ Σ(市值 ÷ 個股本益比)，個股本益比空白（虧損）的不算盈餘
  大盤淨值比 = 全部市值 ÷ Σ(市值 ÷ 個股淨值比)；殖利率 = Σ(市值 × 個股殖利率) ÷ 全部市值
  隱含每股盈餘（點）= 當天加權指數 ÷ 大盤本益比
個股本益比、淨值比、殖利率：證交所 BWIBBU_d；加權指數：MI_5MINS_HIST。
"""
import datetime, json, pathlib, sys, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from twse import get, num, roc_date, col

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "hist" / "mkt-pe.json"
W = "https://www.twse.com.tw/rwd/zh/"
tz = datetime.timezone(datetime.timedelta(hours=8))
today = datetime.datetime.now(tz).date()

req = urllib.request.Request("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", headers={"User-Agent": "Mozilla/5.0"})
co = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
skey = next(k for k in co[0] if "已發行普通股數" in k)
shares = {r["公司代號"]: num(r[skey]) for r in co}
print("shares", len(shares), skey, flush=True)

def ratios(ymd):
    j = get(f"{W}afterTrading/BWIBBU_d?date={ymd}&selectType=ALL&response=json")
    if not (j and j.get("data")):
        return None
    f = j["fields"]; ic, ip, iy, ie, ib = col(f, "證券代號"), col(f, "收盤價"), col(f, "殖利率"), col(f, "本益比"), col(f, "股價淨值比")
    cap = earn = book = div = 0.0; n = 0
    for r in j["data"]:
        p, s = num(r[ip]), shares.get(str(r[ic]).strip())
        if not p or not s:
            continue
        m = p * s; n += 1; cap += m
        pe, pb, dy = num(r[ie]), num(r[ib]), num(r[iy])
        if pe and pe > 0: earn += m / pe
        if pb and pb > 0: book += m / pb
        if dy is not None: div += m * dy / 100
    return {"n": n, "cap": round(cap / 1e6), "pe": round(cap / earn, 2), "pb": round(cap / book, 2), "yield": round(div / cap * 100, 2)}

rows = []
m = datetime.date(2021, 1, 1)
while m <= today:
    j = get(f"{W}TAIEX/MI_5MINS_HIST?date={m:%Y%m}01&response=json")
    if j and j.get("data"):
        f = j["fields"]; i0, ic = col(f, "日期"), col(f, "收盤")
        last = [r for r in j["data"] if num(r[ic])][-1]
        d = roc_date(last[i0]); x = ratios(d.replace("-", ""))
        if x:
            x.update({"ym": f"{m:%Y-%m}", "date": d, "taiex": num(last[ic]), "eps": round(num(last[ic]) / x["pe"], 2)})
            rows.append(x); print(x, flush=True)
        else:
            print("BWIBBU_d", d, "無資料", flush=True)
    m = (m.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
OUT.write_text(json.dumps({"code": "TAIEX", "method": "市值加權大盤本益比（自算，可對證交所月報）", "monthly": rows,
    "source": "臺灣證券交易所 個股日本益比、殖利率及股價淨值比（BWIBBU_d）、公司基本資料（t187ap03_L）已發行普通股數、發行量加權股價指數（MI_5MINS_HIST）"},
    ensure_ascii=False, indent=1), encoding="utf-8")
print("months", len(rows))
