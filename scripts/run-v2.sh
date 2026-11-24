#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-${MODE:-dry-run}}"
N8N_IMAGE="${N8N_IMAGE:-docker.n8n.io/n8nio/n8n:2.47.4}"
CONTAINER_NAME="${CONTAINER_NAME:-n8n-v2}"
EXECUTION_CONTAINER_NAME="${EXECUTION_CONTAINER_NAME:-n8n-v2-execute}"
BOOTSTRAP_CONTAINER_NAME="${BOOTSTRAP_CONTAINER_NAME:-n8n-v2-bootstrap}"
WORKFLOW_ID="${WORKFLOW_ID:-v2NewsAggregate1}"
BOOTSTRAP_WORKFLOW_ID="${BOOTSTRAP_WORKFLOW_ID:-v2DataTableBoot1}"
STATE_DIR="${STATE_DIR:-${GITHUB_WORKSPACE:-$PWD}/.n8n-state}"
DATA_DIR="${STATE_DIR}/data"
DATA_TABLE_ID_FILE="${STATE_DIR}/data-table-id"
RUNTIME_DIR="${RUNNER_TEMP:-/tmp}/n8n-v2-${MODE}"
ARTIFACT_DIR="${GITHUB_WORKSPACE:-$PWD}/artifacts/n8n-v2"

RUNTIME_WORKFLOW="${RUNTIME_DIR}/workflow.json"
BOOTSTRAP_WORKFLOW="${RUNTIME_DIR}/bootstrap-datatable.json"
BOOTSTRAP_OUTPUT="${RUNTIME_DIR}/bootstrap-output.json"
EXECUTION_OUTPUT="${RUNTIME_DIR}/execution-output.json"
EXECUTION_LOG="${RUNTIME_DIR}/execution.log"
CREDENTIALS_JSON="${RUNTIME_DIR}/credentials.json"

mkdir -p "$DATA_DIR" "$RUNTIME_DIR" "$ARTIFACT_DIR"
sudo chown --recursive 1000:1000 "$DATA_DIR"

cleanup() {
  local exit_code=$?
  if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    echo "::group::n8n container logs"
    docker logs --tail 250 "$CONTAINER_NAME" 2>&1 || true
    echo "::endgroup::"
    docker rm --force "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
  docker rm --force "$EXECUTION_CONTAINER_NAME" >/dev/null 2>&1 || true
  docker rm --force "$BOOTSTRAP_CONTAINER_NAME" >/dev/null 2>&1 || true
  exit "$exit_code"
}
trap cleanup EXIT

require_value() {
  local name=$1
  if [[ -z "${!name:-}" ]]; then
    echo "Required GitHub Actions secret is missing: $name" >&2
    exit 2
  fi
}

wait_for_n8n() {
  local attempt
  for attempt in $(seq 1 120); do
    if curl --fail --silent --show-error http://127.0.0.1:5678/healthz >/dev/null; then
      echo "n8n is healthy after $((attempt * 2)) seconds."
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

wait_for_community_package() {
  local attempt
  local logs
  for attempt in $(seq 1 120); do
    logs="$(docker logs "$CONTAINER_NAME" 2>&1 || true)"
    if grep -Fq "Failed to install community package" <<<"$logs"; then
      grep -F "Failed to install community package" <<<"$logs" >&2
      return 1
    fi
    if grep -Fq "Installed community package" <<<"$logs"; then
      echo "Feishu community package is ready after $((attempt * 2)) seconds."
      return 0
    fi
    sleep 2
  done
  echo "Feishu community package did not finish installing within 240 seconds." >&2
  return 1
}

start_n8n() {
  local community_packages
  community_packages='[{"name":"@songlipeng2003/n8n-nodes-feishu-lite","version":"0.4.7"}]'

  docker run --detach \
    --name "$CONTAINER_NAME" \
    --publish 5678:5678 \
    --env "N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}" \
    --env "N8N_INSTANCE_OWNER_MANAGED_BY_ENV=true" \
    --env "N8N_INSTANCE_OWNER_EMAIL=v2-owner@example.invalid" \
    --env "N8N_INSTANCE_OWNER_FIRST_NAME=V2" \
    --env "N8N_INSTANCE_OWNER_LAST_NAME=Owner" \
    --env 'N8N_INSTANCE_OWNER_PASSWORD_HASH=$2b$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy' \
    --env "N8N_COMMUNITY_PACKAGES_MANAGED_BY_ENV=true" \
    --env "N8N_COMMUNITY_PACKAGES=${community_packages}" \
    --env "N8N_UNVERIFIED_PACKAGES_ENABLED=true" \
    --env "N8N_RUNNERS_TASK_TIMEOUT=600" \
    --env "N8N_DIAGNOSTICS_ENABLED=false" \
    --env "N8N_VERSION_NOTIFICATIONS_ENABLED=false" \
    --env "N8N_PERSONALIZATION_ENABLED=false" \
    --env "N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true" \
    --env "N8N_LOG_LEVEL=info" \
    --env "GENERIC_TIMEZONE=Asia/Shanghai" \
    --env "TZ=Asia/Shanghai" \
    --volume "${DATA_DIR}:/home/node/.n8n" \
    "$N8N_IMAGE" >/dev/null

  wait_for_n8n
  wait_for_community_package
}

run_cli() {
  local container_name=$1
  shift
  docker run --rm \
    --name "$container_name" \
    --user node \
    --env "N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}" \
    --env "N8N_RUNNERS_TASK_TIMEOUT=600" \
    --env "N8N_DIAGNOSTICS_ENABLED=false" \
    --env "N8N_VERSION_NOTIFICATIONS_ENABLED=false" \
    --env "N8N_PERSONALIZATION_ENABLED=false" \
    --env "GENERIC_TIMEZONE=Asia/Shanghai" \
    --env "TZ=Asia/Shanghai" \
    --volume "${DATA_DIR}:/home/node/.n8n" \
    --volume "${RUNTIME_DIR}:/tmp/v2-runtime" \
    --entrypoint n8n \
    "$N8N_IMAGE" "$@"
}

redact_secret_file() {
  local path=$1
  local secret=$2
  if [[ -f "$path" && -n "$secret" ]]; then
    python3 - "$path" "$secret" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
secret = sys.argv[2]
path.write_text(path.read_text(encoding="utf-8", errors="replace").replace(secret, "[REDACTED]"), encoding="utf-8")
PY
  fi
}

require_value N8N_ENCRYPTION_KEY
require_value DEEPSEEK_API_KEY

if [[ "$MODE" != "dry-run" && "$MODE" != "publish" ]]; then
  echo "Mode must be dry-run or publish, got: $MODE" >&2
  exit 64
fi

echo "Preparing the persistent n8n state directory."
start_n8n

if [[ ! -s "$DATA_TABLE_ID_FILE" ]]; then
  echo "First run: importing the Data Table bootstrap workflow."
  cp n8n/bootstrap-datatable.json "$BOOTSTRAP_WORKFLOW"
  docker cp "$BOOTSTRAP_WORKFLOW" "${CONTAINER_NAME}:/tmp/bootstrap-datatable.json"
  docker exec --user node "$CONTAINER_NAME" \
    n8n import:workflow --input=/tmp/bootstrap-datatable.json

  echo "Stopping n8n before isolated bootstrap execution."
  docker stop "$CONTAINER_NAME" >/dev/null

  set +e
  run_cli "$BOOTSTRAP_CONTAINER_NAME" \
    execute --id "$BOOTSTRAP_WORKFLOW_ID" --rawOutput \
    >"$BOOTSTRAP_OUTPUT" 2>"${BOOTSTRAP_OUTPUT}.log"
  bootstrap_status=$?
  set -e

  if [[ "$bootstrap_status" -ne 0 ]]; then
    echo "Data Table bootstrap execution failed." >&2
    tail -n 100 "${BOOTSTRAP_OUTPUT}.log" || true
    exit "$bootstrap_status"
  fi

  python3 scripts/extract_data_table_id.py "$BOOTSTRAP_OUTPUT" >"$DATA_TABLE_ID_FILE"
  chmod 600 "$DATA_TABLE_ID_FILE"
  echo "Created persistent Data Table ID: $(cat "$DATA_TABLE_ID_FILE")"
else
  echo "Reusing persistent Data Table ID from cache."
  docker stop "$CONTAINER_NAME" >/dev/null
fi

export DATA_TABLE_ID
DATA_TABLE_ID="$(cat "$DATA_TABLE_ID_FILE")"
export DATA_TABLE_ID

echo "Rendering the runtime workflow and credentials."
python3 scripts/prepare_workflow.py \
  --template n8n/workflow.template.json \
  --config-dir config \
  --output "$RUNTIME_WORKFLOW" \
  --mode "$MODE"

jq -n \
  --arg deepseek "$DEEPSEEK_API_KEY" \
  --arg feishu_app_id "${FEISHU_APP_ID:-}" \
  --arg feishu_app_secret "${FEISHU_APP_SECRET:-}" \
  '[
    {
      "id": "xvaefodMzAZCsD3v",
      "name": "DeepSeek account",
      "type": "deepSeekApi",
      "data": {
        "apiKey": $deepseek,
        "url": "https://api.deepseek.com"
      }
    }
  ] + if ($feishu_app_id | length) > 0 and ($feishu_app_secret | length) > 0 then [
    {
      "id": "v2FeishuCred0001",
      "name": "Feishu Credentials account",
      "type": "feishuCredentialsApi",
      "data": {
        "appId": $feishu_app_id,
        "appSecret": $feishu_app_secret
      }
    }
  ] else [] end' >"$CREDENTIALS_JSON"

run_cli "${EXECUTION_CONTAINER_NAME}-credentials" \
  import:credentials --input=/tmp/v2-runtime/credentials.json
run_cli "${EXECUTION_CONTAINER_NAME}-workflow" \
  import:workflow --input=/tmp/v2-runtime/workflow.json

echo "Executing workflow ${WORKFLOW_ID} in ${MODE} mode."
set +e
run_cli "$EXECUTION_CONTAINER_NAME" \
  execute --id "$WORKFLOW_ID" --rawOutput \
  >"$EXECUTION_OUTPUT" 2>"$EXECUTION_LOG"
execution_status=$?
set -e

redact_secret_file "$BOOTSTRAP_OUTPUT" "${FEISHU_WEBHOOK_URL:-}"
redact_secret_file "${BOOTSTRAP_OUTPUT}.log" "${FEISHU_WEBHOOK_URL:-}"
redact_secret_file "$EXECUTION_OUTPUT" "${FEISHU_WEBHOOK_URL:-}"
redact_secret_file "$EXECUTION_LOG" "${FEISHU_WEBHOOK_URL:-}"

if [[ "$execution_status" -ne 0 ]]; then
  echo "n8n workflow execution failed with exit code $execution_status." >&2
  tail -n 120 "$EXECUTION_LOG" || true
  exit "$execution_status"
fi

python3 scripts/render-run-summary.py \
  "$EXECUTION_OUTPUT" \
  "$ARTIFACT_DIR/run-summary.json"

echo "Workflow execution completed successfully."
