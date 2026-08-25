#!/usr/bin/env bash
# Watch the 500-project sweep and emit only the lines worth acting on.
#
# Written so silence cannot be mistaken for health, which is the trap the
# previous restart fell into: six live processes, no records, and a claim loop
# that would have waited 80 minutes before admitting it was stuck. Every
# terminal state emits -- finished, orchestrator gone, no progress for 40
# minutes, the disk filling, or a kernel OOM kill outside the eval cgroups.
set -uo pipefail
V4=/home/ubuntu/sbomify-eval/v4
TOTAL=500
STEP=25

count() { ls "$V4/meta" 2>/dev/null | wc -l; }

start=$(count)
last=$start
mark=$(( (start / STEP) * STEP ))
stalled=0
echo "watching from $start/$TOTAL"

while true; do
  sleep 60
  n=$(count)

  if [ "$n" -ge $((mark + STEP)) ]; then
    mark=$(( (n / STEP) * STEP ))
    avail=$(free -g | awk '/^Mem:/ {print $7}')
    disk=$(df -h --output=avail / | tail -1 | tr -d ' ')
    echo "progress: $n/$TOTAL records, ${avail}G RAM free, $disk disk free"
  fi

  # 33 GB went on slot caches last time. The sweep is worth more than the
  # margin, but not more than the machine.
  availk=$(df --output=avail / | tail -1 | tr -d ' ')
  if [ "$availk" -lt 10485760 ]; then
    echo "WARNING: under 10G disk free at $n/$TOTAL"
  fi

  if [ "$n" -ge "$TOTAL" ]; then
    echo "FINISHED: $n/$TOTAL"
    exit 0
  fi

  if ! pgrep -f 'bash orchestrate_v[4].sh' >/dev/null \
     && ! pgrep -f 'run_one_v[4].sh' >/dev/null; then
    echo "STOPPED: orchestrator and workers both gone at $n/$TOTAL"
    exit 1
  fi

  if [ "$n" -eq "$last" ]; then
    stalled=$((stalled + 1))
    # A JVM monorepo can legitimately hold a worker a long time; the run
    # timeout is 35 minutes per attempt and strict+fallback is two of them.
    if [ "$stalled" -ge 80 ]; then
      echo "STALLED: no new record in 80 minutes at $n/$TOTAL"
      stalled=0
    fi
  else
    stalled=0
    last=$n
  fi
done
