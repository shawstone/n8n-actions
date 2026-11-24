#!/usr/bin/env python3
"""Write a small, secret-free summary from n8n execution output."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FINAL_NODE = "分类排序1"


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


def decode_execution(raw: str) -> Any:
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
    raise ValueError("No executable n8n JSON document was found")


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
    execution = decode_execution(
        execution_path.read_text(encoding="utf-8", errors="replace")
    )
    run_data = find_run_data(execution)
    if run_data is None:
        raise ValueError("Execution contains no runData")

    items: list[dict[str, Any]] = []
    for run in run_data.get(FINAL_NODE, []):
        branches = (run.get("data") or {}).get("main") or []
        for branch in branches:
            for item in branch or []:
                value = item.get("json") if isinstance(item, dict) and "json" in item else item
                if isinstance(value, dict):
                    items.append(value)

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
