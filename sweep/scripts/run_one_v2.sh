#!/usr/bin/env bash
# Evaluate one project end to end and leave a JSON record behind.
#
# The run mirrors what a user actually gets: the wizard's own discovery
# decides which lockfile is targeted, and the action runs in the published
# container with augmentation and enrichment on and upload off.
#
# Strict mode is run first because that is the default. When it fails we run
# again with SBOMIFY_ALLOW_GENERATOR_FALLBACK=1, which separates two very
# different outcomes that otherwise look identical: "no tool in the image can
# read this project" versus "a working SBOM existed and strict mode refused
# it". Only the first is a coverage gap; the second is a routing bug.

set -uo pipefail

EVAL_ROOT=/home/ubuntu/sbomify-eval
OUT_ROOT=/home/ubuntu/sbomify-eval/v2
IMAGE=ghcr.io/sbomify/sbomify-action:latest

# The user's global gitconfig rewrites https://github.com/ to git@github.com:,
# and port 22 is closed here. Point git at an empty config of our own rather
# than editing theirs, so clones stay on HTTPS.
export GIT_CONFIG_GLOBAL=$EVAL_ROOT/gitconfig
# One runtime cache per concurrent slot, not one shared by all workers.
#
# F16: the JVM bundle pins GRADLE_USER_HOME, maven.repo.local and SBT_OPTS to
# paths inside the runtime cache, and runtimes.py assigns that env directly
# rather than with setdefault, so passing those variables in does nothing. Two
# JVM projects sharing a cache corrupt each other's Gradle journal, which is
# what made the first survey's Java numbers unusable and forced a separate
# isolated re-run. A slot is claimed for one project and reused by the next,
# so each bundle is fetched once per slot rather than once per project.
SLOTS=${SLOTS:-5}
slot=""
for _try in $(seq 1 480); do
  for i in $(seq 0 $((SLOTS-1))); do
    if mkdir "$OUT_ROOT/slots/$i.lock" 2>/dev/null; then slot=$i; break 2; fi
  done
  sleep 10
done
[ -z "$slot" ] && { echo "NOSLOT $2"; exit 0; }
CACHE=$OUT_ROOT/slots/$slot.cache
mkdir -p "$CACHE"
CLONE_TIMEOUT=${CLONE_TIMEOUT:-900}
RUN_TIMEOUT=${RUN_TIMEOUT:-2100}

ecosystem=$1
slug=$2
target=$3
note=$4

key=$(printf '%s' "$slug" | tr '/:.' '___')
res=$OUT_ROOT/meta/$key.json
log=$OUT_ROOT/logs/$key.log
repo=$OUT_ROOT/repos/$key

# Resume: a finished record is never redone.
[ -s "$res" ] && { echo "SKIP $slug (done)"; exit 0; }

# Claim the project before doing any work. mkdir is atomic on a local
# filesystem, so two orchestrators sharing this tree can run side by side
# without both cloning into the same directory. The lock is released on
# exit; a stale one left by a killed run is cleared by hand, not on a
# timer, because a long clone is indistinguishable from a dead worker.
lockdir=$OUT_ROOT/locks/$key
mkdir -p "$OUT_ROOT/locks"
if ! mkdir "$lockdir" 2>/dev/null; then
  echo "BUSY $slug (claimed by another worker)"; exit 0
fi

mkdir -p "$OUT_ROOT/meta" "$OUT_ROOT/logs" "$OUT_ROOT/out"
: > "$log"

emit() { printf '%s\n' "$1" > "$res"; }
jstr() { python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$1"; }

# The action runs as root and several generators build in-tree (setuptools
# leaves build/ and *.egg-info, gradle leaves .gradle), so the clone comes
# back with root-owned files we cannot unlink as ourselves. Delete it from a
# throwaway root container instead of asking for sudo.
release_lock() {
  rmdir "$lockdir" 2>/dev/null
  [ -n "${slot:-}" ] && rmdir "$OUT_ROOT/slots/$slot.lock" 2>/dev/null
  # Gradle leaves a lock file behind on a hard kill; the rest of the slot
  # cache is worth keeping, since it holds the fetched bundles.
  rm -f "$CACHE"/xdg/sbomify/runtimes/bundle-jvm-*/.gradle/caches/journal-1/*.lock 2>/dev/null
  return 0
}
trap release_lock EXIT

cleanup() {
  [ -d "$repo" ] || return 0
  rm -rf "$repo" 2>/dev/null
  [ -d "$repo" ] && docker run --rm -v "$OUT_ROOT/repos":/r alpine:3 \
      rm -rf "/r/$key" >/dev/null 2>&1
  return 0
}
trap 'cleanup; release_lock' EXIT

t_start=$(date +%s)

# ---------------------------------------------------------------- container
# The docker path takes no clone and no discovery: the image reference is the
# input, so DOCKER_IMAGE goes straight to the action.
if [ "$ecosystem" = "docker" ]; then
  out=$OUT_ROOT/out/$key.cdx.json
  timeout $RUN_TIMEOUT docker run --rm \
    -v "$CACHE":/cache -v "$OUT_ROOT/out":/out \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -e HOME=/cache/home -e XDG_CACHE_HOME=/cache/xdg -e SBOMIFY_CACHE_DIR=/cache/enrichment \
    -e DOCKER_IMAGE="$target" -e OUTPUT_FILE="/out/$key.cdx.json" \
    -e UPLOAD=false -e AUGMENT=true -e ENRICH=true -e TELEMETRY=false \
    -e COMPONENT_NAME="$slug" \
    "$IMAGE" >>"$log" 2>&1
  rc=$?
  insp='{}'
  [ -s "$out" ] && insp=$(python3 "$EVAL_ROOT/inspect_sbom_v2.py" "$out")
  t_end=$(date +%s)
  emit "$(python3 - "$ecosystem" "$slug" "$note" "$rc" "$((t_end-t_start))" "$insp" <<'PY'
import json,sys
eco,slug,note,rc,dur,insp = sys.argv[1:7]
print(json.dumps({"ecosystem":eco,"slug":slug,"note":note,"kind":"container",
  "strict_rc":int(rc),"fallback_rc":None,"used_fallback":False,
  "duration_s":int(dur),"discovered":[],"target_lockfile":None,
  "sbom":json.loads(insp)}))
PY
)"
  echo "DONE $slug rc=$rc"
  exit 0
fi

# -------------------------------------------------------------------- clone
# A previous attempt may have left a root-owned tree here (the action builds
# in-tree as root); git refuses to clone into it. Clear it the same way the
# exit trap does before trying.
cleanup
if ! timeout $CLONE_TIMEOUT git clone --depth 1 --quiet "$target" "$repo" >>"$log" 2>&1; then
  emit "$(python3 - "$ecosystem" "$slug" "$note" <<'PY'
import json,sys
eco,slug,note = sys.argv[1:4]
print(json.dumps({"ecosystem":eco,"slug":slug,"note":note,"kind":"repo",
  "error":"clone_failed","strict_rc":None,"discovered":[],"sbom":{}}))
PY
)"
  echo "CLONEFAIL $slug"; exit 0
fi
repo_size=$(du -sm "$repo" 2>/dev/null | cut -f1)

# ----------------------------------------------------------------- discover
# Run the wizard's own discover() so the report describes what the wizard
# would put in front of a user, not a reimplementation of it.
disc=$(timeout 300 docker run --rm -v "$repo":/workspace:ro --entrypoint python3 "$IMAGE" -c '
import json
from pathlib import Path
from sbomify_action.cli.wizard.discovery import discover
try:
    found = discover(Path("/workspace"), repo_name="'"$(basename "$slug")"'")
    print(json.dumps([{"path": str(f.rel_path), "ecosystem": f.ecosystem,
                       "name": f.suggested_name} for f in found]))
except Exception as e:
    print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
' 2>>"$log")
[ -z "$disc" ] && disc='[]'

# The wizard lists every hit; a user configuring one component takes the
# first. Rank by the wizard's own priority table so "first" here means the
# same thing it means in the UI.
lock=$(python3 - "$disc" <<'PY'
import json,sys
PRI = {"uv.lock":10,"poetry.lock":11,"Pipfile.lock":12,"requirements.txt":13,"pyproject.toml":14,
       "bun.lock":20,"pnpm-lock.yaml":21,"yarn.lock":22,"package-lock.json":23,"package.json":24,
       "composer.lock":30,"composer.json":31,"go.sum":40,"go.mod":41,
       "gradle.lockfile":50,"build.gradle":51,"build.gradle.kts":52,"pom.xml":53,
       "Cargo.lock":55,"Cargo.toml":56}
try:
    d = json.loads(sys.argv[1])
    if not isinstance(d, list) or not d: print(""); raise SystemExit
    # Root-level lockfiles first: a monorepo's nested ones are not what a
    # user configuring the top-level component would pick.
    best = min(d, key=lambda f: (f["path"].count("/"), PRI.get(f["path"].split("/")[-1], 99), f["path"]))
    print(best["path"])
except Exception:
    print("")
PY
)

if [ -z "$lock" ]; then
  t_end=$(date +%s)
  emit "$(python3 - "$ecosystem" "$slug" "$note" "$disc" "$((t_end-t_start))" "${repo_size:-0}" <<'PY'
import json,sys
eco,slug,note,disc,dur,size = sys.argv[1:7]
print(json.dumps({"ecosystem":eco,"slug":slug,"note":note,"kind":"repo",
  "error":"no_lockfile_discovered","strict_rc":None,"fallback_rc":None,
  "used_fallback":False,"duration_s":int(dur),"repo_mb":int(size),
  "discovered":json.loads(disc),"target_lockfile":None,"sbom":{}}))
PY
)"
  echo "NOLOCK $slug"; exit 0
fi

# ------------------------------------------------------------------ run x2
out=$OUT_ROOT/out/$key.cdx.json
run_action() {  # $1 = extra env flag value ("" or "1")
  local fb=$1
  timeout $RUN_TIMEOUT docker run --rm \
    -v "$repo":/workspace -v "$CACHE":/cache -v "$OUT_ROOT/out":/out \
    -e HOME=/cache/home -e XDG_CACHE_HOME=/cache/xdg -e SBOMIFY_CACHE_DIR=/cache/enrichment \
    ${fb:+-e SBOMIFY_ALLOW_GENERATOR_FALLBACK=1} \
    -e WORKING_DIR=/workspace -e LOCK_FILE="$lock" \
    -e OUTPUT_FILE="/out/$key.cdx.json" \
    -e UPLOAD=false -e AUGMENT=true -e ENRICH=true -e TELEMETRY=false \
    -e COMPONENT_NAME="$(basename "$slug")" \
    "$IMAGE" >>"$log" 2>&1
}

echo "=== STRICT RUN (lock=$lock) ===" >>"$log"
run_action ""
strict_rc=$?

fallback_rc=null
used_fallback=false
if [ $strict_rc -ne 0 ]; then
  rm -f "$out"
  echo "=== FALLBACK RUN ===" >>"$log"
  run_action "1"
  fallback_rc=$?
  used_fallback=true
fi

insp='{}'
[ -s "$out" ] && insp=$(python3 "$EVAL_ROOT/inspect_sbom_v2.py" "$out")
t_end=$(date +%s)

emit "$(python3 - "$ecosystem" "$slug" "$note" "$strict_rc" "$fallback_rc" "$used_fallback" \
        "$((t_end-t_start))" "${repo_size:-0}" "$disc" "$lock" "$insp" <<'PY'
import json,sys
eco,slug,note,src,fbrc,usedfb,dur,size,disc,lock,insp = sys.argv[1:12]
print(json.dumps({"ecosystem":eco,"slug":slug,"note":note,"kind":"repo",
  "strict_rc":int(src),
  "fallback_rc":None if fbrc=="null" else int(fbrc),
  "used_fallback":usedfb=="true","duration_s":int(dur),"repo_mb":int(size),
  "discovered":json.loads(disc),"target_lockfile":lock,
  "sbom":json.loads(insp)}))
PY
)"
echo "DONE $slug strict=$strict_rc fb=$fallback_rc"
