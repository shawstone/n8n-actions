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

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "final_node": FINAL_NODE,
        "item_count": len(items),
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
