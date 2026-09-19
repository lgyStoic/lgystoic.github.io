#!/usr/bin/env python3
"""IndexNow：把当天有变化的页面 URL 推给 Bing（ChatGPT / Perplexity / Kimi 的检索都走 Bing 索引）。

用法：
    python3 tools/indexnow.py            # 提交 sitemap 里 lastmod 为今天（北京时间）的 URL + 首页 + llms.txt
    INDEXNOW_ALL=1 python3 tools/indexnow.py   # 首次接入：提交 sitemap 全部 URL

密钥在 site.json → seo.indexnow_key，根目录同名 <key>.txt 供搜索引擎校验。任何失败只打印，不让工作流失败。
"""
import json, os, re, sys, urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://lgystoic.github.io"


def main() -> int:
    key = ((json.loads((ROOT / "site.json").read_text(encoding="utf-8")).get("seo") or {}).get("indexnow_key") or "").strip()
    if not key or not (ROOT / f"{key}.txt").exists():
        print("[indexnow] 没有密钥或根目录缺少 <key>.txt，跳过"); return 0
    sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    today = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
    urls = []
    for block in re.findall(r"<url>(.*?)</url>", sitemap, re.S):
        loc = re.search(r"<loc>(.*?)</loc>", block); mod = re.search(r"<lastmod>(.*?)</lastmod>", block)
        if loc and (os.environ.get("INDEXNOW_ALL") or (mod and mod.group(1) == today)):
            urls.append(loc.group(1))
    urls = list(dict.fromkeys(urls + [SITE + "/", SITE + "/llms.txt"]))[:10000]
    body = json.dumps({"host": "lgystoic.github.io", "key": key, "keyLocation": f"{SITE}/{key}.txt", "urlList": urls}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"[indexnow] 提交 {len(urls)} 个 URL，HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"[indexnow] HTTP {e.code}：{e.read().decode('utf-8', 'replace')[:200]}")
    except Exception as e:
        print(f"[indexnow] 失败：{e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
