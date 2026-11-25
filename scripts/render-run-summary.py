#!/usr/bin/env python3
"""Write a small, secret-free summary from n8n execution output."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from n8n_execution import find_run_data, load_execution, node_items


FINAL_NODE = "分类排序1"


def first_value(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: render-run-summary.py <execution.json> <summary.json>", file=sys.stderr)
        return 64

    execution_path = Path(sys.argv[1])
    summary_path = Path(sys.argv[2])
    execution = load_execution(execution_path)
    run_data = find_run_data(execution)
    if run_data is None:
        raise ValueError("Execution contains no runData")

    items = node_items(run_data, FINAL_NODE)
    pending_items = node_items(run_data, "待观察占位输出")
    previous_records = node_items(run_data, "读取已推送记录")
    written_records = node_items(run_data, "已推送记录")
    webhook_responses = []
    for response in node_items(run_data, "HTTP Request7"):
        selected = {
            key: response[key]
            for key in ("code", "msg", "message", "status", "statusCode", "StatusCode")
            if key in response
        }
        if selected:
            webhook_responses.append(selected)

    node_errors = []
    for node_name, runs in run_data.items():
        if not isinstance(runs, list):
            continue
        for run in runs:
            if not isinstance(run, dict) or not run.get("error"):
                continue
            error = run["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            node_errors.append({"node": node_name, "message": str(message)[:500]})

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "final_node": FINAL_NODE,
        "item_count": len(items),
        "pending_item_count": len(pending_items),
        "previous_record_count": len(previous_records),
        "written_record_count": len(written_records),
        "previous_record_samples": previous_records[:3],
        "written_record_samples": written_records[:3],
        "feishu_webhook_responses": webhook_responses,
        "node_errors": node_errors,
        "items": [
            {
                "title": first_value(item, "标题", "title"),
                "category": first_value(item, "分类", "category"),
                "labels": first_value(item, "标签", "labels"),
                "source": first_value(item, "来源", "source"),
                "date": first_value(item, "日期", "date"),
                "link": first_value(item, "链接", "url", "link"),
            }
            for item in items
        ],
        "pending_items": [
            {
                "title": first_value(item, "标题", "title"),
                "link": first_value(item, "链接", "url", "link"),
                "source": first_value(item, "来源", "source"),
                "labels": first_value(item, "标签", "labels"),
                "date": first_value(item, "日期", "date"),
            }
            for item in pending_items
        ],
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote secret-free summary with {len(items)} items.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
