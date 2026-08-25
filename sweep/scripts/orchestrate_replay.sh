#!/usr/bin/env bash
# Drive the worst-200 replay. Resume-safe: re-running skips finished records.
#
# Concurrency is deliberately low. The box has 15G total and is shared with
# other sessions; an uncapped sweep here has already OOM-killed an agent
# session once. Each container is memory-capped and marked as the first thing
# the kernel should kill, so a runaway generator dies instead of the host.
set -uo pipefail

ROOT=/home/ubuntu/sbomify-eval
export OUT_ROOT=${OUT_ROOT:-$ROOT/v6}
export IMAGE=${IMAGE:?set IMAGE to a digest-pinned reference}
export CACHE=${CACHE:-$OUT_ROOT/cache}
export RUN_TIMEOUT=${RUN_TIMEOUT:-900}
export MEM=${MEM:-2g}
WORKERS=${WORKERS:-3}

mkdir -p "$OUT_ROOT/meta" "$OUT_ROOT/logs" "$OUT_ROOT/out" "$CACHE"
main_log=$OUT_ROOT/orchestrate.log

total=$(grep -c . "$ROOT/replay200.tsv")
done_now=$(find "$OUT_ROOT/meta" -name '*.json' -size +0 2>/dev/null | wc -l)
echo "[$(date +%H:%M:%S)] replay: $total projects, $WORKERS workers, image=$IMAGE" | tee -a "$main_log"
echo "[$(date +%H:%M:%S)] resuming from $done_now existing records" | tee -a "$main_log"

# xargs -P for the worker pool: each line is independent, there is no shared
# state between projects, and every worker writes only its own record.
awk -F'\t' 'NF{print $1"\t"$2"\t"$3}' "$ROOT/replay200.tsv" \
  | xargs -P "$WORKERS" -I{} -d'\n' bash -c '
      IFS=$'"'"'\t'"'"' read -r slug ref target <<< "{}"
      /home/ubuntu/sbomify-eval/replay_one.sh "$slug" "$ref" "$target"
    ' >>"$main_log" 2>&1

final=$(find "$OUT_ROOT/meta" -name '*.json' -size +0 2>/dev/null | wc -l)
echo "[$(date +%H:%M:%S)] finished: $final of $total" | tee -a "$main_log"
