#!/usr/bin/env bash
# Block until the CI/CD run finishes, then report its conclusion.
set -uo pipefail
run=${1:?run id}
for _ in $(seq 1 60); do
  st=$(gh run view "$run" --json status --jq .status 2>/dev/null)
  [ "$st" = "completed" ] && break
  sleep 30
done
gh run view "$run" --json status,conclusion --jq '"\(.status) \(.conclusion // "-")"'
