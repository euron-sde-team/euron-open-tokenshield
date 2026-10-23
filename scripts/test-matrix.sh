#!/usr/bin/env bash
# Run the API integration suite under every backend combination the app supports:
#
#   keys:    local AES-GCM master key | AWS KMS (Floci)
#   storage: local disk               | Amazon S3 (Floci)
#
# Needs the local stack (make up): Floci with the local-floci Terraform applied.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FLOCI_URL="http://localhost:${TS_FLOCI_PORT:-4166}"

if ! curl -sf -o /dev/null "$FLOCI_URL/"; then
  echo "Floci is not reachable at $FLOCI_URL. Start the stack first: make up" >&2
  exit 1
fi
"$ROOT/scripts/test-db.sh"

export AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_REGION=us-east-1
export TEST_AWS_ENDPOINT="$FLOCI_URL"
failed=()
for keys in local kms; do
  for storage in local s3; do
    echo
    echo "== keys=$keys storage=$storage"
    if ! (cd "$ROOT/apps/api" && TEST_KEY_MODE=$keys TEST_STORAGE=$storage \
          uv run pytest tests/integration -q -p no:warnings); then
      failed+=("keys=$keys storage=$storage")
    fi
  done
done
echo
if ((${#failed[@]})); then
  printf 'matrix: FAILED for %s\n' "${failed[@]}"
  exit 1
fi
echo "matrix: all 4 combinations passed"
