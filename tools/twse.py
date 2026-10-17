"""證交所公開資料（在 GitHub Actions 上可以直接抓）：慢慢抓、遇到擋頁會重試。"""
import json, time, urllib.request

BASE = "https://www.twse.com.tw/rwd/zh/afterTrading/"
_last = [0.0]


def get(path, retries=4, gap=2.2):
    url = path if path.startswith("http") else BASE + path
    for i in range(retries):
        wait = gap - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (value-taiwan-stock)", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8", "replace")
            j = json.loads(body)
            return j
        except Exception as e:  # 擋頁（HTML）或連線問題：等久一點再試
            print(f"  retry {i + 1} {url}: {str(e)[:80]}", flush=True)
            time.sleep(10 * (i + 1))
    return None


def num(x):
    if x is None:
        return None
    s = str(x).replace(",", "").strip()
    if s in ("", "-", "--", "---", "X0.00"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def roc_date(s):  # 115/10/16 → 2026-10-16
    y, m, d = str(s).strip().split("/")
    return f"{int(y) + 1911:04d}-{int(m):02d}-{int(d):02d}"


def roc_report(s):  # 115/2 → 2026/2
    s = str(s or "").strip()
    if "/" not in s:
        return s or None
    y, q = s.split("/")
    try:
        return f"{int(y) + 1911}/{int(q)}"
    except ValueError:
        return s


def col(fields, *names):
    for n in names:
        for i, f in enumerate(fields or []):
            if n in f:
                return i
    return None
