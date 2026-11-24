#!/usr/bin/env python3
"""Write pending items from the run summary into Feishu Bitable."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from feishu_bitable import build_records, create_records, list_fields, tenant_token


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--app-secret", required=True)
    parser.add_argument("--app-token", required=True)
    parser.add_argument("--table-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    config = load_json(args.config)
    if not config.get("enabled", True):
        result = {"enabled": False, "created": 0}
    else:
        summary = load_json(args.summary)
        token = tenant_token(args.app_id, args.app_secret)
        fields = list_fields(token, args.app_token, args.table_id)
        records = build_records(
            summary.get("pending_items") or [],
            fields,
            config["field_map"],
        )
        result = {
            "enabled": True,
            "pending_items": len(summary.get("pending_items") or []),
            "mapped_records": len(records),
            "available_fields": [field.name for field in fields],
            **create_records(token, args.app_token, args.table_id, records),
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Feishu Bitable: pending={result.get('pending_items', 0)}, "
        f"mapped={result.get('mapped_records', 0)}, created={result.get('created', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
