#!/usr/bin/env bash
set -Eeuo pipefail

N8N_IMAGE="${N8N_IMAGE:-docker.n8n.io/n8nio/n8n:2.47.4}"
CONTAINER_NAME="${CONTAINER_NAME:-n8n-phase1}"
WORKFLOW_ID="${WORKFLOW_ID:-SDbEpCrT1vf0m3gr}"
EXPECTED_WORKFLOW_SHA256="${EXPECTED_WORKFLOW_SHA256:-492A6C99A7AF6AC71D8AD45017DB4FF1D907881672D323DC7D521B17BB4F28EF}"
EXECUTE_WORKFLOW="${EXECUTE_WORKFLOW:-false}"

run_root="${RUNNER_TEMP:-/tmp}/n8n-phase1"
data_dir="${run_root}/data"
workflow_json="${run_root}/workflow.json"
exported_workflow="${run_root}/imported-workflow.json"
credentials_json="${run_root}/credentials.json"

mkdir -p "$data_dir"
sudo chown --recursive 1000:1000 "$data_dir"

cleanup() {
  local exit_code=$?
  if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    echo "::group::n8n container logs"
    docker logs --tail 500 "$CONTAINER_NAME" || true
    echo "::endgroup::"
    docker rm --force "$CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
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

wait_for_community_package() {
  local attempt
  local logs
  for attempt in $(seq 1 120); do
    logs="$(docker logs "$CONTAINER_NAME" 2>&1 || true)"

    if grep -Fq "Failed to install community package" <<< "$logs"; then
      grep -F "Failed to install community package" <<< "$logs" >&2
      return 1
    fi

    if grep -Fq "Installed community package" <<< "$logs"; then
      echo "Feishu community package installation completed after $((attempt * 2)) seconds."
      return 0
    fi

    sleep 2
  done

  echo "Feishu community package did not finish installing within 240 seconds." >&2
  return 1
}

echo "Restoring the original workflow JSON from the compressed repository copy."
base64 --decode n8n/workflow.json.gz.b64 | gzip --decompress > "$workflow_json"

actual_sha256="$(sha256sum "$workflow_json" | awk '{print toupper($1)}')"
if [[ "$actual_sha256" != "$EXPECTED_WORKFLOW_SHA256" ]]; then
  echo "Workflow checksum mismatch: expected $EXPECTED_WORKFLOW_SHA256, got $actual_sha256" >&2
  exit 1
fi

jq -e --arg id "$WORKFLOW_ID" '.id == $id and (.nodes | length) == 87' "$workflow_json" >/dev/null
echo "Workflow JSON verified: ID=$WORKFLOW_ID, nodes=87, SHA-256=$actual_sha256"

community_packages='[{"name":"@songlipeng2003/n8n-nodes-feishu-lite","version":"0.4.7"}]'
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
  --env "N8N_COMMUNITY_PACKAGES_MANAGED_BY_ENV=true" \
  --env "N8N_COMMUNITY_PACKAGES=$community_packages" \
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
wait_for_community_package

echo "Importing the original workflow."
docker cp "$workflow_json" "${CONTAINER_NAME}:/tmp/workflow.json"
docker exec --user node "$CONTAINER_NAME" n8n import:workflow --input=/tmp/workflow.json

echo "Exporting the imported workflow for verification."
docker exec --user node "$CONTAINER_NAME" n8n export:workflow --id="$WORKFLOW_ID" --output=/tmp/imported-workflow.json
docker cp "${CONTAINER_NAME}:/tmp/imported-workflow.json" "$exported_workflow"

jq -e --arg id "$WORKFLOW_ID" '
  (if type == "array" then .[0] else . end) as $workflow |
  $workflow.id == $id and
  $workflow.name == "n8n信息聚合器" and
  ($workflow.nodes | length) == 87
' "$exported_workflow" >/dev/null
echo "Import verification passed: workflow ID, name, and 87-node count all match."

if [[ "$EXECUTE_WORKFLOW" != "true" ]]; then
  echo "Execution was not requested. Phase 1 import verification is complete."
  echo "No scheduled or external workflow was started in this run."
  exit 0
fi

if [[ -z "${N8N_CREDENTIALS_JSON:-}" ]]; then
  echo "Execution requested, but the N8N_CREDENTIALS_JSON secret is missing." >&2
  exit 2
fi

printf '%s' "$N8N_CREDENTIALS_JSON" > "$credentials_json"
jq -e 'type == "array" and length > 0' "$credentials_json" >/dev/null

echo "Importing credentials supplied through GitHub Secrets."
docker cp "$credentials_json" "${CONTAINER_NAME}:/tmp/credentials.json"
docker exec --user node "$CONTAINER_NAME" n8n import:credentials --input=/tmp/credentials.json

echo "Executing the imported workflow by its original ID."
docker exec --user node "$CONTAINER_NAME" n8n execute --id "$WORKFLOW_ID"
echo "Workflow execution completed successfully."
