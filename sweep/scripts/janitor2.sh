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
SLOT_RUNTIMES=$EVAL_ROOT/slots
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
    # Slot caches hold a full JVM bundle each; drop only their mutable
    # build state, never the toolchain, or the next project refetches 2.7G.
    for c in "$SLOT_RUNTIMES"/*.cache; do
      [ -d "$c" ] || continue
      docker run --rm -v "$c":/c alpine:3 sh -c '"'"'
        rm -rf /c/xdg/sbomify/runtimes/bundle-go-tools-*/.gomodcache \
               /c/xdg/sbomify/runtimes/bundle-jvm-tools-*/repository/.cache 2>/dev/null; exit 0'"'"' >/dev/null 2>&1
    done
    echo "[$(date -u +%H:%M:%S)] now $(free_gb)G free"
  fi
  # Stop only when no evaluation worker of any kind is left. Matching on the
  # xargs driver lines rather than script names: the first janitor exited
  # early because it watched for orchestrate.sh, which the later passes do
  # not use.
  if ! ps -eo args --no-headers | grep -qE '[x]args -P [0-9]+ -n [0-9]+'; then
    sleep 120
    ps -eo args --no-headers | grep -qE '[x]args -P [0-9]+ -n [0-9]+' || { echo "no workers left, janitor exiting"; break; }
  fi
  sleep 45
done
