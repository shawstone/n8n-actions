#!/usr/bin/env python3
"""Run a workflow through n8n's authenticated internal REST endpoint."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {"success", "error", "crashed", "canceled", "failed"}


class N8nClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.browser_id = str(uuid.uuid4())
        self.auth_cookie: str | None = None
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> Any:
        data = None
        headers = {
            "Accept": "application/json",
            "browser-id": self.browser_id,
        }
        if self.auth_cookie:
            headers["Cookie"] = self.auth_cookie
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        with self.opener.open(request, timeout=timeout) as response:
            raw = response.read()
        if not raw:
            return None
        return json.loads(raw)

    def login(self, email: str, password: str) -> None:
        self.request(
            "POST",
            "/rest/login",
            {"emailOrLdapLoginId": email, "password": password},
        )
        if not self.cookies:
            raise RuntimeError("n8n login succeeded without returning a session cookie")
        auth_cookie = next(
            (cookie for cookie in self.cookies if cookie.name == "n8n-auth"),
            None,
        )
        if auth_cookie is None:
            raise RuntimeError("n8n login did not return the n8n-auth cookie")
        # n8n marks this cookie Secure even on an HTTP localhost instance. The
        # workflow runner talks to localhost inside the same Actions job, so send
        # the cookie explicitly instead of relying on CookieJar's scheme check.
        self.auth_cookie = f"n8n-auth={auth_cookie.value}"

    def run_workflow(self, workflow_id: str, trigger_name: str) -> str:
        response = self.request(
            "POST",
            f"/rest/workflows/{workflow_id}/run",
            {"triggerToStartFrom": {"name": trigger_name}},
            timeout=120,
        )
        payload = response.get("data", response) if isinstance(response, dict) else {}
        execution_id = payload.get("executionId")
        if not execution_id:
            raise RuntimeError(f"n8n returned no executionId: {response!r}")
        return str(execution_id)

    def wait_for_execution(self, execution_id: str, timeout_seconds: int) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            response = self.request(
                "GET",
                f"/rest/executions/{execution_id}?includeData=true",
                timeout=120,
            )
            execution = response.get("data", response) if isinstance(response, dict) else {}
            status = str(execution.get("status", "")).lower()
            if status in TERMINAL_STATUSES:
                return execution
            time.sleep(3)
        raise TimeoutError(f"n8n execution {execution_id} did not finish within {timeout_seconds}s")


def print_execution_error(execution: dict[str, Any]) -> None:
    serialized = json.dumps(execution, ensure_ascii=False)
    decoder = json.JSONDecoder()
    messages: list[str] = []
    for index, char in enumerate(serialized):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(serialized[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            for key in ("message", "error", "description"):
                text = value.get(key)
                if isinstance(text, str) and len(text) < 1200:
                    messages.append(text)
            if messages:
                break
    for message in dict.fromkeys(messages):
        print(f"n8n error: {message}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5678")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--trigger-name", required=True)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    client = N8nClient(args.base_url)
    client.login(args.email, args.password)
    execution_id = client.run_workflow(args.workflow_id, args.trigger_name)
    print(f"Started n8n execution {execution_id}")
    execution = client.wait_for_execution(execution_id, args.timeout)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(execution, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    status = str(execution.get("status", "")).lower()
    print(f"n8n execution {execution_id} finished with status: {status}")
    if status != "success":
        print_execution_error(execution)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
