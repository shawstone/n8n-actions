#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-${MODE:-dry-run}}"
N8N_IMAGE="${N8N_IMAGE:-docker.n8n.io/n8nio/n8n:2.47.4}"
CONTAINER_NAME="${CONTAINER_NAME:-n8n-v2}"
WORKFLOW_ID="${WORKFLOW_ID:-v2NewsAggregate1}"
BOOTSTRAP_WORKFLOW_ID="${BOOTSTRAP_WORKFLOW_ID:-v2DataTableBoot1}"
N8N_BASE_URL="${N8N_BASE_URL:-http://127.0.0.1:5678}"
N8N_OWNER_EMAIL='v2-owner@example.invalid'
N8N_OWNER_PASSWORD='n8n-runner-internal-pass-V2'
N8N_OWNER_PASSWORD_HASH='$2a$10$rX/19l/w0ScsHGaNcHJzK.o22qbzs9CocJJ51Xs3rZRG0Y6S/1Vsy'
STATE_DIR="${STATE_DIR:-${GITHUB_WORKSPACE:-$PWD}/.n8n-state}"
DATA_DIR="${STATE_DIR}/data"
DATA_TABLE_ID_FILE="${STATE_DIR}/data-table-id"
RUNTIME_DIR="${RUNNER_TEMP:-/tmp}/n8n-v2-${MODE}"
ARTIFACT_DIR="${GITHUB_WORKSPACE:-$PWD}/artifacts/n8n-v2"

RUNTIME_WORKFLOW="${RUNTIME_DIR}/workflow.json"
BOOTSTRAP_WORKFLOW="${RUNTIME_DIR}/bootstrap-datatable.json"
BOOTSTRAP_OUTPUT="${RUNTIME_DIR}/bootstrap-output.json"
EXECUTION_OUTPUT="${RUNTIME_DIR}/execution-output.json"
CREDENTIALS_JSON="${RUNTIME_DIR}/credentials.json"
BITABLE_LOG="${ARTIFACT_DIR}/feishu-bitable.log"

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
  if [[ -d "$STATE_DIR" ]]; then
    sudo chown --recursive "$(id -u):$(id -g)" "$STATE_DIR" || true
  fi
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
  local logs
  for attempt in $(seq 1 120); do
    logs="$(docker logs "$CONTAINER_NAME" 2>&1 || true)"
    if grep -Fq "Editor is now accessible via:" <<<"$logs"; then
      echo "n8n startup and database migrations completed after $((attempt * 2)) seconds."
      return 0
    fi
    if ! docker inspect --format '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null | grep -q true; then
      echo "n8n container stopped before becoming healthy." >&2
      return 1
    fi
    sleep 2
  done
  echo "n8n did not finish startup within 240 seconds." >&2
  return 1
}

start_n8n() {
  docker run --detach \
    --name "$CONTAINER_NAME" \
    --publish 5678:5678 \
    --env "N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}" \
    --env "N8N_INSTANCE_OWNER_MANAGED_BY_ENV=true" \
    --env "N8N_INSTANCE_OWNER_EMAIL=${N8N_OWNER_EMAIL}" \
    --env "N8N_INSTANCE_OWNER_FIRST_NAME=V2" \
    --env "N8N_INSTANCE_OWNER_LAST_NAME=Owner" \
    --env "N8N_INSTANCE_OWNER_PASSWORD_HASH=${N8N_OWNER_PASSWORD_HASH}" \
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
}

invoke_workflow() {
  local workflow_id=$1
  local trigger_name=$2
  local output_path=$3
  local timeout_seconds=$4
  python3 scripts/invoke_n8n_workflow.py \
    --base-url "$N8N_BASE_URL" \
    --email "$N8N_OWNER_EMAIL" \
    --password "$N8N_OWNER_PASSWORD" \
    --workflow-id "$workflow_id" \
    --trigger-name "$trigger_name" \
    --timeout "$timeout_seconds" \
    --output "$output_path"
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

if [[ "$MODE" != "dry-run" && "$MODE" != "publish" && "$MODE" != "diagnostic" ]]; then
  echo "Mode must be dry-run, publish, or diagnostic, got: $MODE" >&2
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

  echo "Creating the Data Table through the running n8n REST API."
  invoke_workflow \
    "$BOOTSTRAP_WORKFLOW_ID" \
    "Execute Workflow Trigger" \
    "$BOOTSTRAP_OUTPUT" \
    120

  python3 scripts/extract_data_table_id.py "$BOOTSTRAP_OUTPUT" >"$DATA_TABLE_ID_FILE"
  chmod 600 "$DATA_TABLE_ID_FILE"
  echo "Created persistent Data Table ID: $(cat "$DATA_TABLE_ID_FILE")"
else
  echo "Reusing persistent Data Table ID from cache."
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
  ]' >"$CREDENTIALS_JSON"

docker cp "$CREDENTIALS_JSON" "${CONTAINER_NAME}:/tmp/runtime-credentials.json"
docker cp "$RUNTIME_WORKFLOW" "${CONTAINER_NAME}:/tmp/runtime-workflow.json"
docker exec --user node "$CONTAINER_NAME" \
  n8n import:credentials --input=/tmp/runtime-credentials.json
docker exec --user node "$CONTAINER_NAME" \
  n8n import:workflow --input=/tmp/runtime-workflow.json

echo "Executing workflow ${WORKFLOW_ID} in ${MODE} mode through the REST API."
set +e
invoke_workflow \
  "$WORKFLOW_ID" \
  "Schedule Trigger" \
  "$EXECUTION_OUTPUT" \
  1800
execution_status=$?
set -e

redact_secret_file "$BOOTSTRAP_OUTPUT" "${FEISHU_WEBHOOK_URL:-}"
redact_secret_file "$EXECUTION_OUTPUT" "${FEISHU_WEBHOOK_URL:-}"

if [[ "$execution_status" -ne 0 ]]; then
  echo "n8n workflow execution failed with exit code $execution_status." >&2
  exit "$execution_status"
fi

python3 scripts/render-run-summary.py \
  "$EXECUTION_OUTPUT" \
  "$ARTIFACT_DIR/run-summary.json"

if [[ "$MODE" == "publish" ]]; then
  require_value FEISHU_APP_ID
  require_value FEISHU_APP_SECRET
  require_value FEISHU_BITABLE_APP_TOKEN
  require_value FEISHU_BITABLE_TABLE_ID

  set +e
  python3 scripts/publish_feishu_bitable.py \
    --summary "$ARTIFACT_DIR/run-summary.json" \
    --config config/feishu-bitable.json \
    --app-id "$FEISHU_APP_ID" \
    --app-secret "$FEISHU_APP_SECRET" \
    --app-token "$FEISHU_BITABLE_APP_TOKEN" \
    --table-id "$FEISHU_BITABLE_TABLE_ID" \
    --output "$ARTIFACT_DIR/feishu-bitable.json" \
    >"$BITABLE_LOG" 2>&1
  bitable_status=$?
  set -e
  cat "$BITABLE_LOG"
  if [[ "$bitable_status" -ne 0 ]]; then
    echo "::warning::Feishu Bitable write failed; group push and Pages deployment will continue."
  fi
fi

echo "Workflow execution completed successfully."
