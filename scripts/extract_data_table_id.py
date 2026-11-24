#!/usr/bin/env python3
"""Extract the data table ID emitted by the bootstrap workflow."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


NODE_NAME = "确保已推送记录表"


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
    raise ValueError("No executable JSON document was found in bootstrap output")


def table_ids(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        if value.get("name") == "已推送记录" and isinstance(value.get("id"), str):
            found.append(value["id"])
        for child in value.values():
            found.extend(table_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(table_ids(child))
    return found


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: extract_data_table_id.py <bootstrap-output>", file=sys.stderr)
        return 64

    raw = Path(sys.argv[1]).read_text(encoding="utf-8")
    execution = decode_execution(raw)
    run_data = find_run_data(execution)
    node_runs = (run_data or {}).get(NODE_NAME)
    if not isinstance(node_runs, list):
        raise ValueError(f"Bootstrap node did not run: {NODE_NAME}")

    candidates = table_ids(node_runs)
    unique = list(dict.fromkeys(candidates))
    if len(unique) != 1 or len(unique[0]) != 16:
        raise ValueError(f"Expected one 16-character data table ID, got {unique}")

    print(unique[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
