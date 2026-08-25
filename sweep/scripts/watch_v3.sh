#!/usr/bin/env bash
# Watch the v3 sweep and emit only the lines worth acting on.
#
# Written so that silence cannot be mistaken for health, which is the trap the
# first restart fell into: six live processes, no records, and a claim loop
# that would have waited 80 minutes before admitting it was stuck. Every
# terminal state emits -- finished, orchestrator gone, no progress for 25
# minutes, or the kernel OOM killer firing again.
set -uo pipefail
V3=/home/ubuntu/sbomify-eval/v3
TOTAL=249
STEP=10

count() { ls "$V3/meta" 2>/dev/null | wc -l; }

start=$(count)
last=$start
mark=$(( (start / STEP) * STEP ))
stalled=0
echo "watching from $start/$TOTAL"

while true; do
  sleep 60
  n=$(count)

  # Progress, but only on each multiple of STEP so this stays quiet.
  if [ "$n" -ge $((mark + STEP)) ]; then
    mark=$(( (n / STEP) * STEP ))
    avail=$(free -g | awk '/^Mem:/ {print $7}')
    echo "progress: $n/$TOTAL records, ${avail}G RAM available"
  fi

  # The kernel taking a container is expected under the cap and is recorded as
  # rc 137; the kernel taking anything outside the eval tree is not.
  if sudo dmesg -T --level=err,crit,alert,emerg 2>/dev/null | tail -40 \
       | grep -qi "Out of memory: Killed process"; then
    if ! sudo dmesg -T 2>/dev/null | tail -3 | grep -q "$(date +%H:%M)"; then :; else
      echo "WARNING: kernel OOM kill just fired -- check what died"
    fi
  fi

  if [ "$n" -ge "$TOTAL" ]; then
    echo "FINISHED: $n/$TOTAL"
    exit 0
  fi

  if ! pgrep -f 'bash orchestrate_v[3].sh' >/dev/null; then
    if ! pgrep -f 'run_one_v[3].sh' >/dev/null; then
      echo "STOPPED: orchestrator and workers both gone at $n/$TOTAL"
      exit 1
    fi
  fi

  if [ "$n" -eq "$last" ]; then
    stalled=$((stalled + 1))
    # A single JVM monorepo can legitimately hold a worker for a while; the
    # run timeout is 35 minutes, so only complain past that.
    if [ "$stalled" -ge 40 ]; then
      echo "STALLED: no new record in 40 minutes at $n/$TOTAL"
      stalled=0
    fi
  else
    stalled=0
    last=$n
  fi
done
