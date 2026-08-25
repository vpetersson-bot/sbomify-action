#!/usr/bin/env bash
# Second pass: re-run the projects whose default pick landed on the wrong
# stack, this time against the best lockfile of the *right* stack that the
# wizard actually discovered.
#
# This separates two failures that the first pass conflates. If a Scala
# project's SBOM is empty because discovery ranked pyproject.toml above
# pom.xml, that is a routing problem and the tool can do better. If it is
# still empty when pointed straight at pom.xml, that is a generation
# problem. Only the second is a gap in what the image can read.

set -uo pipefail
EVAL_ROOT=/home/ubuntu/sbomify-eval
IMAGE=ghcr.io/sbomify/sbomify-action:latest
export GIT_CONFIG_GLOBAL=$EVAL_ROOT/gitconfig
CACHE=$EVAL_ROOT/cache
RUN_TIMEOUT=${RUN_TIMEOUT:-1500}

ecosystem=$1; slug=$2; target=$3; lock=$4

key=$(printf '%s' "$slug" | tr '/:.' '___')
res=$EVAL_ROOT/meta2/$key.json
log=$EVAL_ROOT/logs2/$key.log
repo=$EVAL_ROOT/repos/${key}__best

[ -s "$res" ] && { echo "SKIP $slug"; exit 0; }
mkdir -p "$EVAL_ROOT/meta2" "$EVAL_ROOT/logs2" "$EVAL_ROOT/out2" "$EVAL_ROOT/locks2"

lockdir=$EVAL_ROOT/locks2/$key
mkdir "$lockdir" 2>/dev/null || { echo "BUSY $slug"; exit 0; }

cleanup() {
  rmdir "$lockdir" 2>/dev/null
  [ -d "$repo" ] || return 0
  rm -rf "$repo" 2>/dev/null
  [ -d "$repo" ] && docker run --rm -v "$EVAL_ROOT/repos":/r alpine:3 \
      rm -rf "/r/${key}__best" >/dev/null 2>&1
  return 0
}
trap cleanup EXIT
: > "$log"
t0=$(date +%s)

cleanup_repo_only() { :; }
rm -rf "$repo" 2>/dev/null
if ! timeout 900 git clone --depth 1 --quiet "$target" "$repo" >>"$log" 2>&1; then
  echo "CLONEFAIL $slug"; exit 0
fi

out=$EVAL_ROOT/out2/$key.cdx.json
# Fallback is enabled from the start here: the question this pass answers is
# "what is the best SBOM obtainable from the right lockfile", and strict
# mode's refusal was already measured in pass one.
timeout $RUN_TIMEOUT docker run --rm \
  -v "$repo":/workspace -v "$CACHE":/cache -v "$EVAL_ROOT/out2":/out \
  -e HOME=/cache/home -e XDG_CACHE_HOME=/cache/xdg -e SBOMIFY_CACHE_DIR=/cache/enrichment \
  -e SBOMIFY_ALLOW_GENERATOR_FALLBACK=1 \
  -e WORKING_DIR=/workspace -e LOCK_FILE="$lock" \
  -e OUTPUT_FILE="/out/$key.cdx.json" \
  -e UPLOAD=false -e AUGMENT=true -e ENRICH=true -e TELEMETRY=false \
  -e COMPONENT_NAME="$(basename "$slug")" \
  "$IMAGE" >>"$log" 2>&1
rc=$?

insp='{}'
[ -s "$out" ] && insp=$(python3 "$EVAL_ROOT/inspect_sbom.py" "$out")
t1=$(date +%s)
python3 - "$ecosystem" "$slug" "$lock" "$rc" "$((t1-t0))" "$insp" > "$res" <<'PY'
import json,sys
eco,slug,lock,rc,dur,insp = sys.argv[1:7]
print(json.dumps({"ecosystem":eco,"slug":slug,"best_lockfile":lock,
  "rc":int(rc),"duration_s":int(dur),"sbom":json.loads(insp)}))
PY
echo "DONE2 $slug rc=$rc lock=$lock"
