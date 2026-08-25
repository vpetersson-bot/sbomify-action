#!/usr/bin/env bash
# Drive run_one.sh across the whole project list with bounded parallelism.
#
# Ordering is round-robin across ecosystems rather than the file's order, so
# that a run stopped early still has proportional coverage of every stack
# instead of all the Python and none of the Swift.

set -uo pipefail
EVAL_ROOT=/home/ubuntu/sbomify-eval
JOBS=${JOBS:-5}

cd "$EVAL_ROOT"

# Interleave: emit one project per ecosystem, then the next of each, ...
python3 - <<'PY' > /tmp/ordered.tsv
import csv, itertools
rows = list(csv.reader(open('/home/ubuntu/sbomify-eval/projects.tsv'), delimiter='\t'))[1:]
buckets = {}
for r in rows:
    if len(r) >= 4:
        buckets.setdefault(r[0], []).append(r)
out = []
for group in itertools.zip_longest(*buckets.values()):
    out.extend(r for r in group if r)
with open('/dev/stdout', 'w', newline='') as fh:
    csv.writer(fh, delimiter='\t').writerows(out)
PY

total=$(wc -l < /tmp/ordered.tsv)
echo "[$(date -u +%H:%M:%S)] starting $total projects, $JOBS workers"

# -P bounds concurrency; each line is one project. run_one.sh is idempotent
# and skips anything with a finished record, so a rerun resumes.
tr '\t' '\n' < /tmp/ordered.tsv | xargs -P "$JOBS" -n 4 "$EVAL_ROOT/run_one.sh" \
  >> "$EVAL_ROOT/orchestrate.log" 2>&1

echo "[$(date -u +%H:%M:%S)] finished: $(ls "$EVAL_ROOT/meta" | wc -l) records"
