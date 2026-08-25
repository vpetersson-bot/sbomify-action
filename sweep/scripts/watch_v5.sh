#!/usr/bin/env bash
# Watch the 500-project sweep. Emits only what is worth acting on.
#
# Written so silence cannot be mistaken for health. Every terminal state
# emits -- finished, orchestrator gone, no progress for 80 minutes, the disk
# filling, or an ecosystem lock stuck long enough to be dropping projects.
#
# Zero-byte records are counted directly rather than inferred: the v4 run
# reported "finished: 500 of 500" with 18 of them empty, written in the 22
# minutes it spent under 400MB free. A count of files is not a count of
# results.
set -uo pipefail
V5=/home/ubuntu/sbomify-eval/v5
TOTAL=500
STEP=25

count() { ls "$V5/meta" 2>/dev/null | wc -l; }
empty() { find "$V5/meta" -size 0 2>/dev/null | wc -l; }
ecolocks() { find "$V5/eco" -maxdepth 1 -name '*.lock' -type d 2>/dev/null | wc -l; }

start=$(count)
last=$start
mark=$(( (start / STEP) * STEP ))
stalled=0
echo "watching from $start/$TOTAL, $(df -h --output=avail / | tail -1 | tr -d ' ') disk free"

while true; do
  sleep 60
  n=$(count)
  availk=$(df --output=avail / | tail -1 | tr -d ' ')

  if [ "$n" -ge $((mark + STEP)) ]; then
    mark=$(( (n / STEP) * STEP ))
    echo "progress: $n/$TOTAL ($(empty) empty), $(free -g | awk '/^Mem:/ {print $7}')G RAM, $(df -h --output=avail / | tail -1 | tr -d ' ') disk, $(ecolocks) ecosystems busy"
  fi

  if [ "$availk" -lt 20971520 ]; then
    echo "WARNING: under 20G disk free at $n/$TOTAL -- reclaim slot caches before records start truncating"
  fi

  # More ecosystem locks held than workers means one is stale, and a stale
  # ecosystem lock silently drops every remaining project in that ecosystem.
  if [ "$(ecolocks)" -gt 3 ]; then
    echo "WARNING: $(ecolocks) ecosystem locks held with 3 workers -- one is stale"
  fi

  if [ "$n" -ge "$TOTAL" ]; then
    echo "FINISHED: $n/$TOTAL, $(empty) zero-byte records"
    exit 0
  fi

  if ! pgrep -f 'bash orchestrate_v[5].sh' >/dev/null && ! pgrep -f 'run_one_v[5].sh' >/dev/null; then
    echo "STOPPED: orchestrator and workers both gone at $n/$TOTAL"
    exit 1
  fi

  if [ "$n" -eq "$last" ]; then
    stalled=$((stalled + 1))
    if [ "$stalled" -ge 80 ]; then
      echo "STALLED: no new record in 80 minutes at $n/$TOTAL"
      stalled=0
    fi
  else
    stalled=0
    last=$n
  fi
done
