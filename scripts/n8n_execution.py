"""Helpers for reading n8n REST execution responses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_execution(path: Path) -> dict[str, Any]:
    execution = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(execution, dict):
        raise ValueError("Execution response must be a JSON object")
    return execution


def flattened_items(execution: dict[str, Any]) -> list[Any] | None:
    data = execution.get("data")
    if isinstance(data, str):
        try:
            value = json.loads(data)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, list) else None
    return data if isinstance(data, list) else None


def resolve_flat(value: Any, flat: list[Any], active: set[int] | None = None) -> Any:
    if active is None:
        active = set()

    if isinstance(value, str) and value.isdigit():
        index = int(value)
        if index >= len(flat) or index in active:
            return None
        active.add(index)
        try:
            return resolve_flat(flat[index], flat, active)
        finally:
            active.remove(index)

    if isinstance(value, list):
        return [resolve_flat(child, flat, active) for child in value]

    if isinstance(value, dict):
        return {key: resolve_flat(child, flat, active) for key, child in value.items()}

    return value


def find_run_data(execution: dict[str, Any]) -> dict[str, Any] | None:
    flat = flattened_items(execution)
    if flat is not None:
        for item in flat:
            if isinstance(item, dict) and "runData" in item:
                resolved = resolve_flat(item["runData"], flat)
                if isinstance(resolved, dict):
                    return resolved

    current: Any = execution
    if isinstance(current.get("data"), str):
        try:
            current = json.loads(current["data"])
        except json.JSONDecodeError:
            return None
    if isinstance(current, dict) and isinstance(current.get("runData"), dict):
        return current["runData"]
    return None


def node_items(run_data: dict[str, Any], node_name: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for run in run_data.get(node_name, []):
        if not isinstance(run, dict):
            continue
        for branch in (run.get("data") or {}).get("main") or []:
            for item in branch or []:
                value = item.get("json") if isinstance(item, dict) and "json" in item else item
                if isinstance(value, dict):
                    items.append(value)
    return items
