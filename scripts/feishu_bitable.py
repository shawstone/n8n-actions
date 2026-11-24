"""Small Feishu Bitable API client used by GitHub Actions."""

from __future__ import annotations

import json
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


API_BASE = "https://open.feishu.cn/open-apis"


class FeishuError(RuntimeError):
    pass


@dataclass
class BitableField:
    name: str
    type: int


def request_json(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    data = None
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        API_BASE + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise FeishuError(f"Feishu HTTP {error.code}: {detail[:1000]}") from error
    except urllib.error.URLError as error:
        raise FeishuError(f"Feishu network error: {error.reason}") from error

    if not isinstance(payload, dict):
        raise FeishuError("Feishu returned a non-object response")
    if payload.get("code") not in (0, None):
        raise FeishuError(
            f"Feishu API code={payload.get('code')} msg={payload.get('msg', '')}"
        )
    return payload


def tenant_token(app_id: str, app_secret: str) -> str:
    payload = request_json(
        "POST",
        "/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
    )
    token = payload.get("tenant_access_token")
    if not token:
        raise FeishuError("Feishu response did not include tenant_access_token")
    return str(token)


def list_fields(token: str, app_token: str, table_id: str) -> list[BitableField]:
    fields: list[BitableField] = []
    page_token: str | None = None
    while True:
        query = "?page_size=100"
        if page_token:
            query += "&page_token=" + urllib.parse.quote(page_token)
        payload = request_json(
            "GET",
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields{query}",
            token=token,
        )
        data = payload.get("data") or {}
        for item in data.get("items") or []:
            fields.append(BitableField(name=str(item.get("field_name")), type=int(item.get("type"))))
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
        if not page_token:
            break
    return fields


def adapt_value(value: Any, field_type: int, title: str) -> Any:
    if value in (None, ""):
        return None

    if field_type == 15:  # URL
        text = title or str(value)
        return {"link": str(value), "text": text}
    if field_type == 5:  # DateTime, milliseconds
        from datetime import datetime

        text = str(value).replace("Z", "+00:00")
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    if field_type in (3, 4):  # Single/multi select
        parts = [part.strip() for part in str(value).split("/") if part.strip()]
        return parts if field_type == 4 else (parts[0] if parts else None)
    if field_type == 2:  # Number
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if field_type == 7:  # Checkbox
        return bool(value)
    return str(value)


def build_records(
    pending_items: list[dict[str, Any]],
    fields: list[BitableField],
    field_map: dict[str, str],
) -> list[dict[str, Any]]:
    by_name = {field.name: field for field in fields}
    records: list[dict[str, Any]] = []

    for item in pending_items:
        values: dict[str, Any] = {}
        title = str(item.get("title") or "")
        for source_key, target_name in field_map.items():
            field = by_name.get(target_name)
            if field is None:
                continue
            adapted = adapt_value(item.get(source_key), field.type, title)
            if adapted is not None:
                values[target_name] = adapted
        if values:
            records.append({"fields": values})
    return records


def create_records(
    token: str,
    app_token: str,
    table_id: str,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    if not records:
        return {"created": 0, "code": 0, "msg": "nothing to write"}

    payload = request_json(
        "POST",
        f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
        {"records": records},
        token=token,
    )
    created = len(((payload.get("data") or {}).get("records") or []))
    return {"created": created, "code": payload.get("code", 0), "msg": payload.get("msg", "")}
