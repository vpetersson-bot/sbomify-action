#!/usr/bin/env bash
# Keep re-running the deferred projects until a pass adds nothing.
#
# The targeted re-run used a single xargs pass, which is the flaw the main
# orchestrator already fixed and this script did not inherit: a worker that
# cannot take the ecosystem lock hands its project back, and with no later
# pass there is nothing to hand it back to. 21 of 101 were dropped exactly
# that way -- the ECOBUSY count in the log matches the shortfall to the
# project.
#
# So: loop until a pass produces no new records, the same rule the orchestrator
# uses, which is the honest definition of "as far as this gets".
set -uo pipefail
ROOT=/home/ubuntu/sbomify-eval

while pgrep -f 'queue_noinput_rerun' > /dev/null || pgrep -f 'run_one_v[5].sh' > /dev/null; do
  sleep 60
done
echo "earlier re-runs finished; completing anything still missing"

pass=0
while :; do
  pass=$((pass + 1))
  before=$(ls "$ROOT/v5/meta" | wc -l)

  python3 - <<'PY'
import pathlib
ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
have = {p.stem for p in (ROOT / "v5/meta").glob("*.json") if p.stat().st_size}
missing = []
for line in (ROOT / "projects_v5.tsv").read_text().splitlines():
    if not line.strip():
        continue
    slug = line.split("\t")[1]
    key = slug.replace("/", "_").replace(":", "_").replace(".", "_")
    if key not in have:
        missing.append(line)
(ROOT / "still_missing.tsv").write_text("".join(m + "\n" for m in missing))
print(f"  {len(missing)} project(s) still without a record")
PY

  [ -s "$ROOT/still_missing.tsv" ] || { echo "nothing missing; done"; break; }

  find "$ROOT/v5/slots" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null
  find "$ROOT/v5/eco" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null

  tr '\t\n' '\0\0' < "$ROOT/still_missing.tsv" \
    | SLOTS=3 xargs -0 -P 3 -n 5 "$ROOT/run_one_v5.sh" \
    >> "$ROOT/v5/rerun_finish.log" 2>&1

  after=$(ls "$ROOT/v5/meta" | wc -l)
  echo "pass $pass: $before -> $after of 500"
  [ "$after" -le "$before" ] && { echo "pass $pass added nothing; stopping"; break; }
done
echo "COMPLETE: $(ls "$ROOT/v5/meta" | wc -l)/500 records"
