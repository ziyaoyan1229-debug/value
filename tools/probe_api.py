#!/usr/bin/env python3
"""查證交所 OpenAPI 資料集的欄位（只印出來）。用法：python3 tools/probe_api.py t187ap05_L t187ap17_L ..."""
import json, sys, urllib.request
for name in sys.argv[1:]:
    u = name if name.startswith("http") else "https://openapi.twse.com.tw/v1/opendata/" + name
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            j = json.loads(r.read().decode("utf-8")); h = dict(r.headers)
        print("==", name, len(j), "CORS", h.get("Access-Control-Allow-Origin"))
        rows = [x for x in j if str(x.get("公司代號", x.get("Code", ""))) in ("2330", "2881", "2412")] or j[:2]
        for x in rows[:3]: print(json.dumps(x, ensure_ascii=False))
    except Exception as e:
        print("==", name, "ERR", e)
