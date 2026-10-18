#!/usr/bin/env python3
"""查證交所公開資料的格式（只印出來，不改檔案）。GitHub Actions：.github/workflows/probe.yml"""
import sys, urllib.request
for u in sys.argv[1:]:
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=40) as r:
            b = r.read()
            print("==", u, r.status, r.headers.get("Content-Type"), len(b))
            print(b[:3000].decode("utf-8", "replace"))
    except Exception as e:
        print("==", u, "ERR", e)
