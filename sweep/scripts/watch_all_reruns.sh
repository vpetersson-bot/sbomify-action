#!/usr/bin/env bash
# One line per milestone until every re-run stage is finished.
set -uo pipefail
last=0
while true; do
  n=$(ls /home/ubuntu/sbomify-eval/v5/meta 2>/dev/null | wc -l)
  busy=0
  pgrep -f 'queue_noinput_rerun' > /dev/null && busy=1
  pgrep -f 'finish_reruns' > /dev/null && busy=1
  pgrep -f 'run_one_v[5].sh' > /dev/null && busy=1
  if [ "$busy" -eq 0 ]; then
    echo "ALL RERUNS COMPLETE: $n/500 records, $(find /home/ubuntu/sbomify-eval/v5/meta -size 0 | wc -l) empty"
    break
  fi
  if [ "$n" -ge $((last + 25)) ] || [ "$last" -eq 0 ]; then
    echo "records $n/500 ($(docker ps -q | wc -l) running, $(df -h /home/ubuntu | awk 'NR==2{print $4}') free)"
    last=$n
  fi
  sleep 120
done
