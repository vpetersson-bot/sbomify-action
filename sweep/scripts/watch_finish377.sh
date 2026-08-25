#!/usr/bin/env bash
set -uo pipefail
while pgrep -f 'finish_reruns' > /dev/null || pgrep -f 'run_one_v[5].sh' > /dev/null; do sleep 90; done
echo "COMPLETE: $(ls /home/ubuntu/sbomify-eval/v5/meta | wc -l)/500 records, $(find /home/ubuntu/sbomify-eval/v5/meta -size 0 | wc -l) empty"
