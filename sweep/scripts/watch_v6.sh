#!/usr/bin/env bash
# Emit progress for the v6 replay, and stop on every terminal state.
#
# Deliberately covers failure as well as success: a monitor that only watched
# for "200 records" would stay silent through an orchestrator crash or a full
# disk, and silence reads exactly like "still running".
set -uo pipefail
META=${META:-${OUT_ROOT:-$HOME/sbomify-eval/v6}/meta}
prev=0
while true; do
  n=$(find "$META" -name '*.json' -size +0 2>/dev/null | wc -l)
  if [ "$n" -ge 200 ]; then echo "SWEEP COMPLETE: $n/200 records"; break; fi
  if ! pgrep -f orchestrate_replay.sh >/dev/null 2>&1; then
    echo "SWEEP STOPPED EARLY: $n/200 records, orchestrator gone"; break
  fi
  avail=$(df -BG --output=avail "$META" | tail -1 | tr -dc '0-9')
  if [ "${avail:-99}" -lt 15 ]; then echo "DISK LOW: ${avail}G free at $n/200"; break; fi
  if [ "$n" -ge $((prev + 40)) ]; then echo "progress: $n/200 records"; prev=$n; fi
  sleep 60
done
