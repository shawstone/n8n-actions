#!/usr/bin/env bash
set -Eeuo pipefail

N8N_IMAGE="${N8N_IMAGE:-docker.n8n.io/n8nio/n8n:2.47.4}"
CONTAINER_NAME="${CONTAINER_NAME:-n8n-rss-dry-run}"
EXECUTION_CONTAINER_NAME="${EXECUTION_CONTAINER_NAME:-n8n-rss-dry-run-execute}"
WORKFLOW_ID="${WORKFLOW_ID:-SDbEpCrT1vf0m3gr}"
EXPECTED_WORKFLOW_SHA256="${EXPECTED_WORKFLOW_SHA256:-492A6C99A7AF6AC71D8AD45017DB4FF1D907881672D323DC7D521B17BB4F28EF}"

run_root="${RUNNER_TEMP:-/tmp}/n8n-rss-dry-run"
data_dir="${run_root}/data"
original_workflow="${run_root}/original-workflow.json"
dry_run_workflow="${run_root}/dry-run-workflow.json"
credentials_json="${run_root}/credentials.json"
execution_json="${run_root}/execution.json"
execution_log="${run_root}/execution.log"
artifact_dir="${GITHUB_WORKSPACE:-$PWD}/dry-run"

mkdir -p "$data_dir" "$artifact_dir"
sudo chown --recursive 1000:1000 "$data_dir"

cleanup() {
  local exit_code=$?
  if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    echo "::group::n8n container logs"
    docker logs --tail 200 "$CONTAINER_NAME" || true
    echo "::endgroup::"
    docker rm --force "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
  docker rm --force "$EXECUTION_CONTAINER_NAME" >/dev/null 2>&1 || true
  exit "$exit_code"
}
trap cleanup EXIT

wait_for_n8n() {
  local attempt
  for attempt in $(seq 1 120); do
    if curl --fail --silent --show-error http://127.0.0.1:5678/healthz >/dev/null; then
      echo "n8n is ready after $((attempt * 2)) seconds."
      return 0
    fi
    if ! docker inspect --format '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null | grep -q true; then
      echo "n8n container stopped before becoming healthy." >&2
      return 1
    fi
    sleep 2
  done
  echo "n8n did not become healthy within 240 seconds." >&2
  return 1
}

if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "The DEEPSEEK_API_KEY GitHub Actions secret is missing." >&2
  exit 2
fi

echo "Restoring and verifying the untouched original workflow."
base64 --decode n8n/workflow.json.gz.b64 | gzip --decompress > "$original_workflow"
actual_sha256="$(sha256sum "$original_workflow" | awk '{print toupper($1)}')"
if [[ "$actual_sha256" != "$EXPECTED_WORKFLOW_SHA256" ]]; then
  echo "Workflow checksum mismatch: expected $EXPECTED_WORKFLOW_SHA256, got $actual_sha256" >&2
  exit 1
fi

echo "Creating the RSS-only dry-run copy; the committed original remains unchanged."
jq '
  .name = "n8n信息聚合器 [RSS dry run]"
  | .active = false
  | .nodes |= map(
      if .type == "n8n-nodes-feishu-lite.feishuNode" then
        .type = "n8n-nodes-base.noOp"
        | .typeVersion = 1
        | .parameters = {}
        | del(.credentials)
      else .
      end
    )
  | .connections["Schedule Trigger"].main[0] = []
  | .connections["Execute Workflow Trigger"] = {
      "main": [[
        { "node": "Techcrunch", "type": "main", "index": 0 },
        { "node": "Theverge", "type": "main", "index": 0 },
        { "node": "纽约时报", "type": "main", "index": 0 }
      ]]
    }
  | .connections["Merge6"].main[0] = [
      { "node": "Limit test items", "type": "main", "index": 0 }
    ]
  | .connections["Limit test items"] = {
      "main": [[{ "node": "24h内5", "type": "main", "index": 0 }]]
    }
  | .connections["分类排序"].main[0] = []
  | .nodes += [
      {
        "parameters": { "inputSource": "passthrough" },
        "id": "c894e836-abf2-43d8-aa6d-218a778fa414",
        "name": "Execute Workflow Trigger",
        "type": "n8n-nodes-base.executeWorkflowTrigger",
        "typeVersion": 1.1,
        "position": [-300, 1180]
      },
      {
        "parameters": {
          "mode": "runOnceForAllItems",
          "jsCode": "return $input.all().slice(0, 5);"
        },
        "id": "91eb0f8e-6daf-4c03-8bf9-3f8372851b6d",
        "name": "Limit test items",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [820, 1180]
      }
    ]
' "$original_workflow" > "$dry_run_workflow"

jq -e '
  (.connections["Execute Workflow Trigger"].main[0] | length) == 3
  and (.connections["Schedule Trigger"].main[0] | length) == 0
  and (.connections["分类排序"].main[0] | length) == 0
  and ([.nodes[] | select(.type == "n8n-nodes-feishu-lite.feishuNode")] | length) == 0
  and ([.nodes[] | select(.name == "Limit test items")] | length) == 1
' "$dry_run_workflow" >/dev/null

cp "$dry_run_workflow" "$artifact_dir/dry-run-workflow.json"
echo "Dry-run workflow checks passed: CLI trigger, 3 RSS feeds, 5-item cap, Feishu disabled."

jq -n --arg apiKey "$DEEPSEEK_API_KEY" '[{
  "id": "yt8fyLgfmvOBHB4v",
  "name": "DeepSeek account",
  "type": "deepSeekApi",
  "data": {
    "apiKey": $apiKey,
    "url": "https://api.deepseek.com"
  }
}]' > "$credentials_json"

encryption_key="$(openssl rand -hex 32)"
owner_password_hash='$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy'

echo "Starting pinned n8n image: $N8N_IMAGE"
docker run --detach \
  --name "$CONTAINER_NAME" \
  --publish 5678:5678 \
  --env "N8N_ENCRYPTION_KEY=$encryption_key" \
  --env "N8N_INSTANCE_OWNER_MANAGED_BY_ENV=true" \
  --env "N8N_INSTANCE_OWNER_EMAIL=phase1-owner@example.invalid" \
  --env "N8N_INSTANCE_OWNER_FIRST_NAME=Phase1" \
  --env "N8N_INSTANCE_OWNER_LAST_NAME=Owner" \
  --env "N8N_INSTANCE_OWNER_PASSWORD_HASH=$owner_password_hash" \
  --env "N8N_UNVERIFIED_PACKAGES_ENABLED=true" \
  --env "N8N_RUNNERS_TASK_TIMEOUT=300" \
  --env "N8N_DIAGNOSTICS_ENABLED=false" \
  --env "N8N_VERSION_NOTIFICATIONS_ENABLED=false" \
  --env "N8N_PERSONALIZATION_ENABLED=false" \
  --env "N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true" \
  --env "GENERIC_TIMEZONE=Asia/Shanghai" \
  --env "TZ=Asia/Shanghai" \
  --volume "${data_dir}:/home/node/.n8n" \
  "$N8N_IMAGE" >/dev/null

wait_for_n8n

echo "Importing the test-only DeepSeek credential."
docker cp "$credentials_json" "${CONTAINER_NAME}:/tmp/credentials.json"
docker exec --user node "$CONTAINER_NAME" n8n import:credentials --input=/tmp/credentials.json

echo "Importing the RSS dry-run workflow."
docker cp "$dry_run_workflow" "${CONTAINER_NAME}:/tmp/dry-run-workflow.json"
docker exec --user node "$CONTAINER_NAME" n8n import:workflow --input=/tmp/dry-run-workflow.json

echo "Stopping the temporary n8n server before the isolated CLI execution."
docker stop "$CONTAINER_NAME" >/dev/null

echo "Executing the RSS dry-run workflow."
set +e
docker run --rm \
  --name "$EXECUTION_CONTAINER_NAME" \
  --user node \
  --env "N8N_ENCRYPTION_KEY=$encryption_key" \
  --env "N8N_LOG_LEVEL=silent" \
  --env "N8N_RUNNERS_TASK_TIMEOUT=300" \
  --env "N8N_DIAGNOSTICS_ENABLED=false" \
  --env "N8N_VERSION_NOTIFICATIONS_ENABLED=false" \
  --env "N8N_PERSONALIZATION_ENABLED=false" \
  --env "GENERIC_TIMEZONE=Asia/Shanghai" \
  --env "TZ=Asia/Shanghai" \
  --volume "${data_dir}:/home/node/.n8n" \
  --entrypoint n8n \
  "$N8N_IMAGE" execute --id "$WORKFLOW_ID" --rawOutput \
  > "$execution_json" 2> "$execution_log"
execution_status=$?
set -e

if [[ "$execution_status" -ne 0 ]]; then
  echo "n8n workflow execution failed with exit code $execution_status." >&2
  cp "$execution_json" "$artifact_dir/execution.json"
  cp "$execution_log" "$artifact_dir/execution.log"

  echo "::group::n8n execution diagnostics"
  if jq -e . "$execution_json" >/dev/null 2>&1; then
    jq -r '.. | objects | .message? // empty | select(type == "string")' "$execution_json" | head -n 80 || true
  fi
  if [[ -s "$execution_json" ]]; then
    tail -n 80 "$execution_json" || true
  fi
  if [[ -s "$execution_log" ]]; then
    tail -n 80 "$execution_log" || true
  fi
  echo "::endgroup::"
  exit "$execution_status"
fi

cp "$execution_json" "$artifact_dir/execution.json"
cp "$execution_log" "$artifact_dir/execution.log"

echo "Rendering the dry-run preview."
python3 scripts/render-dry-run.py \
  "$execution_json" \
  "$artifact_dir/report.json" \
  "$artifact_dir/index.html"

echo "RSS dry run completed. The artifact contains the report, normalized items, and raw execution log."
