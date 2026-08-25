#!/usr/bin/env bash
# Emit one line per meaningful change in the sweep, and nothing otherwise.
#
# Watches for the three ways this run has actually gone wrong before, not just
# for success: the orchestrator dying (which looked identical to "still
# working" for 64 minutes), zero-byte records written under a full disk, and
# the disk filling in the first place. Silence here means healthy.
set -uo pipefail
ROOT=/home/ubuntu/sbomify-eval/v5
last=0
while true; do
  n=$(ls "$ROOT/meta" 2>/dev/null | wc -l)
  empty=$(find "$ROOT/meta" -size 0 2>/dev/null | wc -l)
  availg=$(($(df --output=avail /home/ubuntu | tail -1 | tr -d ' ') / 1048576))
  orch=$(pgrep -cf 'bash orchestrate_v[5].sh')

  if [ "$orch" -eq 0 ]; then
    echo "STOPPED: orchestrator gone at $n/500 (empty=$empty, ${availg}G free)"
    break
  fi
  [ "$availg" -lt 25 ] && echo "DISK LOW: ${availg}G free at $n/500"
  [ "$empty" -gt 0 ] && echo "EMPTY RECORDS: $empty at $n/500"

  if [ "$n" -ge $((last + 25)) ]; then
    echo "progress $n/500 (${availg}G free, $(docker ps -q | wc -l) running)"
    last=$n
  fi
  if [ "$n" -ge 500 ]; then
    echo "COMPLETE: $n/500 (empty=$empty)"
    break
  fi
  sleep 120
done
