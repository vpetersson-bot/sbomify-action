#!/usr/bin/env bash
# Progress of the 189-project rescan against merged master.
set -uo pipefail
last=0
while true; do
  n=$(ls /home/ubuntu/sbomify-eval/v5/meta 2>/dev/null | wc -l)
  done_now=$((n - 311))
  busy=0
  pgrep -f 'clear_and_rerun_failures' > /dev/null && busy=1
  pgrep -f 'run_one_v[5].sh' > /dev/null && busy=1
  if [ "$busy" -eq 0 ]; then
    echo "RESCAN COMPLETE: $done_now/189 re-measured ($n/500 total, $(find /home/ubuntu/sbomify-eval/v5/meta -size 0 | wc -l) empty)"
    break
  fi
  if [ "$done_now" -ge $((last + 30)) ]; then
    echo "rescan $done_now/189 ($(docker ps -q | wc -l) containers, $(df -h /home/ubuntu | awk 'NR==2{print $4}') free)"
    last=$done_now
  fi
  sleep 120
done
