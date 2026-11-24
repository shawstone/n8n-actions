#!/usr/bin/env python3
"""Extract the data table ID emitted by the bootstrap workflow."""

from __future__ import annotations

import sys
from pathlib import Path

from n8n_execution import flattened_items, load_execution, resolve_flat


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: extract_data_table_id.py <bootstrap-output>", file=sys.stderr)
        return 64

    execution = load_execution(Path(sys.argv[1]))
    flat = flattened_items(execution)
    if flat is None:
        raise ValueError("Bootstrap response did not contain n8n execution data")
    candidates: list[str] = []
    for item in flat:
        if not (
            isinstance(item, dict)
            and "columns" in item
            and "id" in item
            and "name" in item
        ):
            continue
        resolved = resolve_flat(item, flat)
        if isinstance(resolved, dict) and resolved.get("name") == "已推送记录":
            candidates.append(str(resolved.get("id", "")))
    unique = list(dict.fromkeys(candidates))
    if len(unique) != 1 or len(unique[0]) != 16:
        raise ValueError(f"Expected one 16-character data table ID, got {unique}")

    print(unique[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
