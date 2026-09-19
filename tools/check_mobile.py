#!/usr/bin/env python3
"""手机宽度溢出检查：用 Playwright 在 340 / 360 / 390 / 430px 视口打开页面，报告 scrollWidth 与最宽的元素。

用法：
    python3 tools/check_mobile.py notes/xxx/index.html [更多页面...]     # 默认四个宽度
    python3 tools/check_mobile.py --widths 360,390 guides/pc/index.html
    python3 tools/check_mobile.py --all                                  # 全站代表页面

需要：pip install playwright；浏览器用 Claude Code 沙箱预装的 /opt/pw-browsers/chromium-*/chrome-linux/chrome，
本机没有的话去掉 executable_path 让 Playwright 用自己下载的（playwright install chromium）。
退出码：有任何页面在任何宽度溢出则 1。pre 里的代码行超出自己的滚动容器不算溢出。
"""
import argparse, glob, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PAGES = ["index.html", "notes/index.html", "radar/index.html", "radar/events/index.html", "radar/jobs/index.html",
                 "radar/contributions/index.html", "guides/index.html", "guides/pc/index.html", "guides/proxy/index.html",
                 "guides/chatgpt/index.html", "about/index.html", "status/index.html"]
JS = """() => {
  const vw = document.documentElement.clientWidth;
  let worst = null;
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.right <= vw + 1 || r.width === 0) continue;
    // 在自己的滚动容器里的内容不算（pre / table-wrap / diagram-wrap）
    let clipped = false;
    for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      if (getComputedStyle(p).overflowX !== 'visible') { clipped = true; break; }
    }
    if (clipped) continue;
    if (!worst || r.right > worst.right) worst = {right: r.right, desc: el.tagName.toLowerCase() + (typeof el.className === 'string' && el.className ? '.' + el.className.split(' ')[0] : ''), text: (el.textContent || '').trim().slice(0, 40)};
  }
  return {scrollWidth: document.documentElement.scrollWidth, vw, worst};
}"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pages", nargs="*")
    ap.add_argument("--widths", default="340,360,390,430")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--executable", default=next(iter(sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))), None))
    a = ap.parse_args()
    pages = a.pages or (DEFAULT_PAGES + sorted(glob.glob(str(ROOT / "notes/*/index.html"))) if a.all else [])
    if not pages:
        ap.error("给页面路径，或 --all")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("缺 playwright：pip install playwright"); return 2
    widths = [int(w) for w in a.widths.split(",")]
    bad = 0
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=a.executable, args=["--no-sandbox"]) if a.executable else p.chromium.launch(args=["--no-sandbox"])
        for page in pages:
            path = Path(page) if Path(page).is_absolute() else ROOT / page
            for w in widths:
                pg = b.new_page(viewport={"width": w, "height": 900})
                pg.goto(path.as_uri()); pg.wait_for_timeout(150)
                r = pg.evaluate(JS); pg.close()
                ok = r["scrollWidth"] <= w
                bad += 0 if ok else 1
                worst = f"  最宽元素 {r['worst']['desc']} 右边 {r['worst']['right']:.0f} 「{r['worst']['text']}」" if (not ok and r["worst"]) else ""
                print(f"{'✓' if ok else '✗'} {w:3d}px scrollWidth={r['scrollWidth']:4d}  {Path(page).as_posix()}{worst}")
        b.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
