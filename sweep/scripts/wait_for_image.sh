#!/usr/bin/env bash
# Wait until master's CI has published an image newer than the one we pinned,
# then print its digest and the version it reports.
#
# Two conditions, not one. The workflow going green is not the same as the
# image being pullable -- the push is a later job, and a manifest can be
# visible before all its layers are. So this waits for the run to finish and
# then for a pull to succeed and report a digest different from the current
# pin, which is the only thing that actually proves a new build is in hand.
set -uo pipefail

CURRENT=sha256:36023aa84e8997b1526ba366b09d6e75aca12d2665a3b0e3647219e700763b10
IMAGE=ghcr.io/sbomify/sbomify-action

for _ in $(seq 1 120); do   # up to ~60 minutes
  status=$(gh run list --repo sbomify/sbomify-action --branch master --limit 5 \
    --json workflowName,status,conclusion \
    --jq '[.[] | select(.workflowName == "CI/CD Pipeline")][0] | "\(.status) \(.conclusion // "-")"' 2>/dev/null || echo "unknown -")

  if [ "$status" = "completed success" ]; then
    docker pull -q "$IMAGE:latest" >/dev/null 2>&1 || true
    digest=$(docker images --digests "$IMAGE" --format '{{.Digest}}' 2>/dev/null | head -1)
    if [ -n "$digest" ] && [ "$digest" != "$CURRENT" ]; then
      version=$(docker run --rm --memory=1g --memory-swap=1g --entrypoint python3 \
        "$IMAGE@$digest" -c 'import sbomify_action as m; print(m.__version__)' 2>/dev/null | tail -1)
      echo "NEW IMAGE $digest ($version)"
      exit 0
    fi
  fi

  case $status in
    "completed failure"|"completed cancelled")
      echo "CI FAILED on master: $status -- no new image"
      exit 1
      ;;
  esac
  sleep 30
done
echo "TIMED OUT waiting for a new image"
exit 1
