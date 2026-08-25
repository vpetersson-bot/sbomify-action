#!/usr/bin/env bash
# Progress of the 101-project failure re-run, and nothing else.
set -uo pipefail
last=0
while true; do
  n=$(ls /home/ubuntu/sbomify-eval/v5/meta 2>/dev/null | wc -l)
  done_now=$((n - 399))
  if ! pgrep -f 'clear_and_rerun_failures' > /dev/null && ! pgrep -f 'run_one_v[5].sh' > /dev/null; then
    echo "RERUN COMPLETE: $done_now/101 re-measured ($n/500 total)"
    break
  fi
  if [ "$done_now" -ge $((last + 20)) ]; then
    echo "rerun progress $done_now/101 ($(docker ps -q | wc -l) running, $(df -h /home/ubuntu | awk 'NR==2{print $4}') free)"
    last=$done_now
  fi
  sleep 120
done
