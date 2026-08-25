#!/usr/bin/env bash
# Re-run the projects each merged fix was supposed to change, against the
# fixed image, and record the result next to the original.
#
# Deliberately narrow. A full 251-project sweep would take hours and answer a
# question nobody asked: what matters is whether the specific failures the
# report named are gone, and whether anything that used to work still does.
# The control rows are there for the second half of that.

set -uo pipefail
EVAL_ROOT=/home/ubuntu/sbomify-eval
IMAGE=${IMAGE:-sbomify-fixed-all}
export GIT_CONFIG_GLOBAL=$EVAL_ROOT/gitconfig
OUT=$EVAL_ROOT/validate
mkdir -p "$OUT"/{meta,logs,sbom}

eco=$1; slug=$2; url=$3; lock=$4
key=$(printf '%s' "$slug" | tr '/:.' '___')
res=$OUT/meta/$key.json
[ -s "$res" ] && { echo "SKIP $slug"; exit 0; }

repo=$EVAL_ROOT/repos/${key}__val
log=$OUT/logs/$key.log
sbom=$OUT/sbom/$key.json

nuke() {
  [ -e "$1" ] || return 0
  rm -rf "$1" 2>/dev/null
  [ -e "$1" ] && docker run --rm -v "$(dirname "$1")":/p alpine:3 rm -rf "/p/$(basename "$1")" >/dev/null 2>&1
  return 0
}
trap 'nuke "$repo"' EXIT
nuke "$repo"; : > "$log"

if ! timeout -k 30 900 git clone --depth 1 --quiet "$url" "$repo" >>"$log" 2>&1; then
  echo '{"slug":"'"$slug"'","error":"clone_failed"}' > "$res"; echo "CLONEFAIL $slug"; exit 0
fi

# Discovery is timed separately: the symlink-cycle fix is about this step
# terminating at all, and that is invisible in a generation timing.
t0=$(date +%s)
disc=$(timeout -k 15 180 docker run --rm --name "vd_$key" -v "$repo":/workspace:ro \
  --entrypoint python3 "$IMAGE" -c '
import json
from pathlib import Path
from sbomify_action.cli.wizard.discovery import discover
print(json.dumps([str(f.rel_path) for f in discover(Path("/workspace"))]))' 2>>"$log")
drc=$?
docker rm -f "vd_$key" >/dev/null 2>&1
t1=$(date +%s)
[ -z "$disc" ] && disc='[]'

# Strict first, then again with the fallback flag if that failed -- the same
# two phases the original survey ran. Comparing a strict-only re-run against a
# survey that allowed the fallback would invent regressions that are really
# just a different method.
cname="v_$key"
run_once() {
  docker rm -f "$cname" >/dev/null 2>&1
  timeout -k 30 1500 docker run --rm --name "$cname" \
    -v "$repo":/workspace -v "$EVAL_ROOT/cache":/cache -v "$OUT/sbom":/out \
    -e HOME=/cache/home -e XDG_CACHE_HOME=/cache/xdg -e SBOMIFY_CACHE_DIR=/cache/enrichment \
    ${1:+-e SBOMIFY_ALLOW_GENERATOR_FALLBACK=1} \
    -e WORKING_DIR=/workspace -e LOCK_FILE="$lock" -e OUTPUT_FILE="/out/$key.json" \
    -e UPLOAD=false -e AUGMENT=false -e ENRICH=false -e TELEMETRY=false \
    -e COMPONENT_NAME="$(basename "$slug")" \
    "$IMAGE" >>"$log" 2>&1
}
run_once ""
rc=$?
if [ $rc -ne 0 ]; then
  echo "=== retry with fallback ===" >>"$log"
  rm -f "$sbom"
  run_once "1"
  rc=$?
fi
docker rm -f "$cname" >/dev/null 2>&1
t2=$(date +%s)

insp='{}'
[ -s "$sbom" ] && insp=$(python3 "$EVAL_ROOT/inspect_sbom.py" "$sbom")
python3 - "$eco" "$slug" "$lock" "$rc" "$drc" "$((t1-t0))" "$((t2-t1))" "$disc" "$insp" > "$res" <<'PY'
import json,sys
eco,slug,lock,rc,drc,dsec,gsec,disc,insp = sys.argv[1:10]
print(json.dumps({"ecosystem":eco,"slug":slug,"lockfile":lock,"rc":int(rc),
  "discover_rc":int(drc),"discover_s":int(dsec),"generate_s":int(gsec),
  "discovered":json.loads(disc),"sbom":json.loads(insp)}))
PY
echo "VAL $slug rc=$rc discover=$((t1-t0))s gen=$((t2-t1))s"
