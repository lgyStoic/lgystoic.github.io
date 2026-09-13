#!/usr/bin/env python3
"""雷达收件箱：把手动投递到私有仓库 Issue 的链接整理成每日私有摘要。

数据全部留在私有仓库（默认 lgyStoic/radar-inbox），这个公开仓库只放代码。

工作方式：
  1. 手机上分享链接 → iOS 快捷指令 → 往私有仓库的「📥 雷达收件箱」Issue 追加一条评论
     （评论内容：链接 + 可选的一句话备注）。
  2. 每天 Actions 运行本脚本：读取新评论 → 抓取链接的 OG 标题/描述（抓不到就用你的备注）
     → 有 ANTHROPIC_API_KEY / GEMINI_API_KEY 时让模型写一句摘要和标签 → 写入私有仓库：
        digest/<date>.md / .json   当天摘要
        README.md                  最近 30 条索引 + 使用说明
        state.json                 处理进度（Issue 编号、最后处理的评论 id）
     → 给处理过的评论点一个 👍，方便在手机上确认已入库。
  3. 首次运行会自动创建 Issue 和 README。

环境变量：
  INBOX_TOKEN       fine-grained PAT，只授权该私有仓库的 Issues（读写）和 Contents（读写）。没有则直接跳过。
  INBOX_REPO        owner/repo，默认 lgyStoic/radar-inbox
  INBOX_API_BASE    GitHub API 地址，默认 https://api.github.com（测试时指向本地 mock）
  ANTHROPIC_API_KEY / GEMINI_API_KEY 可选，启用 AI 摘要（Claude 优先）
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from radar import call_llm_json, log, strip_html  # noqa: E402

API = os.environ.get("INBOX_API_BASE", "https://api.github.com").rstrip("/")
REPO = os.environ.get("INBOX_REPO", "lgyStoic/radar-inbox")
TOKEN = os.environ.get("INBOX_TOKEN", "").strip()
TZ = ZoneInfo("Asia/Shanghai")

ISSUE_TITLE = "📥 雷达收件箱"
ISSUE_BODY = """在这条 Issue 下面评论即可投递。每条评论：**一个链接 + 可选的一句话备注**，例如：

```
https://www.xiaohongshu.com/explore/xxxx
Kaggle 那个 3D 生成比赛，9 月底截止
```

每天北京时间 08:00 自动整理进 `digest/<日期>.md`，README 里有最近 30 条索引。处理过的评论会被点一个 👍。

> 这里是私有仓库，内容不会出现在公开站点上。
"""

README_HEAD = """# 📥 雷达收件箱（私有）

手动投递的链接每天自动整理。代码在公开仓库 [lgystoic.github.io](https://github.com/lgyStoic/lgystoic.github.io) 的 `tools/inbox.py`。

## 怎么投递

在 [收件箱 Issue](#issue) 下评论：一个链接 + 可选备注。手机上用 iOS 快捷指令一步完成：

1. 快捷指令 → 新建 → 打开「在共享表单中显示」，接受类型选 URL / 文本。
2. 添加动作「获取 URL 内容」：
   - URL：`https://api.github.com/repos/{repo}/issues/{issue}/comments`
   - 方法：POST；请求体：JSON，字段 `body` = 快捷指令输入（可再加一个「要求输入」动作拼上备注）
   - 头部：`Authorization` = `Bearer <你的 fine-grained token>`，`Accept` = `application/vnd.github+json`
3. 在任何 App 里分享 → 选这个快捷指令。

Token 只需要本仓库的 Issues（读写）与 Contents（读写）权限。

"""

UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
URL_RE = re.compile(r"https?://[^\s<>\"'）)】\]]+")


# ---------------------------------------------------------------- GitHub API


def gh(method: str, path: str, body: dict | None = None, *, ok404: bool = False):
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GarryRadarInbox/1.0",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 404 and ok404:
            return None
        detail = e.read().decode("utf-8", "replace")[:300]
        raise SystemExit(f"[inbox] GitHub API {method} {path} → {e.code}: {detail}")


def read_file(path: str) -> tuple[str | None, str | None]:
    data = gh("GET", f"/repos/{REPO}/contents/{path}", ok404=True)
    if not data:
        return None, None
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content, data["sha"]


def write_file(path: str, content: str, message: str, sha: str | None) -> None:
    body = {"message": message, "content": base64.b64encode(content.encode("utf-8")).decode("ascii")}
    if sha:
        body["sha"] = sha
    gh("PUT", f"/repos/{REPO}/contents/{path}", body)


def ensure_issue(state: dict) -> int:
    if state.get("issue_number"):
        return state["issue_number"]
    for issue in gh("GET", f"/repos/{REPO}/issues?state=open&per_page=100") or []:
        if issue.get("title") == ISSUE_TITLE and "pull_request" not in issue:
            state["issue_number"] = issue["number"]
            return issue["number"]
    created = gh("POST", f"/repos/{REPO}/issues", {"title": ISSUE_TITLE, "body": ISSUE_BODY})
    state["issue_number"] = created["number"]
    log(f"[inbox] 已创建收件箱 Issue #{created['number']}")
    return created["number"]


def fetch_comments(issue: int, after_id: int) -> list[dict]:
    out, page = [], 1
    while True:
        batch = gh("GET", f"/repos/{REPO}/issues/{issue}/comments?per_page=100&page={page}") or []
        out.extend(c for c in batch if c["id"] > after_id)
        if len(batch) < 100:
            return out
        page += 1


def react(comment_id: int) -> None:
    try:
        gh("POST", f"/repos/{REPO}/issues/comments/{comment_id}/reactions", {"content": "+1"})
    except SystemExit as e:  # 反应失败不影响主流程
        log(f"[inbox] 点赞失败（忽略）：{e}")


# ---------------------------------------------------------------- 链接元信息


def fetch_og(url: str) -> dict:
    """尽力取 OG 标题/描述。小红书、微信这类对机房 IP 常返回登录墙，取不到就返回空。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA_MOBILE, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read(300_000).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        log(f"[inbox] 取不到页面元信息 {url[:60]}：{e}")
        return {}

    def meta(*names: str) -> str:
        for n in names:
            m = re.search(rf'<meta[^>]+(?:property|name)=["\']{re.escape(n)}["\'][^>]+content=["\']([^"\']*)["\']', html, re.I)
            if not m:
                m = re.search(rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{re.escape(n)}["\']', html, re.I)
            if m and m.group(1).strip():
                return strip_html(m.group(1))
        return ""

    title = meta("og:title", "twitter:title")
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        title = strip_html(m.group(1)) if m else ""
    desc = meta("og:description", "description", "twitter:description")
    if re.search(r"登录|login|验证|环境异常", title, re.I) and not desc:
        return {}
    return {"title": title[:200], "description": desc[:500], "site": meta("og:site_name")}


def site_label(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for key, label in (
        ("xiaohongshu", "小红书"), ("xhslink", "小红书"), ("weixin.qq", "微信"), ("x.com", "X"),
        ("twitter.com", "X"), ("bilibili", "B 站"), ("b23.tv", "B 站"), ("zhihu", "知乎"),
        ("github.com", "GitHub"), ("arxiv.org", "arXiv"), ("huggingface", "Hugging Face"),
        ("kaggle", "Kaggle"), ("tianchi", "天池"), ("modelscope", "ModelScope"),
    ):
        if key in host:
            return label
    return host.removeprefix("www.")


# ---------------------------------------------------------------- Claude

INBOX_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "deadline": {"type": "string"},
                },
                "required": ["id", "title", "summary", "tags", "deadline"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

INBOX_SYSTEM = """你在整理一位工程师手动投递的链接（多来自小红书、微信、X），他关注 AI 比赛/活动、GPU 与生成模型相关内容。

对每条给出：
- title：≤ 30 字的中文标题。有页面标题就精炼它；没有就根据备注和链接推断，推断不出来写「未知链接」。
- summary：≤ 60 字，说清这是什么、和他有什么关系。只能用输入里有的信息，不要编造。
- tags：2-4 个标签，如「比赛」「活动」「截止」「教程」「招聘」。
- deadline：如果备注或描述里出现报名/截止日期，用 YYYY-MM-DD 或原文写法；没有就留空字符串。"""


def enrich(items: list[dict]) -> None:
    payload = [
        {"id": it["comment_id"], "url": it["url"], "site": it["site"], "note": it["note"],
         "page_title": it["og"].get("title", ""), "page_description": it["og"].get("description", "")}
        for it in items
    ]
    data = call_llm_json(INBOX_SYSTEM, "投递条目（JSON）：\n\n" + json.dumps(payload, ensure_ascii=False), INBOX_SCHEMA, label="inbox")
    if not data:
        return
    by_id = {row["id"]: row for row in data.get("items", [])}
    for it in items:
        row = by_id.get(it["comment_id"])
        if row:
            it["title"] = row.get("title") or it["title"]
            it["summary"] = row.get("summary") or it["summary"]
            it["tags"] = (row.get("tags") or it["tags"])[:4]
            it["deadline"] = row.get("deadline", "")
            it["ai"] = True


# ---------------------------------------------------------------- 渲染


def render_day_md(date: str, items: list[dict]) -> str:
    lines = [f"# 收件箱 · {date}", "", f"{len(items)} 条投递。", ""]
    for it in items:
        head = f"## [{it['title']}]({it['url']})"
        meta = f"`{it['site']}` · 投递于 {it['created_at']}"
        if it.get("deadline"):
            meta += f" · ⏰ 截止 {it['deadline']}"
        lines += [head, "", meta, ""]
        if it.get("summary"):
            lines += [it["summary"], ""]
        if it.get("note"):
            lines += [f"> 备注：{it['note']}", ""]
        if it.get("tags"):
            lines += [" ".join(f"`#{t}`" for t in it["tags"]), ""]
    return "\n".join(lines).rstrip() + "\n"


def render_readme(issue: int, recent: list[dict]) -> str:
    head = README_HEAD.format(repo=REPO, issue=issue).replace("(#issue)", f"(https://github.com/{REPO}/issues/{issue})")
    rows = ["## 最近投递", "", "| 日期 | 来源 | 标题 | 备注 |", "|---|---|---|---|"]
    for it in recent:
        note = (it.get("note") or it.get("summary") or "").replace("|", "／").replace("\n", " ")[:80]
        rows.append(f"| [{it['date']}](digest/{it['date']}.md) | {it['site']} | [{it['title'].replace('|', '／')}]({it['url']}) | {note} |")
    if not recent:
        rows.append("| — | — | 还没有投递 | — |")
    return head + "\n".join(rows) + "\n"


# ---------------------------------------------------------------- 主流程


def main() -> None:
    if not TOKEN:
        log("[inbox] 未配置 INBOX_TOKEN，跳过收件箱")
        return

    now = datetime.now(timezone.utc)
    today = now.astimezone(TZ).strftime("%Y-%m-%d")

    state_raw, state_sha = read_file("state.json")
    state = json.loads(state_raw) if state_raw else {"issue_number": None, "last_comment_id": 0, "recent": []}
    issue = ensure_issue(state)

    comments = fetch_comments(issue, int(state.get("last_comment_id") or 0))
    log(f"[inbox] Issue #{issue}：{len(comments)} 条新评论")

    items: list[dict] = []
    for c in comments:
        body = c.get("body") or ""
        urls = URL_RE.findall(body)
        if not urls:
            log(f"[inbox] 评论 {c['id']} 没有链接，跳过")
            continue
        note = URL_RE.sub("", body).strip()
        for url in urls[:3]:
            og = fetch_og(url)
            items.append(
                {
                    "comment_id": c["id"],
                    "created_at": datetime.fromisoformat(c["created_at"].replace("Z", "+00:00")).astimezone(TZ).strftime("%m-%d %H:%M"),
                    "url": url,
                    "site": site_label(url),
                    "note": note,
                    "og": og,
                    "title": og.get("title") or (note.splitlines()[0][:40] if note else "") or site_label(url) + " 链接",
                    "summary": og.get("description", ""),
                    "tags": [],
                    "deadline": "",
                    "ai": False,
                    "date": today,
                }
            )

    if items:
        enrich(items)

        # 当天文件：同一天多次运行合并
        existing_raw, existing_sha = read_file(f"digest/{today}.json")
        day_items = json.loads(existing_raw) if existing_raw else []
        known = {(d["comment_id"], d["url"]) for d in day_items}
        day_items += [dict(it, og=None) for it in items if (it["comment_id"], it["url"]) not in known]
        write_file(f"digest/{today}.json", json.dumps(day_items, ensure_ascii=False, indent=2) + "\n", f"inbox: {today} ({len(day_items)} 条)", existing_sha)
        _, md_sha = read_file(f"digest/{today}.md")
        write_file(f"digest/{today}.md", render_day_md(today, day_items), f"inbox: {today} ({len(day_items)} 条)", md_sha)

        recent = [{"date": it["date"], "site": it["site"], "title": it["title"], "url": it["url"], "note": it["note"], "summary": it["summary"]} for it in items]
        state["recent"] = (recent[::-1] + state.get("recent", []))[:30]
        state["last_comment_id"] = max(c["id"] for c in comments)
        for c in comments:
            react(c["id"])
    elif comments:
        state["last_comment_id"] = max(c["id"] for c in comments)

    # README 与 state 每次都刷新（首次运行也要把说明写出来）
    _, readme_sha = read_file("README.md")
    write_file("README.md", render_readme(issue, state.get("recent", [])), f"inbox: 更新索引 {today}", readme_sha)
    write_file("state.json", json.dumps(state, ensure_ascii=False, indent=2) + "\n", f"inbox: state {today}", state_sha)
    log(f"[inbox] 完成：本次入库 {len(items)} 条，累计索引 {len(state.get('recent', []))} 条")


if __name__ == "__main__":
    main()
