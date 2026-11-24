#!/usr/bin/env python3
"""Render a standalone GitHub Pages report from the run summary."""

from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path
from typing import Any


def safe_url(value: Any) -> str:
    text = str(value or "")
    return text if text.startswith(("https://", "http://")) else ""


def render_item(item: dict[str, Any]) -> str:
    title = html.escape(str(item.get("title") or "未命名资讯"))
    link = safe_url(item.get("link"))
    title_html = (
        f'<a href="{html.escape(link, quote=True)}" target="_blank" rel="noopener noreferrer">{title}</a>'
        if link
        else title
    )
    meta = " · ".join(
        html.escape(str(value))
        for value in (
            item.get("source"),
            item.get("date"),
            item.get("category"),
            item.get("labels"),
        )
        if value
    )
    return f"""
    <article class="item">
      <h2>{title_html}</h2>
      <p class="meta">{meta}</p>
      {f'<p class="source"><a href="{html.escape(link, quote=True)}" target="_blank" rel="noopener noreferrer">查看原文</a></p>' if link else ''}
    </article>
    """


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    items = summary.get("items") or []
    pending = summary.get("pending_items") or []
    webhook_responses = summary.get("feishu_webhook_responses") or []
    node_errors = summary.get("node_errors") or []
    generated_at = html.escape(str(summary.get("generated_at") or ""))

    categories: dict[str, int] = {}
    for item in items:
        category = str(item.get("category") or "未分类")
        categories[category] = categories.get(category, 0) + 1

    category_chips = "".join(
        f'<span class="chip">{html.escape(name)} <b>{count}</b></span>'
        for name, count in sorted(categories.items(), key=lambda pair: (-pair[1], pair[0]))
    )
    cards = "".join(render_item(item) for item in items)
    webhook_status = (
        html.escape(json.dumps(webhook_responses, ensure_ascii=False))
        if webhook_responses
        else "未调用飞书 Webhook"
    )
    errors = (
        "<p class=\"warning\">存在节点警告，请查看 Actions 摘要。</p>"
        if node_errors
        else "<p class=\"ok\">本次没有记录到节点错误。</p>"
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.summary, args.output_dir / "report.json")
    (args.output_dir / ".nojekyll").touch()
    (args.output_dir / "index.html").write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI 全网资讯聚合</title>
  <style>
    :root {{ color-scheme: light; --ink:#17202a; --muted:#667085; --line:#e4e7ec; --accent:#175cd3; --bg:#f6f8fb; --card:#fff; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif; }}
    main {{ width:min(980px,calc(100% - 32px)); margin:36px auto 64px; }}
    header {{ margin-bottom:26px; }}
    h1 {{ margin:0 0 8px; font-size:clamp(28px,5vw,44px); letter-spacing:-.03em; }}
    h2 {{ margin:0 0 6px; font-size:20px; line-height:1.35; }}
    .muted,.meta {{ color:var(--muted); }}
    .summary {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:22px 0; }}
    .summary div {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px; }}
    .summary b {{ display:block; font-size:24px; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:8px; margin:16px 0 22px; }}
    .chip {{ padding:5px 10px; border:1px solid var(--line); border-radius:999px; background:var(--card); font-size:13px; }}
    .item {{ margin:14px 0; padding:20px 22px; background:var(--card); border:1px solid var(--line); border-radius:16px; box-shadow:0 8px 24px rgba(16,24,40,.045); }}
    a {{ color:var(--accent); text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .source {{ margin:0; font-size:14px; }}
    .warning {{ color:#b54708; }}
    .ok {{ color:#067647; }}
    footer {{ color:var(--muted); font-size:13px; margin-top:28px; }}
    @media (max-width:600px) {{ .summary {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>AI 全网资讯聚合</h1>
      <p class="muted">自动生成时间：{generated_at}</p>
    </header>
    <section class="summary">
      <div><b>{len(items)}</b>本次资讯</div>
      <div><b>{len(pending)}</b>待观察</div>
      <div><b>{len(categories)}</b>个分类</div>
    </section>
    <div class="chips">{category_chips}</div>
    <p class="muted">飞书 Webhook：{webhook_status}</p>
    {errors}
    <section>{cards or '<p class="muted">本次没有资讯。</p>'}</section>
    <footer>由 GitHub Actions、n8n 和 DeepSeek 自动生成。</footer>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )
    print(f"Rendered report with {len(items)} items and {len(pending)} pending items.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
