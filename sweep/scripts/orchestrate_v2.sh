#!/usr/bin/env bash
# Re-run the whole corpus against the image built from master after the fixes.
#
# One pass, with every worker holding its own runtime cache (see
# run_one_v2.sh). An earlier version split JVM projects into a separate
# isolated phase because there was only 16G of disk and each slot pulls its
# own copy of the 2.7G JVM bundle. With 213G there is no reason to
# compromise: isolating every project removes the shared-cache contamination
# behind F16, which made the first survey's Java numbers unusable and forced a
# second isolated run. All 251 results are now comparable in one pass.
#
# The environment handed to the action is deliberately identical to the first
# survey -- AUGMENT and ENRICH on, UPLOAD off, no token, no CI variables -- so
# the before/after comparison measures our changes and not a changed harness.
# The cost is that the sbomify API augmentation provider skips itself for want
# of a token, exactly as it did the first time; the report says so.

set -uo pipefail
EVAL_ROOT=/home/ubuntu/sbomify-eval
OUT_ROOT=$EVAL_ROOT/v2
JOBS=${JOBS:-5}
SLOTS=${SLOTS:-2}

cd "$EVAL_ROOT"
mkdir -p "$OUT_ROOT"/{meta,logs,out,repos,locks,slots}

# One list from both files, deduplicated on slug, header rows dropped.
python3 - <<'PY' > "$OUT_ROOT/all.tsv"
import csv, itertools, pathlib
rows, seen = [], set()
for name in ("projects.tsv", "projects_ext.tsv"):
    p = pathlib.Path("/home/ubuntu/sbomify-eval") / name
    if not p.exists():
        continue
    for r in csv.reader(p.open(), delimiter="\t"):
        if len(r) < 4 or r[0] == "ecosystem":
            continue
        if r[1] in seen:
            continue
        seen.add(r[1])
        rows.append(r)

# Interleave across ecosystems so a run stopped early still has proportional
# coverage of every stack rather than all the Python and none of the Swift.
buckets = {}
for r in rows:
    buckets.setdefault(r[0], []).append(r)
out = []
for group in itertools.zip_longest(*buckets.values()):
    out.extend(r for r in group if r)
csv.writer(open("/dev/stdout", "w", newline=""), delimiter="\t").writerows(out)
PY

total=$(wc -l < "$OUT_ROOT/all.tsv")
echo "[$(date -u +%H:%M:%S)] corpus: $total projects"

echo "[$(date -u +%H:%M:%S)] running all $total projects, $JOBS workers, one cache each"
tr '\t' '\n' < "$OUT_ROOT/all.tsv" | SLOTS=$JOBS xargs -P "$JOBS" -n 4 "$EVAL_ROOT/run_one_v2.sh" \
  >> "$OUT_ROOT/orchestrate.log" 2>&1

echo "[$(date -u +%H:%M:%S)] finished: $(ls "$OUT_ROOT/meta" | wc -l) records of $total"
