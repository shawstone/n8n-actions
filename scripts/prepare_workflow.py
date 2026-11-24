#!/usr/bin/env python3
"""Render the committed n8n template into a runtime workflow."""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
from typing import Any


DEEPSEEK_CREDENTIAL_ID = "xvaefodMzAZCsD3v"
FEISHU_CREDENTIAL_ID = "v2FeishuCred0001"
DRY_RUN_LIMIT_NODE_ID = "f425620f-4c52-4f13-93b6-8b41a17d7afb"
EXTRA_FEED_INPUT_NODE_ID = "e9606b82-9f29-4d5c-b7a8-5ef62415a4c8"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def node_by_name(workflow: dict[str, Any], name: str) -> dict[str, Any]:
    for node in workflow["nodes"]:
        if node.get("name") == name:
            return node
    raise ValueError(f"Workflow node not found: {name}")


def js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_tag_rules(rules: list[dict[str, str]], only_filter: bool) -> str:
    rule_lines = "\n".join(
        f"  [new RegExp({js_string(rule['pattern'])}, 'i'), {js_string(rule['label'])}],"
        for rule in rules
    )

    if only_filter:
        return f"""// Generated from config/tag-rules.json.
// Stage 1: keep an item only when at least one configured rule matches its title.
const src = $json;

const 标签规则 = [
{rule_lines}
];

const 标题 = String(src['标题'] || '');
const 命中 = 标签规则.some(([词]) => 词.test(标题));
if (!命中) return null;

const 净 = 标题
  .replace(/<[^>]+>/g, ' ')
  .replace(/&nbsp;/g, ' ')
  .replace(/\\s+/g, ' ')
  .trim();

return {{ json: {{ ...src, 标题: 净.length > 200 ? 净.slice(0, 200) : 净 }} }};
"""

    return f"""// Generated from config/tag-rules.json.
// Stage 2: attach all matching labels to the item before AI classification.
const src = $json;

const 标签规则 = [
{rule_lines}
];

const 标题 = String(src['标题'] || '');
const 标签组 = [];

for (const [词, 名] of 标签规则) {{
  if (词.test(标题) && !标签组.includes(名)) 标签组.push(名);
}}

return {{ json: {{ ...src, 标签: 标签组.join('/') || '未分类' }} }};
"""


def patch_sources(workflow: dict[str, Any], sources: dict[str, Any]) -> None:
    for name, url in sources.get("rss_nodes", {}).items():
        node_by_name(workflow, name)
        if url:
            node_by_name(workflow, name)["parameters"]["url"] = url

    youtube_node = node_by_name(workflow, "油管更新")
    youtube_node["parameters"]["jsonOutput"] = {
        "feeds": list(sources.get("youtube_channels", []))
    }


def configure_optional_source(workflow: dict[str, Any], sources: dict[str, Any]) -> None:
    extra_feeds = sources.get("extra_feeds", [])
    if extra_feeds:
        for feed in extra_feeds:
            if not str(feed.get("url", "")).startswith(("http://", "https://")):
                raise ValueError("Every extra feed needs an HTTP(S) URL")

        input_node_name = "Extra Feed Input"
        workflow["nodes"].append(
            {
                "parameters": {
                    "mode": "runOnceForAllItems",
                    "jsCode": (
                        "const feeds = "
                        + json.dumps(extra_feeds, ensure_ascii=False)
                        + ";\nreturn feeds.map((feed) => ({ json: feed }));"
                    ),
                },
                "id": EXTRA_FEED_INPUT_NODE_ID,
                "name": input_node_name,
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [-280, 340],
            }
        )

        for edge in workflow["connections"]["Schedule Trigger"]["main"][0]:
            if edge.get("node") == "补充源 RSS":
                edge["node"] = input_node_name
        workflow["connections"][input_node_name] = {
            "main": [[{"node": "补充源 RSS", "type": "main", "index": 0}]]
        }

        node_by_name(workflow, "补充源 RSS")["parameters"]["url"] = "={{ $json.url }}"
        source_assignments = node_by_name(workflow, "补充源字段")["parameters"][
            "assignments"
        ]["assignments"]
        for assignment in source_assignments:
            if assignment.get("name") == "来源":
                assignment["value"] = (
                    "={{ $('Extra Feed Input').item.json.source || '补充源' }}"
                )
        return

    workflow["nodes"] = [
        node
        for node in workflow["nodes"]
        if node.get("name") not in {"补充源 RSS", "补充源字段"}
    ]

    schedule = workflow["connections"].get("Schedule Trigger", {})
    for branch in schedule.get("main", []):
        if isinstance(branch, list):
            branch[:] = [edge for edge in branch if edge.get("node") != "补充源 RSS"]

    merge_node = node_by_name(workflow, "Merge4")
    merge_node["type"] = "n8n-nodes-base.noOp"
    merge_node["typeVersion"] = 1
    merge_node["parameters"] = {}
    merge_node.pop("credentials", None)

    workflow["connections"].pop("补充源 RSS", None)
    workflow["connections"].pop("补充源字段", None)


def patch_tables(workflow: dict[str, Any], data_table_id: str) -> None:
    if not data_table_id:
        raise ValueError("DATA_TABLE_ID is required")

    for node in workflow["nodes"]:
        if node.get("type") != "n8n-nodes-base.dataTable":
            continue
        node.setdefault("parameters", {})["dataTableId"] = {
            "__rl": True,
            "mode": "id",
            "value": data_table_id,
        }


def patch_credentials_and_secrets(workflow: dict[str, Any], publish: bool) -> None:
    feishu_bitable = node_by_name(workflow, "飞书多维表格")
    feishu_bitable["credentials"] = {
        "feishuCredentialsApi": {"id": FEISHU_CREDENTIAL_ID}
    }

    app_token = os.getenv("FEISHU_BITABLE_APP_TOKEN", "").strip()
    table_id = os.getenv("FEISHU_BITABLE_TABLE_ID", "").strip()
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL", "").strip()

    if app_token:
        feishu_bitable["parameters"]["app_toke"] = app_token
    if table_id:
        feishu_bitable["parameters"]["table_id"] = table_id
    if webhook_url:
        node_by_name(workflow, "HTTP Request7")["parameters"]["url"] = webhook_url

    if publish:
        missing = [
            name
            for name, value in {
                "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
                "FEISHU_WEBHOOK_URL": webhook_url,
                "FEISHU_APP_ID": os.getenv("FEISHU_APP_ID"),
                "FEISHU_APP_SECRET": os.getenv("FEISHU_APP_SECRET"),
                "FEISHU_BITABLE_APP_TOKEN": app_token,
                "FEISHU_BITABLE_TABLE_ID": table_id,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError("Missing required action secrets: " + ", ".join(missing))

        if not webhook_url.startswith("https://open.feishu.cn/"):
            raise ValueError("FEISHU_WEBHOOK_URL must point to open.feishu.cn")


def replace_with_noop(workflow: dict[str, Any], node_names: set[str]) -> None:
    for name in node_names:
        node = node_by_name(workflow, name)
        node["type"] = "n8n-nodes-base.noOp"
        node["typeVersion"] = 1
        node["parameters"] = {}
        node.pop("credentials", None)


def add_dry_run_limit(workflow: dict[str, Any]) -> None:
    limit = int(os.getenv("DRY_RUN_LIMIT", "3"))
    workflow["nodes"].append(
        {
            "parameters": {
                "mode": "runOnceForAllItems",
                "jsCode": f"return $input.all().slice(0, {limit});",
            },
            "id": DRY_RUN_LIMIT_NODE_ID,
            "name": "Dry Run Limit",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1260, 940],
        }
    )

    source_branches = workflow["connections"]["补默认值"]["main"][0]
    for edge in source_branches:
        if edge.get("node") == "24h内5":
            edge["node"] = "Dry Run Limit"

    workflow["connections"]["Dry Run Limit"] = {
        "main": [[{"node": "24h内5", "type": "main", "index": 0}]]
    }


def patch_prompts_and_tags(workflow: dict[str, Any], config_dir: Path) -> None:
    rules = load_json(config_dir / "tag-rules.json")
    node_by_name(workflow, "本地标签筛选")["parameters"]["jsCode"] = render_tag_rules(
        rules, only_filter=True
    )
    node_by_name(workflow, "打标签")["parameters"]["jsCode"] = render_tag_rules(
        rules, only_filter=False
    )

    ai_classify_prompt = (config_dir / "prompts" / "ai-classify.txt").read_text(
        encoding="utf-8"
    ).rstrip()
    language_prompt = (
        config_dir / "prompts" / "language-analysis.txt"
    ).read_text(encoding="utf-8").rstrip()

    node_by_name(workflow, "AI批量分类")["parameters"]["text"] = (
        "=" + ai_classify_prompt
    )
    node_by_name(workflow, "语言资讯深度解析")["parameters"]["text"] = (
        "=" + language_prompt
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--config-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=("dry-run", "publish"), default="dry-run")
    args = parser.parse_args()

    workflow = copy.deepcopy(load_json(args.template))
    sources = load_json(args.config_dir / "sources.json")

    patch_sources(workflow, sources)
    configure_optional_source(workflow, sources)
    patch_prompts_and_tags(workflow, args.config_dir)

    data_table_id = os.getenv("DATA_TABLE_ID", "").strip()
    patch_tables(workflow, data_table_id)
    patch_credentials_and_secrets(workflow, publish=args.mode == "publish")
    workflow["active"] = False

    if args.mode == "dry-run":
        replace_with_noop(
            workflow,
            {"HTTP Request7", "飞书多维表格", "已推送记录", "清理旧纪录"},
        )
        add_dry_run_limit(workflow)

    save_json(args.output, workflow)
    print(
        f"Rendered {len(workflow['nodes'])} nodes in {args.mode} mode "
        f"to {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
