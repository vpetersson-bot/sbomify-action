#!/usr/bin/env bash
# Re-run the "no recognised input" projects once the current re-run finishes.
#
# These were excluded on the reasoning that none of the merged fixes touches
# discovery, so re-running them could only confirm they are still unsupported.
# That reasoning is probably right and it is still an assumption, and the cost
# of testing it is small -- these projects clone, discover nothing and exit,
# with no build to run. "All the ones that previously failed" is a cheaper
# claim to make true than to argue about.
#
# Chained rather than run alongside: the three worker slots are held by the
# current re-run, and starting a second xargs would oversubscribe the box that
# has already been OOM-killed once in this project.
set -uo pipefail
ROOT=/home/ubuntu/sbomify-eval

while pgrep -f 'clear_and_rerun_failures' > /dev/null || pgrep -f 'run_one_v[5].sh' > /dev/null; do
  sleep 60
done
echo "first re-run finished; starting the no-input set"

python3 - <<'PY'
import json, pathlib
ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
rows = {
    line.split("\t")[1]: line
    for line in (ROOT / "projects_v5.tsv").read_text().splitlines()
    if line.strip()
}
wanted = []
for f in sorted((ROOT / "v5/meta").glob("*.json")):
    if not f.stat().st_size:
        continue
    rec = json.loads(f.read_text())
    if rec.get("error") == "no_lockfile_discovered":
        wanted.append(rows[rec["slug"]])
(ROOT / "rerun_noinput.tsv").write_text("".join(r + "\n" for r in wanted))
print(f"{len(wanted)} no-input projects queued")
PY

while IFS=$'\t' read -r _eco slug _url _note _ref; do
  [ -z "${slug:-}" ] && continue
  key=$(printf '%s' "$slug" | tr '/:.' '___')
  rm -f "$ROOT/v5/meta/$key.json"
  rm -rf "$ROOT/v5/out/$key" "$ROOT/v5/locks/$key"
done < "$ROOT/rerun_noinput.tsv"

find "$ROOT/v5/slots" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null
find "$ROOT/v5/eco" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null

tr '\t\n' '\0\0' < "$ROOT/rerun_noinput.tsv" \
  | SLOTS=3 xargs -0 -P 3 -n 5 "$ROOT/run_one_v5.sh" \
  >> "$ROOT/v5/rerun_noinput.log" 2>&1

echo "no-input re-run finished: $(ls "$ROOT/v5/meta" | wc -l)/500 records"
