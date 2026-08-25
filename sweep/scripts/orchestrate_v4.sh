#!/usr/bin/env bash
# All 500 projects, one pinned image.
#
# The two earlier sweeps each measured a different build: 251 projects against
# whatever `:latest` was on the 7th, 249 against the 8th, with roughly fifteen
# fixes merged in between. That was fine while the goal was finding bugs, and
# useless for stating what the tool does now -- a finding could describe a
# build that has since been fixed, and no single number covered the whole
# corpus. This run exists to produce numbers that need no such footnote:
# every project against ghcr.io/sbomify/sbomify-action@sha256:0a29db00...,
# which reports 26.7.0+688841c, i.e. master with all of those fixes in it.
#
# The corpus is built and validated by build_v4_corpus.py, not here, so a
# malformed row fails at corpus-build time rather than hours into a sweep.
#
# Fields are handed to xargs NUL-delimited rather than newline-delimited.
# `tr '\t' '\n' | xargs -n 4` splits on whitespace, so a note containing a
# space becomes two arguments and shifts every field after it: `top-100, huge
# JS+native monorepo` produced a run whose ecosystem was "huge" and whose lock
# file was a fragment of prose.
set -uo pipefail
EVAL_ROOT=/home/ubuntu/sbomify-eval
OUT_ROOT=$EVAL_ROOT/v4

# Two workers, not five. Five uncapped builds is what exhausted this 15 GB
# host -- shared with several other dev stacks -- and got the previous sweep
# OOM-killed at 115 of 249, taking the agent's own session down with it.
# run_one_v4.sh caps each container at 4 GB and marks it as the kernel's first
# choice, and two of those is the most this box has headroom for.
JOBS=${JOBS:-2}

cd "$EVAL_ROOT"
mkdir -p "$OUT_ROOT"/{meta,logs,out,repos,locks,slots}

if [ ! -s "$OUT_ROOT/all.tsv" ]; then
  echo "refusing to start: no corpus at $OUT_ROOT/all.tsv (run build_v4_corpus.py)" >&2
  exit 1
fi
total=$(wc -l < "$OUT_ROOT/all.tsv")

bad=$(awk -F'\t' 'NF != 4 {n++} END {print n+0}' "$OUT_ROOT/all.tsv")
if [ "$bad" -ne 0 ]; then
  echo "refusing to start: $bad malformed rows in $OUT_ROOT/all.tsv" >&2
  exit 1
fi

# The image must be present locally. Pulling it here would defeat the pin: a
# digest that does not resolve should stop the run, not silently fetch.
if ! docker image inspect \
    ghcr.io/sbomify/sbomify-action@sha256:0a29db0020f59c8ed0b4d0ac3202346f2734d6fd6704b4139c8078207293da30 \
    >/dev/null 2>&1; then
  echo "refusing to start: pinned image digest not present locally" >&2
  exit 1
fi

# Slot locks are released by an EXIT trap, which a killed worker never runs.
# Five stale ones left the next run's workers queueing for a slot that would
# never free: no logs, no records, and the retry loop waits 80 minutes before
# giving up, so it looks like slow progress rather than a stuck run. Nothing
# should be holding a slot at startup, so clear them.
stale=$(find "$OUT_ROOT/slots" -maxdepth 1 -name '*.lock' -type d 2>/dev/null | wc -l)
if [ "$stale" -gt 0 ]; then
  echo "clearing $stale stale slot lock(s) from a previous run"
  find "$OUT_ROOT/slots" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null
fi

# Same for per-project locks: a lock with no record behind it is the residue
# of a killed worker, and run_one treats it as "another worker has this" and
# skips the project for good. Only clear the ones with nothing to show.
recovered=0
for l in "$OUT_ROOT"/locks/*; do
  [ -d "$l" ] || continue
  k=$(basename "$l")
  [ -s "$OUT_ROOT/meta/$k.json" ] && continue
  rm -rf "$l" && recovered=$((recovered + 1))
done
[ "$recovered" -gt 0 ] && echo "released $recovered abandoned project lock(s)"

echo "[$(date -u +%H:%M:%S)] v4 sweep: $total projects, $JOBS workers, one cache each"
echo "[$(date -u +%H:%M:%S)] resuming from $(ls "$OUT_ROOT/meta" 2>/dev/null | wc -l) existing records"
tr '\t\n' '\0\0' < "$OUT_ROOT/all.tsv" \
  | SLOTS=$JOBS xargs -0 -P "$JOBS" -n 4 "$EVAL_ROOT/run_one_v4.sh" \
  >> "$OUT_ROOT/orchestrate.log" 2>&1
echo "[$(date -u +%H:%M:%S)] finished: $(ls "$OUT_ROOT/meta" | wc -l) of $total"
