#!/usr/bin/env bash
set -uo pipefail
last=0
while true; do
  n=$(grep -c "^[a-zA-Z]" /home/ubuntu/sbomify-eval/validate377.log 2>/dev/null || echo 0)
  n=$((n - 1))
  if ! pgrep -f 'validate_pr377' > /dev/null; then
    echo "VALIDATION COMPLETE: $n/15 projects"
    break
  fi
  if [ "$n" -gt "$last" ]; then
    echo "validated $n/15"
    last=$n
  fi
  sleep 60
done
