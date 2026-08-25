#!/usr/bin/env bash
# Replay ONE project from the worst-200 set against a new image.
#
# This is deliberately much thinner than run_one_v5.sh. A regression run holds
# every input constant and varies only the image, so all the machinery that
# script needs -- discovery, per-ecosystem priority, multi-target selection,
# eco locks -- is not just unnecessary here, it is exactly the machinery that
# manufactured findings last time by approximating product decisions. The
# targets are already recorded; this script does not choose anything.
#
#   usage: replay_one.sh <slug> <ref> <target-lockfile-or-empty>
#
# Env: IMAGE (required, digest-pinned), OUT_ROOT, CACHE, RUN_TIMEOUT, MEM.
set -uo pipefail

slug=$1; ref=$2; target=${3:-}
key=$(echo "$slug" | tr '/' '_')

# Resolve sibling scripts relative to this file. The summariser used to be
# referenced by an absolute /home/ubuntu path, which on any other machine
# silently failed and recorded `null` for every SBOM -- the runs succeeded,
# the numbers were simply absent, which is the worst way for a harness to
# break because nothing looks wrong until analysis.
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

OUT_ROOT=${OUT_ROOT:?}; IMAGE=${IMAGE:?}
CACHE=${CACHE:-$OUT_ROOT/cache}
RUN_TIMEOUT=${RUN_TIMEOUT:-900}
MEM=${MEM:-2g}
meta=$OUT_ROOT/meta/$key.json
log=$OUT_ROOT/logs/$key.log

mkdir -p "$OUT_ROOT/meta" "$OUT_ROOT/logs" "$OUT_ROOT/out" "$CACHE"

# Resume: a populated record means this project is done.
if [ -s "$meta" ]; then echo "SKIP $slug"; exit 0; fi

# Disk guard. A sweep that fills the disk corrupts every record still being
# written, not just its own, so refuse to start rather than fail halfway.
# Check the filesystem the output actually lands on, not a hardcoded home
# directory -- the original read /home/ubuntu, which does not exist on a box
# where the user is not `ubuntu`, and df's error left avail_gb empty so every
# project aborted with "only G free".
avail_gb=$(df -BG --output=avail "$OUT_ROOT" | tail -1 | tr -dc '0-9')
if [ "${avail_gb:-0}" -lt 15 ]; then
  echo "ABORT $slug: only ${avail_gb}G free" >&2; exit 3
fi

: > "$log"
work=$(mktemp -d "$OUT_ROOT/work.XXXXXX")
repo=$work/repo
# The container runs as root and writes into the bind-mounted clone -- Gradle
# build output, .gradle, node_modules -- so those files end up root-owned and
# a plain rm as `ubuntu` cannot remove them. Left unfixed the work directories
# leak one clone per project, which is how 64G of unreachable cache
# accumulated under v5/slots. sudo -n so a box without passwordless sudo fails
# loudly here rather than silently filling the disk.
cleanup() { rm -rf "$work" 2>/dev/null || sudo -n rm -rf "$work"; }
trap cleanup EXIT

url="https://github.com/$slug.git"
if [ "$ref" = "@default" ]; then
  git clone --depth 1 --quiet "$url" "$repo" >>"$log" 2>&1
else
  git clone --depth 1 --branch "$ref" --quiet "$url" "$repo" >>"$log" 2>&1
fi
if [ ! -d "$repo" ]; then
  printf '{"slug":"%s","ref":"%s","error":"clone failed"}\n' "$slug" "$ref" > "$meta"
  echo "CLONEFAIL $slug"; exit 0
fi

ci_ref=""
[ "$ref" != "@default" ] && ci_ref="refs/tags/$ref"

outdir=$OUT_ROOT/out/$key
rm -rf "$outdir"; mkdir -p "$outdir/strict" "$outdir/fallback"

# Same invocation as v5, so the two records are comparable. COMPONENT_NAME is
# kept -- including its known effect of naming the root after the repo -- for
# the same reason: changing an input would make a diff unattributable to the
# image. It does mean this run cannot see naming defects.
# Running the container as the invoking user makes the clone cleanable
# without sudo, which is the honest fix for the root-ownership leak. It is
# opt-in and OFF by default because it changes an input: a generator that
# needs to write into HOME or a cache may behave differently as a non-root
# user, and a regression sweep cannot afford an unvalidated input change.
# Prove it produces identical output before turning it on.
USEROPT=""
[ "${RUN_AS_HOST_USER:-0}" = "1" ] && USEROPT="--user $(id -u):$(id -g)"

# MEM=none removes the cap entirely. A cap that is too low does not merely
# slow a project down, it fabricates findings: at 2g every Gradle project
# died with "Gradle build daemon disappeared unexpectedly", which reads in the
# results exactly like an architecture defect. The JVM needs far more than the
# median project, so JVM-heavy work wants a bigger cap or none at all.
MEMOPT="--memory=$MEM"
[ "$MEM" = "none" ] && MEMOPT=""

run_action() {
  local fb=$1 dir=$2
  timeout "$RUN_TIMEOUT" docker run --rm $MEMOPT --oom-score-adj=1000 $USEROPT \
    -v "$repo":/workspace -v "$CACHE":/cache -v "$dir":/out \
    -e HOME=/cache/home -e XDG_CACHE_HOME=/cache/xdg -e SBOMIFY_CACHE_DIR=/cache/enrichment \
    ${fb:+-e SBOMIFY_ALLOW_GENERATOR_FALLBACK=1} \
    -e WORKING_DIR=/workspace ${target:+-e LOCK_FILE="$target"} \
    -e OUTPUT_FILE="/out/sbom.cdx.json" \
    -e UPLOAD=false -e AUGMENT=true -e ENRICH=true -e TELEMETRY=false \
    -e COMPONENT_NAME="$(basename "$slug")" \
    ${ci_ref:+-e GITHUB_REF="$ci_ref"} \
    "$IMAGE" >>"$log" 2>&1
}

start=$(date +%s)
echo "=== STRICT (lock=${target:-<discover>}) ===" >>"$log"
run_action "" "$outdir/strict"; strict_rc=$?
echo "=== FALLBACK ===" >>"$log"
run_action 1 "$outdir/fallback"; fallback_rc=$?
dur=$(( $(date +%s) - start ))

# Reuse the v5 summariser rather than restating what "good" means here.
summarise() {
  local f=$1
  if [ -s "$f" ]; then python3 "$HERE/inspect_sbom_v2.py" "$f" 2>/dev/null || echo 'null'
  else echo 'null'; fi
}
strict_sbom=$(summarise "$outdir/strict/sbom.cdx.json")
fallback_sbom=$(summarise "$outdir/fallback/sbom.cdx.json")

# Did the product disclose inferred resolution? Grep the log for the banner
# the shipped code writes; recorded as a fact, judged later.
disclosed=false
grep -qi "INFERRED, NOT RECORDED" "$log" && disclosed=true

# A failure that explains itself is a different outcome from a failure that
# does not, and rc alone cannot tell them apart. Alamofire still exits 1 --
# Package.swift genuinely cannot be resolved without Package.resolved -- but
# it now names the command to fix it. That is the difference between a bug and
# a documented limitation, which is the whole question this sweep is asking.
advised=false
grep -qiE "run \`(swift package resolve|cargo generate-lockfile|composer update|uv lock|npm install|bundle install|mix deps.get)|point LOCK_FILE at it|then commit" "$log" && advised=true

# Bug signals, as opposed to outcomes. A graceful refusal is the product
# working; an unhandled exception is the product breaking, and the two are
# indistinguishable by exit code -- both are rc=1. Capture the first
# traceback's final line, which is the exception type and message, so a sweep
# can be triaged by defect rather than by return code.
traceback=false
crash_line=""
if grep -q "Traceback (most recent call last)" "$log"; then
  traceback=true
  crash_line=$(grep -aE "^[A-Za-z_.]+(Error|Exception|Warning):" "$log" | head -1 | cut -c1-300)
fi
# Anything the runtime itself killed: OOM, segfault, a tool that vanished.
killed=false
grep -qiE "Killed|Out of memory|Segmentation fault|MemoryError|No space left" "$log" && killed=true

python3 - "$meta" "$slug" "$ref" "$target" "$strict_rc" "$fallback_rc" "$dur" \
         "$disclosed" "$advised" "$traceback" "$crash_line" "$killed" "$(uname -m)" \
         "$IMAGE" "$strict_sbom" "$fallback_sbom" <<'PY'
import json, sys
(path, slug, ref, target, srx, fbrx, dur, disclosed, advised,
 tb, crash, killed, arch, image, ss, fs) = sys.argv[1:17]
def j(s):
    try: return json.loads(s)
    except Exception: return None
rec = {
    "slug": slug, "ref": ref, "target_lockfile": target or None,
    "strict_rc": int(srx), "fallback_rc": int(fbrx),
    "used_fallback": int(srx) != 0 and int(fbrx) == 0,
    "duration_s": int(dur), "disclosed_inferred": disclosed == "true",
    "recommended_action": advised == "true",
    "traceback": tb == "true", "crash_line": crash or None,
    "killed": killed == "true", "arch": arch,
    "image": image, "strict_sbom": j(ss), "fallback_sbom": j(fs),
}
with open(path, "w") as fh:
    json.dump(rec, fh)
PY

echo "DONE $slug strict=$strict_rc fb=$fallback_rc ${dur}s"
