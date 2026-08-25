#!/usr/bin/env bash
# Wait for the 17-project re-run, then say so once.
set -uo pipefail
while pgrep -f 'run_one_v[5].sh' > /dev/null; do sleep 60; done
echo "rerun finished: $(ls /home/ubuntu/sbomify-eval/v5/meta | wc -l)/500 records, $(find /home/ubuntu/sbomify-eval/v5/meta -size 0 | wc -l) empty"
