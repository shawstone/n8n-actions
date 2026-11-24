#!/usr/bin/env python3
"""Fast structural checks that don't call n8n or external APIs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_PATTERN = re.compile(
    r"""\$items\s*\(\s*["'](?P<items>[^"']+)["']"""
    r"""|\$\(\s*["'](?P<expression>[^"']+)["']"""
    r"""|\$node\[\s*["'](?P<node>[^"']+)["']"""
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_strings(child)


def validate_template() -> dict[str, Any]:
    template_path = ROOT / "n8n" / "workflow.template.json"
    template_text = template_path.read_text(encoding="utf-8")
    workflow = json.loads(template_text)
    names = {node["name"] for node in workflow["nodes"]}

    if len(workflow["nodes"]) != 73:
        raise ValueError(f"Expected 73 template nodes, got {len(workflow['nodes'])}")
    if workflow.get("id") != "v2NewsAggregate1":
        raise ValueError("Unexpected workflow ID")

    referenced: set[str] = set()
    for text in walk_strings(workflow.get("nodes")):
        for match in REFERENCE_PATTERN.finditer(text):
            name = next(value for value in match.groupdict().values() if value)
            referenced.add(name)

    missing = sorted(referenced - names)
    if missing:
        raise ValueError("Template references missing nodes: " + ", ".join(missing))

    if re.search(r"sk-[A-Za-z0-9_-]{20,}", template_text):
        raise ValueError("Possible API key literal found in workflow template")
    if re.search(r"open-apis/bot/v2/hook/(?!REPLACE_WITH_)[A-Za-z0-9_-]{16,}", template_text):
        raise ValueError("Possible Feishu webhook token found in workflow template")
    for node in workflow["nodes"]:
        if node.get("type") == "n8n-nodes-base.dataTable":
            value = (node.get("parameters", {}).get("dataTableId") or {}).get("value")
            if value != "REPLACE_WITH_DATA_TABLE_ID":
                raise ValueError(f"Data Table placeholder missing in node: {node['name']}")

    return workflow


def validate_bootstrap() -> None:
    workflow = load_json(ROOT / "n8n" / "bootstrap-datatable.json")
    if workflow.get("id") != "v2DataTableBoot1":
        raise ValueError("Unexpected bootstrap workflow ID")
    nodes = workflow.get("nodes", [])
    tables = [node for node in nodes if node.get("type") == "n8n-nodes-base.dataTable"]
    if len(tables) != 1:
        raise ValueError("Bootstrap workflow must contain exactly one Data Table node")
    columns = tables[0]["parameters"]["columns"]["column"]
    if [column["name"] for column in columns] != ["link", "title", "pushed_at"]:
        raise ValueError("Unexpected pushed-record table columns")


def validate_config(template: dict[str, Any]) -> None:
    names = {node["name"] for node in template["nodes"]}
    sources = load_json(ROOT / "config" / "sources.json")
    for name in sources["rss_nodes"]:
        if name not in names:
            raise ValueError(f"Configured RSS node not found: {name}")
    for feed in sources["extra_feeds"]:
        if not feed.get("url") and not feed.get("source"):
            continue
        if not str(feed.get("url", "")).startswith(("http://", "https://")):
            raise ValueError("Every extra feed needs an HTTP(S) URL")
        if not feed.get("source"):
            raise ValueError("Every extra feed needs a source label")
    if not sources["youtube_channels"]:
        raise ValueError("At least one YouTube channel ID is required")

    rules = load_json(ROOT / "config" / "tag-rules.json")
    filled_rules = [
        rule for rule in rules if rule.get("label") or rule.get("pattern")
    ]
    labels = [rule["label"] for rule in filled_rules]
    if len(labels) != len(set(labels)):
        raise ValueError("Tag labels must be unique")
    for rule in filled_rules:
        if not rule.get("label") or not rule.get("pattern"):
            raise ValueError(f"Empty tag pattern for {rule['label']}")

    for prompt_name in ("ai-classify.txt", "language-analysis.txt"):
        prompt = (ROOT / "config" / "prompts" / prompt_name).read_text(encoding="utf-8")
        if not prompt.strip():
            raise ValueError(f"Prompt is empty: {prompt_name}")


def main() -> int:
    template = validate_template()
    validate_bootstrap()
    validate_config(template)
    print("Project validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
