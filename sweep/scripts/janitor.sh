#!/usr/bin/env bash
# Keep the run alive on a disk that the Go module cache will otherwise fill.
#
# The go runtime bundle keeps GOMODCACHE inside itself, and every Go project
# analysed adds its whole module graph to it -- 20 Go repos took it to 8.6G
# and it does not shrink. This drops it (and the Go build cache) whenever
# free space falls below the threshold. Go re-downloads what it needs, so the
# cost is time on the next Go project, not correctness.
#
# A prune can land mid-generation and fail that one project. That is
# acceptable: run_one.sh records the failure, and the final sweep re-runs
# anything without a record.

set -uo pipefail
EVAL_ROOT=/home/ubuntu/sbomify-eval
RUNTIMES=$EVAL_ROOT/cache/xdg/sbomify/runtimes
THRESHOLD_GB=${THRESHOLD_GB:-12}

free_gb() { df -BG --output=avail / | tail -1 | tr -dc '0-9'; }

while true; do
  free=$(free_gb)
  if [ "$free" -lt "$THRESHOLD_GB" ]; then
    echo "[$(date -u +%H:%M:%S)] ${free}G free, pruning module caches"
    # Root-owned (the action runs as root), so delete from a container.
    docker run --rm -v "$RUNTIMES":/r alpine:3 sh -c '
      rm -rf /r/bundle-go-tools-rolling-amd64/.gomodcache \
             /r/bundle-go-tools-rolling-amd64/.gocache \
             /r/bundle-jvm-tools-rolling-amd64/.m2 \
             /r/bundle-jvm-tools-rolling-amd64/.gradle \
             /r/bundle-rust-tools-rolling-amd64/.cargo/registry 2>/dev/null
      exit 0' >/dev/null 2>&1
    echo "[$(date -u +%H:%M:%S)] now $(free_gb)G free"
  fi
  # Stop once the orchestrators are gone and nothing is left to protect.
  pgrep -f orchestrate.sh >/dev/null 2>&1 || pgrep -f run_best.sh >/dev/null 2>&1 || {
    sleep 120
    pgrep -f 'orchestrate.sh|run_best.sh' >/dev/null 2>&1 || { echo "orchestrators gone, janitor exiting"; break; }
  }
  sleep 45
done
