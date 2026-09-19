#!/usr/bin/env python3
"""源探针：在 Actions 里试抓一批 URL，打印状态、类型、条数和前两条标题。加源之前先跑这个，不要凭记忆写 URL。

用法：
  python3 tools/probe.py https://a/feed https://b/api            # 位置参数
  PROBE_URLS=$'https://a/feed\nhttps://b/api' python3 tools/probe.py   # 每行一个（工作流 probe.yml 用这个）
"""
import json, os, sys, urllib.error, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar import USER_AGENT, parse_feed


def probe(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/json, text/html, */*"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            blob, ctype, final = r.read(), r.headers.get("Content-Type", ""), r.geturl()
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}  {e.read()[:120]!r}"
    except Exception as e:
        return f"ERR {e}"
    head = blob[:200].lstrip()
    note = f"{len(blob)}B {ctype.split(';')[0]}" + (f" → {final}" if final != url else "")
    try:
        if head.startswith(b"{") or head.startswith(b"["):
            data = json.loads(blob)
            rows = data if isinstance(data, list) else next((v for v in data.values() if isinstance(v, list)), [])
            keys = sorted(rows[0].keys())[:12] if rows and isinstance(rows[0], dict) else []
            return f"OK json {note} rows={len(rows)} keys={keys}"
        entries = parse_feed(blob)
        if entries:
            return f"OK feed {note} entries={len(entries)} | " + " | ".join(e["title"][:50] for e in entries[:2])
    except Exception as e:
        return f"OK? {note} 解析失败：{e} | {head[:120]!r}"
    return f"OK? {note} 不是 feed/JSON | {head[:160]!r}"


def main():
    urls = [u.strip() for u in (sys.argv[1:] or os.environ.get("PROBE_URLS", "").splitlines()) if u.strip()]
    if not urls:
        raise SystemExit("没有 URL")
    for u in urls:
        print(f"{u}\n    {probe(u)}", flush=True)


if __name__ == "__main__":
    main()
