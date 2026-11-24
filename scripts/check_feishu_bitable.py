#!/usr/bin/env python3
"""Inspect the configured Bitable fields without writing records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from feishu_bitable import list_fields, tenant_token


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
    output = {
        "table_id": args.table_id,
        "field_count": len(fields),
        "fields": [
            {
                "name": field.name,
                "type": field.type,
            }
            for field in fields
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Feishu Bitable check passed with {len(fields)} fields.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
