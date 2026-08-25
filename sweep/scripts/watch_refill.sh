#!/usr/bin/env bash
# Watch the refill of the 18 records lost when the disk ran out.
#
# The first pass reported "finished: 500 of 500" while 18 of those records
# were zero bytes -- written between 23:17 and 23:39, exactly the window the
# disk went from 387M to 33M free. A count of files is not a count of results,
# which is why this watches emptiness rather than the tally.
#
# The disk guard is set at 15G rather than the 10G the main watcher used: 10G
# was too late last time, since a single JVM slot cache can grow past that
# between two checks.
set -uo pipefail
V4=/home/ubuntu/sbomify-eval/v4

empty_now() { find "$V4/meta" -size 0 2>/dev/null | wc -l; }

echo "refilling; $(empty_now) records empty, $(df -h --output=avail / | tail -1 | tr -d ' ') disk free"

while true; do
  sleep 60
  empty=$(empty_now)
  availk=$(df --output=avail / | tail -1 | tr -d ' ')

  if [ "$availk" -lt 15728640 ]; then
    echo "WARNING: under 15G disk free with $empty records still empty"
  fi

  if [ "$empty" -eq 0 ]; then
    echo "REFILLED: all 18 records non-empty, $(df -h --output=avail / | tail -1 | tr -d ' ') disk free"
    exit 0
  fi

  if ! pgrep -f 'run_one_v[4].sh' >/dev/null && ! pgrep -f 'bash orchestrate_v[4].sh' >/dev/null; then
    echo "STOPPED: sweep gone with $empty records still empty"
    exit 1
  fi
done
