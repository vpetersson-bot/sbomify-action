#!/usr/bin/env bash
# Drive the worst-200 replay. Resume-safe: re-running skips finished records.
#
# Concurrency is deliberately low. The box has 15G total and is shared with
# other sessions; an uncapped sweep here has already OOM-killed an agent
# session once. Each container is memory-capped and marked as the first thing
# the kernel should kill, so a runaway generator dies instead of the host.
set -uo pipefail

# Resolve relative to this script so the harness runs on any machine;
# absolute /home/ubuntu paths made it silently machine-specific.
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export OUT_ROOT=${OUT_ROOT:-$ROOT/v6}
export IMAGE=${IMAGE:?set IMAGE to a digest-pinned reference}
export CACHE=${CACHE:-$OUT_ROOT/cache}
export RUN_TIMEOUT=${RUN_TIMEOUT:-900}
export RUN_AS_HOST_USER=${RUN_AS_HOST_USER:-0}
export MEM=${MEM:-2g}
WORKERS=${WORKERS:-3}
export ROOT

mkdir -p "$OUT_ROOT/meta" "$OUT_ROOT/logs" "$OUT_ROOT/out" "$CACHE"
main_log=$OUT_ROOT/orchestrate.log

LIST=${LIST:-$ROOT/replay200.tsv}
total=$(grep -c . "$LIST")
done_now=$(find "$OUT_ROOT/meta" -name '*.json' -size +0 2>/dev/null | wc -l)
echo "[$(date +%H:%M:%S)] replay: $total from $(basename "$LIST"), $WORKERS workers, arch=$(uname -m), image=$IMAGE" | tee -a "$main_log"
echo "[$(date +%H:%M:%S)] resuming from $done_now existing records" | tee -a "$main_log"

# xargs -P for the worker pool: each line is independent, there is no shared
# state between projects, and every worker writes only its own record.
awk -F'\t' 'NF{print $1"\t"$2"\t"$3}' "$LIST" \
  | xargs -P "$WORKERS" -I{} -d'\n' bash -c '
      IFS=$'"'"'\t'"'"' read -r slug ref target <<< "{}"
      "$ROOT"/replay_one.sh "$slug" "$ref" "$target"
    ' >>"$main_log" 2>&1

final=$(find "$OUT_ROOT/meta" -name '*.json' -size +0 2>/dev/null | wc -l)
echo "[$(date +%H:%M:%S)] finished: $final of $total" | tee -a "$main_log"
