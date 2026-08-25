#!/usr/bin/env bash
# Re-run the projects whose result was produced while the runtime cache was
# cold and several workers raced to materialise the same bundle (F19).
#
# Those failures are mine, not the tool's: I deleted the shared cache
# mid-evaluation. The cache is warm now, and this runs two at a time rather
# than three, so the race cannot recur. Records are deleted first so
# run_one.sh does not skip them.

set -uo pipefail
EVAL_ROOT=/home/ubuntu/sbomify-eval
cd "$EVAL_ROOT"

# Warm the runtime bundles with a single container before fanning out, so the
# first concurrent pair cannot race on a cold cache the way the original run did.
echo "warming runtime cache..."
docker run --rm -v "$EVAL_ROOT/cache":/cache \
  -e HOME=/cache/home -e XDG_CACHE_HOME=/cache/xdg \
  -e SBOMIFY_CACHE_DIR=/cache/enrichment \
  --entrypoint python3 ghcr.io/sbomify/sbomify-action:latest -c '
from sbomify_action.runtimes import ensure_runtime
for r in ("syft", "cdxgen"):
    try:
        ensure_runtime(r); print(f"{r} ready")
    except Exception as e:
        print(f"{r}: {e}")
' 2>&1 | tail -4

# Rebuild eco/slug/url triples for the affected keys from both project lists.
python3 - <<'PY' > /tmp/rerun_flat.txt
import csv, pathlib
keys = set(pathlib.Path('/tmp/rerun.txt').read_text().split())
out = []
for f in ('projects.tsv', 'projects_ext.tsv'):
    for r in csv.reader(open(f'/home/ubuntu/sbomify-eval/{f}'), delimiter='\t'):
        if len(r) < 4 or r[0] == 'ecosystem':
            continue
        key = r[1].replace('/', '_').replace(':', '_').replace('.', '_')
        if key in keys:
            out.append((r[0], r[1], r[2], r[3]))
            keys.discard(key)
for row in out:
    print('\n'.join(row))
print(f'# {len(out)} queued', end='')
PY
sed -i '/^#/d' /tmp/rerun_flat.txt

n=$(( $(wc -l < /tmp/rerun_flat.txt) / 4 ))
echo "re-running $n projects with a warm cache, 2 at a time"

# Drop the contaminated records so they are not skipped.
while read -r k; do rm -f "$EVAL_ROOT/meta/$k.json"; rm -rf "$EVAL_ROOT/locks/$k"; done < /tmp/rerun.txt

xargs -P 2 -n 4 -a /tmp/rerun_flat.txt "$EVAL_ROOT/run_one.sh"
echo "clean re-run complete: $(ls "$EVAL_ROOT/meta" | wc -l) records"
