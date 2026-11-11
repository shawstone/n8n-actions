#!/usr/bin/env python3
"""Extract the final RSS dry-run items and render a small HTML preview."""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FINAL_NODE = "分类排序"


def find_run_data(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        candidate = value.get("runData")
        if isinstance(candidate, dict):
            return candidate
        for child in value.values():
            found = find_run_data(child)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_run_data(child)
            if found is not None:
                return found
    return None


def load_execution_json(path: Path) -> Any:
    raw = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(raw[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and find_run_data(value) is not None:
            return value
    raise ValueError("No n8n execution JSON containing runData was found")


def node_items(run_data: dict[str, Any], node_name: str) -> list[Any]:
    runs = run_data.get(node_name)
    if not isinstance(runs, list):
        return []

    items: list[Any] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        branches = (run.get("data") or {}).get("main") or []
        for branch in branches:
            for item in branch or []:
                if isinstance(item, dict) and "json" in item:
                    items.append(item["json"])
                else:
                    items.append(item)
    return items


def first_value(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def normalize_item(item: Any) -> dict[str, str]:
    if not isinstance(item, dict):
        return {
            "title": "未命名结果",
            "summary": str(item),
            "category": "",
            "source": "",
            "date": "",
            "link": "",
        }

    return {
        "title": first_value(item, "标题", "title") or "未命名结果",
        "summary": first_value(item, "内容", "摘要", "summary", "text"),
        "category": first_value(item, "分类", "category"),
        "source": first_value(item, "来源", "source"),
        "date": first_value(item, "日期", "date", "published"),
        "link": first_value(item, "链接", "url", "link"),
    }


def render_html(items: list[dict[str, str]]) -> str:
    cards: list[str] = []
    for item in items:
        link = item["link"]
        title = html.escape(item["title"])
        if link.startswith(("http://", "https://")):
            safe_link = html.escape(link, quote=True)
            title_html = f'<a href="{safe_link}" target="_blank" rel="noopener noreferrer">{title}</a>'
            source_html = f'<a href="{safe_link}" target="_blank" rel="noopener noreferrer">查看原文</a>'
        else:
            title_html = title
            source_html = ""

        meta_bits = [
            html.escape(value)
            for value in (item["source"], item["date"], item["category"])
            if value
        ]
        meta = " · ".join(meta_bits)
        cards.append(
            f"""
            <article class="card">
              <h2>{title_html}</h2>
              <p class="meta">{meta}</p>
              <p>{html.escape(item['summary'])}</p>
              <p class="source">{source_html}</p>
            </article>
            """
        )

    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>n8n RSS 干跑结果</title>
  <style>
    :root {{ color-scheme: light; --ink: #17202a; --muted: #667085; --line: #e4e7ec; --accent: #175cd3; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f6f8fb; color: var(--ink); font: 16px/1.65 system-ui, -apple-system, "Segoe UI", sans-serif; }}
    main {{ width: min(920px, calc(100% - 32px)); margin: 40px auto; }}
    header {{ margin-bottom: 28px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(28px, 5vw, 44px); }}
    .notice {{ color: var(--muted); }}
    .card {{ margin: 16px 0; padding: 22px 24px; background: white; border: 1px solid var(--line); border-radius: 16px; box-shadow: 0 8px 28px rgba(16, 24, 40, .05); }}
    h2 {{ margin: 0 0 8px; font-size: 20px; line-height: 1.35; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .meta {{ margin: 0 0 12px; color: var(--muted); font-size: 13px; }}
    .source {{ margin-bottom: 0; font-size: 14px; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>AI 资讯 RSS 干跑</h1>
      <p class="notice">公开 RSS + 原 DeepSeek 翻译/分类链；最多 5 条，未连接飞书推送。</p>
      <p class="notice">生成时间：{html.escape(generated)}</p>
    </header>
    {''.join(cards)}
  </main>
</body>
</html>
"""


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: render-dry-run.py <execution.json> <summary.json> <report.html>", file=sys.stderr)
        return 64

    execution_path = Path(sys.argv[1])
    summary_path = Path(sys.argv[2])
    report_path = Path(sys.argv[3])

    execution = load_execution_json(execution_path)
    run_data = find_run_data(execution)
    if run_data is None:
        print("n8n execution JSON did not contain runData", file=sys.stderr)
        return 2

    raw_items = node_items(run_data, FINAL_NODE)
    items = [normalize_item(item) for item in raw_items]

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "final_node": FINAL_NODE,
                "item_count": len(items),
                "items": items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    report_path.write_text(render_html(items), encoding="utf-8")

    print(f"Rendered {len(items)} items from node '{FINAL_NODE}'.")
    for index, item in enumerate(items, start=1):
        print(f"{index}. [{item['category'] or '未分类'}] {item['title']}")

    return 0 if items else 2


if __name__ == "__main__":
    raise SystemExit(main())
