#!/usr/bin/env bash
# All 500 projects, at the release a user would actually scan.
#
# The change from v4 is the subject, not the tool. Every earlier sweep cloned
# each project's default branch, and nobody generates an SBOM for master --
# what you ship is a release. That was not a cosmetic difference: F6
# ("placeholder root versions are pervasive") was measured entirely on
# default-branch checkouts, and a PR was opened off the back of it to fix
# something that had never been shown to be broken against a real subject.
#
# 461 of the 500 resolve to a GitHub release or a version-sorted tag. The
# remaining 39 have neither; they run at their default branch and every record
# carries `released: false` so they can be excluded from a claim about
# released software rather than quietly diluting it.
#
# Fields are handed to xargs NUL-delimited. `tr '\t' '\n' | xargs -n 5` splits
# on whitespace, so a note containing a space becomes two arguments and shifts
# every field after it -- which once produced runs whose "ecosystem" was the
# word "huge" and whose lock file was a fragment of prose.
set -uo pipefail
EVAL_ROOT=/home/ubuntu/sbomify-eval
OUT_ROOT=$EVAL_ROOT/v5
#: 26.7.0+4238898 -- the CI build of master at the #371 merge, carrying all
#: eight fixes this evaluation produced (#360, #361, #363, #367, #368, #369, #371).
IMAGE_DIGEST=local

# Three workers, never two of the same ecosystem.
#
# Two was the safe number when any worker might be a Gradle build: the box has
# about 8 GB of headroom and 3 x 4 GB does not fit. The per-ecosystem lock in
# run_one_v5.sh changes that arithmetic -- at most one heavy build can be in
# flight, so the caps come to 4 + 2 + 2 rather than 12.
#
# It also removes the reason two was chosen in the first place. Five *uncapped*
# builds OOM-killed an earlier sweep at 115 of 249, and what made that possible
# was several JVM projects at once; that can no longer happen regardless of the
# worker count. The rule is the safety property, not the number.
JOBS=${JOBS:-3}

cd "$EVAL_ROOT"
mkdir -p "$OUT_ROOT"/{meta,logs,out,repos,locks,slots,eco}

if [ ! -s "$EVAL_ROOT/projects_v5.tsv" ]; then
  echo "refusing to start: no corpus (run resolve_releases.py)" >&2
  exit 1
fi
cp "$EVAL_ROOT/projects_v5.tsv" "$OUT_ROOT/all.tsv"
total=$(wc -l < "$OUT_ROOT/all.tsv")

# Five fields now: the ref is the point of this run, and a row missing it would
# silently be scanned at its default branch -- the exact thing being fixed.
bad=$(awk -F'\t' 'NF != 5 {n++} END {print n+0}' "$OUT_ROOT/all.tsv")
if [ "$bad" -ne 0 ]; then
  echo "refusing to start: $bad rows are not 5 fields" >&2
  exit 1
fi

if ! docker image inspect "ghcr.io/sbomify/sbomify-action@$IMAGE_DIGEST" >/dev/null 2>&1; then
  echo "refusing to start: pinned image digest not present locally" >&2
  exit 1
fi

# Disk, checked up front. The v4 run reported "finished: 500 of 500" while 18
# of those records were zero bytes, written in the 22 minutes it spent below
# 400MB free. A count of files is not a count of results.
avail=$(df --output=avail "$EVAL_ROOT" | tail -1 | tr -d ' ')
if [ "$avail" -lt 62914560 ]; then
  echo "refusing to start: under 60G free; slot caches alone reached 102G last run" >&2
  exit 1
fi

stale=$(find "$OUT_ROOT/slots" -maxdepth 1 -name '*.lock' -type d 2>/dev/null | wc -l)
if [ "$stale" -gt 0 ]; then
  echo "clearing $stale stale slot lock(s) from a previous run"
  find "$OUT_ROOT/slots" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null
fi

# Ecosystem locks are released by the same EXIT trap, so a killed run leaves
# them held too -- and a held ecosystem lock is worse than a held slot: every
# project in that ecosystem would wait thirty minutes and then give up, so a
# single stale lock could silently drop 48 javascript projects from the run.
stale_eco=$(find "$OUT_ROOT/eco" -maxdepth 1 -name '*.lock' -type d 2>/dev/null | wc -l)
if [ "$stale_eco" -gt 0 ]; then
  echo "clearing $stale_eco stale ecosystem lock(s) from a previous run"
  find "$OUT_ROOT/eco" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null
fi

# A project lock with no record behind it is the residue of a killed worker,
# and run_one treats it as "another worker has this" and skips the project for
# good. Clear only those.
recovered=0
for l in "$OUT_ROOT"/locks/*; do
  [ -d "$l" ] || continue
  k=$(basename "$l")
  [ -s "$OUT_ROOT/meta/$k.json" ] && continue
  rm -rf "$l" && recovered=$((recovered + 1))
done
[ "$recovered" -gt 0 ] && echo "released $recovered abandoned project lock(s)"

echo "[$(date -u +%H:%M:%S)] v5 sweep: $total projects at their releases, $JOBS workers"
echo "[$(date -u +%H:%M:%S)] resuming from $(ls "$OUT_ROOT/meta" 2>/dev/null | wc -l) existing records"

# Repeated passes until one adds nothing.
#
# A single pass drops whatever it could not start. That was rare when every
# ecosystem had its own lock, and is not rare now the JVM family shares one:
# a worker that waits out its thirty minutes gives the project back, and with
# ~55 projects queued behind a single lock plenty will. xargs never revisits
# them, so one pass would silently finish "complete" with those missing --
# the same shape as the v4 run that reported 500 of 500 with 18 empty.
#
# Resume is by record, so a pass costs nothing for work already done: every
# finished project exits immediately on the `[ -s "$res" ]` check. The loop
# stops when a pass adds no records, which is the honest definition of done.
pass=0
while :; do
  pass=$((pass + 1))
  before=$(ls "$OUT_ROOT/meta" 2>/dev/null | wc -l)
  echo "[$(date -u +%H:%M:%S)] pass $pass starting from $before/$total"

  tr '\t\n' '\0\0' < "$OUT_ROOT/all.tsv" \
    | SLOTS=$JOBS xargs -0 -P "$JOBS" -n 5 "$EVAL_ROOT/run_one_v5.sh" \
    >> "$OUT_ROOT/orchestrate.log" 2>&1

  after=$(ls "$OUT_ROOT/meta" 2>/dev/null | wc -l)
  echo "[$(date -u +%H:%M:%S)] pass $pass: $before -> $after of $total"

  [ "$after" -ge "$total" ] && break
  if [ "$after" -le "$before" ]; then
    echo "[$(date -u +%H:%M:%S)] pass $pass added nothing; $((total - after)) project(s) could not be completed"
    break
  fi
  # Locks held by workers killed mid-pass would block the next one.
  find "$OUT_ROOT/eco" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null
  find "$OUT_ROOT/slots" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null
done

echo "[$(date -u +%H:%M:%S)] finished: $(ls "$OUT_ROOT/meta" | wc -l) of $total after $pass pass(es)"
