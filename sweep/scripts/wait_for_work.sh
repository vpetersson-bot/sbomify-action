#!/usr/bin/env bash
# Wait until the sweep is genuinely doing work, not merely running.
#
# Three live worker processes told us nothing: they had been sleeping in a
# retry loop for 49 minutes waiting on slot locks that no longer had an owner.
# A container actually running is the first honest sign of progress.
set -uo pipefail
until [ "$(docker ps -q | wc -l)" -gt 0 ]; do
  sleep 5
done
echo "containers running: $(docker ps -q | wc -l)"
echo "clones on disk: $(du -sh /home/ubuntu/sbomify-eval/v5/repos 2>/dev/null | cut -f1)"
echo "slot locks held: $(find /home/ubuntu/sbomify-eval/v5/slots -maxdepth 1 -name '*.lock' -type d 2>/dev/null | wc -l)"
