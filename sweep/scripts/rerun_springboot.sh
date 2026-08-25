#!/usr/bin/env bash
# spring-boot, uncapped, after the current queue drains.
#
# It was stranded rather than skipped: the capped re-run deleted its record as
# its first step, and killing that run to switch to uncapped mode left the
# project with no record at all -- so the scan that builds the uncapped queue,
# which looks for records that produced nothing, could not see it. A project
# with no record is invisible to every check that reads records, which is a
# sharper version of the same lesson the empty buckets keep teaching.
set -uo pipefail
ROOT=/home/ubuntu/sbomify-eval

while pgrep -f 'rerun_unlimited' > /dev/null || pgrep -f 'run_one_v[5].sh' > /dev/null; do
  sleep 60
done

row=$(grep -P '^java\tspring-projects/spring-boot\t' "$ROOT/projects_v5.tsv")
[ -z "$row" ] && { echo "spring-boot not in the corpus" >&2; exit 1; }

IFS=$'\t' read -r eco slug url note ref <<< "$row"
find "$ROOT/v5/slots" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null
find "$ROOT/v5/eco" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null
rm -rf "$ROOT/v5/locks/spring-projects_spring-boot"

echo "=== $slug (uncapped, 90 min)"
MEM=none SLOTS=1 RUN_TIMEOUT=5400 CLONE_TIMEOUT=1800 \
  "$ROOT/run_one_v5.sh" "$eco" "$slug" "$url" "$note" "$ref" \
  >> "$ROOT/v5/rerun_unlimited.log" 2>&1

echo "finished: $(ls "$ROOT/v5/meta" | wc -l)/500 records"
