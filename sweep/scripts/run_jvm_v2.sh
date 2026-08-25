#!/usr/bin/env bash
# One JVM project, with a genuinely private runtime cache.
#
# The JVM bundle pins GRADLE_USER_HOME, MAVEN_ARGS (maven.repo.local) and
# SBT_OPTS to paths *inside* the runtime cache, and runtimes.py applies that
# env with a direct assignment rather than setdefault -- so passing those
# variables into the container does nothing. See F16. The only isolation that
# works is a separate XDG_CACHE_HOME, which means each concurrent slot fetches
# its own copy of the 2.7G bundle.
#
# So the cache is per *slot*, not per project: a slot is claimed for the
# duration of one project and reused by the next, and the bundle is therefore
# fetched once per slot rather than once per project.

set -uo pipefail
EVAL_ROOT=/home/ubuntu/sbomify-eval
OUT_ROOT=/home/ubuntu/sbomify-eval/v2
IMAGE=ghcr.io/sbomify/sbomify-action:latest
export GIT_CONFIG_GLOBAL=$EVAL_ROOT/gitconfig
RUN_TIMEOUT=${RUN_TIMEOUT:-2100}
SLOTS=${SLOTS:-2}

eco=$1; slug=$2; url=$3
key=$(printf '%s' "$slug" | tr '/:.' '___')
res=$OUT_ROOT/meta/$key.json
log=$OUT_ROOT/logs/$key.log
repo=$OUT_ROOT/repos/${key}__jvm
out=$OUT_ROOT/out/$key.cdx.json

[ -s "$res" ] && { echo "SKIP $slug"; exit 0; }
mkdir -p "$OUT_ROOT"/{meta,logs,out,slots}

# Claim a slot. Each carries its own runtime cache; whoever holds it has
# exclusive use of that cache's Gradle journal, which is the whole point.
# Wait for a slot rather than giving up: xargs will not revisit a project
# that exits early, so a transient "all slots busy" would drop it silently.
slot=""
for _try in $(seq 1 240); do
  for i in $(seq 0 $((SLOTS-1))); do
    if mkdir "$OUT_ROOT/slots/$i.lock" 2>/dev/null; then slot=$i; break 2; fi
  done
  sleep 15
done
[ -z "$slot" ] && { echo "NOSLOT $slug (waited 60m)"; exit 0; }
cache=$OUT_ROOT/slots/$slot.cache
mkdir -p "$cache"

nuke() {
  for d in "$@"; do
    [ -e "$d" ] || continue
    rm -rf "$d" 2>/dev/null
    [ -e "$d" ] && docker run --rm -v "$(dirname "$d")":/p alpine:3 \
        rm -rf "/p/$(basename "$d")" >/dev/null 2>&1
  done
}
cname="jvm_$key"
cleanup() {
  docker rm -f "$cname" >/dev/null 2>&1
  nuke "$repo"
  # Gradle leaves a lock file behind on a hard kill; the slot's cache is
  # otherwise worth keeping, since it holds the bundle.
  rm -f "$cache"/xdg/sbomify/runtimes/bundle-jvm-*/.gradle/caches/journal-1/*.lock 2>/dev/null
  rmdir "$OUT_ROOT/slots/$slot.lock" 2>/dev/null
  return 0
}
trap cleanup EXIT

nuke "$repo"
: > "$log"
if ! timeout -k 30 900 git clone --depth 1 --quiet "$url" "$repo" >>"$log" 2>&1; then
  echo "CLONEFAIL $slug"; exit 0
fi

lock=$(timeout -k 15 240 docker run --rm --name "disc_$key" -v "$repo":/workspace:ro \
  --entrypoint python3 "$IMAGE" -c '
from pathlib import Path
from sbomify_action.cli.wizard.discovery import discover
PRI = {"gradle.lockfile":50,"build.gradle":51,"build.gradle.kts":52,"pom.xml":53,"build.sbt":54}
found = [f for f in discover(Path("/workspace")) if f.rel_path.name in PRI]
if found:
    print(min(found, key=lambda f: (str(f.rel_path).count("/"), PRI[f.rel_path.name])).rel_path)
' 2>>"$log")
docker rm -f "disc_$key" >/dev/null 2>&1
[ -z "$lock" ] && { echo "NOJVMLOCK $slug"; exit 0; }

t0=$(date +%s)
docker rm -f "$cname" >/dev/null 2>&1
timeout -k 30 $RUN_TIMEOUT docker run --rm --name "$cname" \
  -v "$repo":/workspace -v "$cache":/cache -v "$OUT_ROOT/out":/out \
  -e HOME=/cache/home -e XDG_CACHE_HOME=/cache/xdg \
  -e SBOMIFY_CACHE_DIR=/cache/enrichment \
  -e SBOMIFY_ALLOW_GENERATOR_FALLBACK=1 \
  -e WORKING_DIR=/workspace -e LOCK_FILE="$lock" -e OUTPUT_FILE="/out/$key.cdx.json" \
  -e UPLOAD=false -e AUGMENT=true -e ENRICH=true -e TELEMETRY=false \
  -e COMPONENT_NAME="$(basename "$slug")" \
  "$IMAGE" >>"$log" 2>&1
rc=$?
docker rm -f "$cname" >/dev/null 2>&1
t1=$(date +%s)

insp='{}'
[ -s "$out" ] && insp=$(python3 "$EVAL_ROOT/inspect_sbom_v2.py" "$out")
python3 - "$eco" "$slug" "$lock" "$rc" "$((t1-t0))" "$slot" "$insp" > "$res" <<'PY'
import json,sys
eco,slug,lock,rc,dur,slot,insp = sys.argv[1:8]
print(json.dumps({"ecosystem":eco,"slug":slug,"lockfile":lock,"rc":int(rc),
                  "duration_s":int(dur),"slot":int(slot),"isolated":True,
                  "sbom":json.loads(insp)}))
PY
echo "JVM $slug rc=$rc lock=$lock dur=$((t1-t0))s slot=$slot"
