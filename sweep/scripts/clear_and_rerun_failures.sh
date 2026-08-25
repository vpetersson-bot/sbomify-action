#!/usr/bin/env bash
# Clear the failed projects' records and run them again on the new image.
#
# The 500-record corpus measured on 4238898 is snapshotted at
# v5/meta-4238898-snapshot before anything here runs, because this re-run
# deliberately makes v5/meta a mixture of two builds. Every record carries the
# digest it ran under, so the mixture is visible rather than implied -- but the
# snapshot is what the write-up's single-build claim rests on, and it must not
# be the thing that gets overwritten.
set -uo pipefail
ROOT=/home/ubuntu/sbomify-eval
LIST=$ROOT/rerun_failures.tsv

[ -d "$ROOT/v5/meta-4238898-snapshot" ] || {
  echo "refusing to start: no snapshot of the single-build corpus" >&2
  exit 1
}
[ -s "$LIST" ] || { echo "refusing to start: $LIST is empty" >&2; exit 1; }

n=0
while IFS=$'\t' read -r _eco slug _url _note _ref; do
  [ -z "${slug:-}" ] && continue
  key=$(printf '%s' "$slug" | tr '/:.' '___')
  rm -f "$ROOT/v5/meta/$key.json"
  rm -rf "$ROOT/v5/out/$key" "$ROOT/v5/locks/$key"
  n=$((n + 1))
done < "$LIST"
echo "cleared $n records; $(ls "$ROOT/v5/meta" | wc -l) remain from the previous build"

find "$ROOT/v5/slots" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null
find "$ROOT/v5/eco" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null

tr '\t\n' '\0\0' < "$LIST" \
  | SLOTS=3 xargs -0 -P 3 -n 5 "$ROOT/run_one_v5.sh" \
  >> "$ROOT/v5/rerun_failures.log" 2>&1

echo "finished: $(ls "$ROOT/v5/meta" | wc -l)/500 records"
