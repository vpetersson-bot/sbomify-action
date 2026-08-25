#!/usr/bin/env bash
# Re-measure the JVM projects serially, each with a private cache.
#
# Pass 1 ran ten containers against one XDG_CACHE_HOME, and Gradle takes an
# exclusive lock on its journal inside GRADLE_USER_HOME -- so concurrent
# builds reported "Timeout waiting to lock journal cache" whatever the
# project. That is a property of how the harness was run, not of the action,
# and it has to be removed before any claim about Java support is credible.
#
# Serial, one private cache directory per project. Slower by design.

set -uo pipefail
EVAL_ROOT=/home/ubuntu/sbomify-eval
IMAGE=ghcr.io/sbomify/sbomify-action:latest
export GIT_CONFIG_GLOBAL=$EVAL_ROOT/gitconfig
RUN_TIMEOUT=${RUN_TIMEOUT:-2400}

mkdir -p "$EVAL_ROOT"/{meta_jvm,logs_jvm,out_jvm}

# The JVM stacks: java and scala. Read from the same project list so the
# report cannot drift from it.
awk -F'\t' 'NR>1 && ($1=="java" || $1=="scala"){print $1"\t"$2"\t"$3}' \
    "$EVAL_ROOT/projects.tsv" | while IFS=$'\t' read -r eco slug url; do
  key=$(printf '%s' "$slug" | tr '/:.' '___')
  res=$EVAL_ROOT/meta_jvm/$key.json
  [ -s "$res" ] && { echo "SKIP $slug"; continue; }

  repo=$EVAL_ROOT/repos/${key}__jvm
  cache=$EVAL_ROOT/cache_jvm/$key
  log=$EVAL_ROOT/logs_jvm/$key.log
  out=$EVAL_ROOT/out_jvm/$key.cdx.json

  wipe() {
    for d in "$repo" "$cache"; do
      rm -rf "$d" 2>/dev/null
      [ -d "$d" ] && docker run --rm -v "$(dirname "$d")":/p alpine:3 \
          rm -rf "/p/$(basename "$d")" >/dev/null 2>&1
    done
  }
  wipe
  mkdir -p "$cache"
  : > "$log"

  if ! timeout 900 git clone --depth 1 --quiet "$url" "$repo" >>"$log" 2>&1; then
    echo "CLONEFAIL $slug"; wipe; continue
  fi

  # Same discovery the wizard does, then take the JVM entry specifically --
  # this pass is about whether the Java toolchain can read a Java project,
  # so pointing it at a stray pyproject.toml would answer a different
  # question (that one is F3, and already measured).
  lock=$(timeout 300 docker run --rm -v "$repo":/workspace:ro --entrypoint python3 "$IMAGE" -c '
import json
from pathlib import Path
from sbomify_action.cli.wizard.discovery import discover
PRI = {"gradle.lockfile":50,"build.gradle":51,"build.gradle.kts":52,"pom.xml":53,"build.sbt":54}
found = [f for f in discover(Path("/workspace")) if f.rel_path.name in PRI]
if found:
    best = min(found, key=lambda f: (str(f.rel_path).count("/"), PRI[f.rel_path.name]))
    print(best.rel_path)
' 2>>"$log")

  if [ -z "$lock" ]; then echo "NOJVMLOCK $slug"; wipe; continue; fi

  t0=$(date +%s)
  timeout $RUN_TIMEOUT docker run --rm \
    -v "$repo":/workspace -v "$cache":/cache -v "$EVAL_ROOT/out_jvm":/out \
    -e HOME=/cache/home -e XDG_CACHE_HOME=/cache/xdg -e SBOMIFY_CACHE_DIR=/cache/enrichment \
    -e SBOMIFY_ALLOW_GENERATOR_FALLBACK=1 \
    -e WORKING_DIR=/workspace -e LOCK_FILE="$lock" -e OUTPUT_FILE="/out/$key.cdx.json" \
    -e UPLOAD=false -e AUGMENT=true -e ENRICH=true -e TELEMETRY=false \
    -e COMPONENT_NAME="$(basename "$slug")" \
    "$IMAGE" >>"$log" 2>&1
  rc=$?
  t1=$(date +%s)

  insp='{}'
  [ -s "$out" ] && insp=$(python3 "$EVAL_ROOT/inspect_sbom.py" "$out")
  python3 - "$eco" "$slug" "$lock" "$rc" "$((t1-t0))" "$insp" > "$res" <<'PY'
import json,sys
eco,slug,lock,rc,dur,insp = sys.argv[1:7]
print(json.dumps({"ecosystem":eco,"slug":slug,"lockfile":lock,"rc":int(rc),
                  "duration_s":int(dur),"sbom":json.loads(insp)}))
PY
  echo "JVM $slug rc=$rc lock=$lock dur=$((t1-t0))s"
  wipe
done
echo "jvm pass complete"
