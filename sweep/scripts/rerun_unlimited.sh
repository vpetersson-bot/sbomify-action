#!/usr/bin/env bash
# Re-run every project the harness itself decided against, with the harness
# limits removed, one at a time.
#
# Two groups, both carrying a verdict the tool did not earn:
#
#   * "Gradle build daemon disappeared unexpectedly" -- the JVM killed inside a
#     4 GB cgroup. That is the cap, not the action.
#   * exit 124 -- killed at the 35-minute timeout. On a cold runtime cache a
#     large Gradle or Go build can legitimately want longer.
#
# Strictly serial, because uncapped means one container may take the machine.
# --oom-score-adj is still applied inside run_one_v5.sh, so if the host runs
# short the container is chosen first and the session survives; that is the
# difference between this and the run that OOM-killed an earlier session.
set -uo pipefail
ROOT=/home/ubuntu/sbomify-eval

if pgrep -f 'run_one_v[5].sh' > /dev/null; then
  echo "refusing to start: workers are already running" >&2
  exit 1
fi

python3 - <<'PY'
import json, pathlib, re
ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
LOGS = ROOT / "v5/logs"
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
    runs = rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else [])
    if not runs or any((r.get("sbom") or {}).get("components") for r in runs):
        continue
    timed_out = any(r.get("strict_rc") == 124 for r in runs)
    log = LOGS / f"{f.stem}.log"
    text = log.read_text(errors="replace")[-400_000:] if log.exists() else ""
    killed = bool(re.search(r"daemon disappeared unexpectedly|OutOfMemoryError|Java heap space", text, re.I))
    if timed_out or killed:
        wanted.append(rows[rec["slug"]])
(ROOT / "rerun_unlimited.tsv").write_text("".join(w + "\n" for w in wanted))
print(f"{len(wanted)} project(s) held back by a harness limit")
PY

while IFS=$'\t' read -r eco slug url note ref; do
  [ -z "${slug:-}" ] && continue
  key=$(printf '%s' "$slug" | tr '/:.' '___')
  rm -f "$ROOT/v5/meta/$key.json"
  rm -rf "$ROOT/v5/out/$key" "$ROOT/v5/locks/$key"
  find "$ROOT/v5/slots" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null
  find "$ROOT/v5/eco" -maxdepth 1 -name '*.lock' -type d -exec rm -rf {} + 2>/dev/null
  echo "=== $slug (uncapped, 90 min)"
  MEM=none SLOTS=1 RUN_TIMEOUT=5400 CLONE_TIMEOUT=1800 \
    "$ROOT/run_one_v5.sh" "$eco" "$slug" "$url" "$note" "$ref" \
    >> "$ROOT/v5/rerun_unlimited.log" 2>&1
  echo "    -> $(python3 -c "
import json,sys,pathlib
p=pathlib.Path('$ROOT/v5/meta/$key.json')
if not p.exists(): print('no record'); sys.exit()
r=json.loads(p.read_text())
runs=r.get('runs') or [r]
print(', '.join(f\"{x.get('target_lockfile')}={(x.get('sbom') or {}).get('components')}\" for x in runs))
" 2>/dev/null)"
done < "$ROOT/rerun_unlimited.tsv"

echo "finished: $(ls "$ROOT/v5/meta" | wc -l)/500 records"
