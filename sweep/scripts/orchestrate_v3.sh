#!/usr/bin/env bash
# The 249 projects added in the second expansion, against the same image.
#
# Not a before/after: these have no baseline, so the question is different --
# what does the tool do when pointed at an ecosystem or a repository shape it
# has never been measured on. Twelve of the ecosystems here have never been
# tested at all, and a large slice of the list is deliberately monorepos.
#
# Fields are handed to xargs NUL-delimited rather than newline-delimited.
# The first version of this used `tr '\t' '\n' | xargs -n 4`, which splits on
# whitespace, so a note containing a space became two arguments and shifted
# every field after it: `top-100, huge JS+native monorepo` turned into a run
# where the ecosystem was "huge" and the lock file was a fragment of prose.
# It went unnoticed in the first survey because every note there was a single
# token; this corpus writes them as sentences.
set -uo pipefail
EVAL_ROOT=/home/ubuntu/sbomify-eval
OUT_ROOT=$EVAL_ROOT/v3
# Two workers, not five. Five uncapped builds is what exhausted a 15 GB host
# shared with several other dev stacks and got the run OOM-killed at 115 of
# 249; run_one_v3.sh now caps each container at 4 GB, and two of those is the
# most this box has headroom for. The remaining corpus is mostly small
# ecosystems -- zig, lua, nim, nix, ocaml, perl, r -- so the lost parallelism
# costs less here than it would have at the start.
JOBS=${JOBS:-2}

cd "$EVAL_ROOT"
mkdir -p "$OUT_ROOT"/{meta,logs,out,repos,locks,slots}

tail -n +2 projects_v3.tsv > "$OUT_ROOT/all.tsv"
total=$(wc -l < "$OUT_ROOT/all.tsv")

# Reject anything that is not exactly four fields before spending hours on it.
bad=$(awk -F'\t' 'NF != 4 {n++} END {print n+0}' "$OUT_ROOT/all.tsv")
if [ "$bad" -ne 0 ]; then
  echo "refusing to start: $bad malformed rows in projects_v3.tsv" >&2
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

echo "[$(date -u +%H:%M:%S)] v3 sweep: $total projects, $JOBS workers, one cache each"
tr '\t\n' '\0\0' < "$OUT_ROOT/all.tsv" \
  | SLOTS=$JOBS xargs -0 -P "$JOBS" -n 4 "$EVAL_ROOT/run_one_v3.sh" \
  >> "$OUT_ROOT/orchestrate.log" 2>&1
echo "[$(date -u +%H:%M:%S)] finished: $(ls "$OUT_ROOT/meta" | wc -l) of $total"
