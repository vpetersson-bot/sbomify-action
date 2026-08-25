#!/usr/bin/env bash
# Re-run the projects whose Gradle daemon the memory cap killed.
#
# These five carry a verdict the tool did not earn. "Gradle build daemon
# disappeared unexpectedly" is the JVM being killed inside a 4 GB cgroup, and
# the cap is the harness's choice -- made because three concurrent 4 GB builds
# do not fit on this box, which is a fact about the box and not about the
# action. Judging the tool on it would be like reporting a compiler as broken
# because the machine ran out of RAM.
#
# Strictly serial and one at a time, with everything else stopped. 6 GB is
# most of the host's headroom, so two of these at once is how the earlier
# session got OOM-killed.
set -uo pipefail
ROOT=/home/ubuntu/sbomify-eval

if pgrep -f 'run_one_v[5].sh' > /dev/null; then
  echo "refusing to start: workers are already running" >&2
  exit 1
fi

grep -E "^(dart	cfug/dio|dart	flutter/samples|java	spring-projects/spring-boot|kotlin	coil-kt/coil|kotlin	ktorio/ktor)	" \
  "$ROOT/projects_v5.tsv" > "$ROOT/rerun_memory.tsv"
echo "$(wc -l < "$ROOT/rerun_memory.tsv") project(s) to re-run at 6g"

while IFS=$'\t' read -r eco slug url note ref; do
  [ -z "${slug:-}" ] && continue
  key=$(printf '%s' "$slug" | tr '/:.' '___')
  rm -f "$ROOT/v5/meta/$key.json"
  rm -rf "$ROOT/v5/out/$key" "$ROOT/v5/locks/$key"
  find "$ROOT/v5/slots" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null
  find "$ROOT/v5/eco" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null
  echo "--- $slug at 6g"
  MEM=6g SLOTS=1 RUN_TIMEOUT=3000 "$ROOT/run_one_v5.sh" "$eco" "$slug" "$url" "$note" "$ref" \
    >> "$ROOT/v5/rerun_memory.log" 2>&1
done < "$ROOT/rerun_memory.tsv"

echo "done: $(ls "$ROOT/v5/meta" | wc -l)/500 records"
