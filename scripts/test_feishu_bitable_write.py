#!/usr/bin/env python3
"""Write one clearly marked test record to the configured Bitable."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from feishu_bitable import create_records, list_fields, tenant_token


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--app-secret", required=True)
    parser.add_argument("--app-token", required=True)
    parser.add_argument("--table-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    token = tenant_token(args.app_id, args.app_secret)
    fields = list_fields(token, args.app_token, args.table_id)
    if "文本" not in {field.name for field in fields}:
        raise RuntimeError("The Bitable has no '文本' text field")

    record = {
        "fields": {
            "文本": (
                "测试记录：GitHub Actions 已成功连接飞书多维表格。"
                "此条记录可以删除。"
            )
        }
    }
    result = create_records(token, args.app_token, args.table_id, [record])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Feishu Bitable test write completed: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
