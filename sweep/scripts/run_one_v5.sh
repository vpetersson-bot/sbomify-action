#!/usr/bin/env bash
# Evaluate one released project end to end and leave a JSON record behind.
#
# The run mirrors what a user actually gets: the wizard's own discovery
# decides which lockfile is targeted, and the action runs in the published
# container with augmentation and enrichment on and upload off.
#
# Checked out at a release, not at the default branch. Every earlier sweep
# cloned master, which is the wrong subject: an SBOM describes something you
# ship, and nobody ships master. It also made findings unsafe to state. F6 --
# "placeholder root versions are pervasive" -- was measured entirely on
# default-branch checkouts, so the placeholder could as easily have been the
# harness's fault as the tool's, and a PR was opened to fix something that had
# never been shown to be broken. The action does not choose the checkout
# either: that is the workflow's decision, and the build it runs on is
# tag-triggered.
#
# 461 of the 500 resolve to a GitHub release or a version-sorted tag. The other
# 39 have neither and are run at their default branch, recorded as such so they
# can be excluded from any claim about released software instead of quietly
# diluting it.
#
# Strict mode is run first because that is the default. When it fails we run
# again with SBOMIFY_ALLOW_GENERATOR_FALLBACK=1, which separates two very
# different outcomes that otherwise look identical: "no tool in the image can
# read this project" versus "a working SBOM existed and strict mode refused
# it". Only the first is a coverage gap; the second is a routing bug.

set -uo pipefail

EVAL_ROOT=/home/ubuntu/sbomify-eval
OUT_ROOT=/home/ubuntu/sbomify-eval/v5

# Pinned by digest, not by tag: a run that takes most of a day should not have
# its subject change underneath it.
#
# 26.7.0+589ee0c -- master with every fix this evaluation produced, merged.
#
# Pinned to the multi-arch index by digest rather than to :latest, and not
# because pinning is tidier. Three merges landed within a minute and all
# three pipelines pushed :latest, so the tag records whichever finished
# last -- b3552bd (#374) -- while master's head is 589ee0c (#372). :latest
# was a build *older* than master and missing the fix this re-run exists to
# measure. The digest was recovered from the push job's log.
#
# Fixes carried:
#
#   #360  PHP bundle wiring          all 23 PHP projects
#   #361  cross-process bundle lock  concurrent runs, and the JVM cache paths
#   #363  build-wrapper fallback     kafka, flink and the JVM ecosystems
#   #367  tooling lockfiles          the 29 projects that had no root input
#   #368  version from release tag   opt-in, so inert here unless asked for
#   #369  prerelease detection       release records, not the SBOM itself
#   #371  composer root version      the PHP empty-SBOM case, Laravel and Symfony
#   #372  safe.directory for children  Composer can read the workspace at all
#   #373  relocatable Go caches      inert here; nothing overrides them
#   #374  root PURL identity         the 67 documents naming the mount point
#
# Measuring against a build that already superseded these is the footnote
# this whole exercise exists to avoid.
export IMAGE=sbomify-action:master-890c2eb

# The first pass at this corpus took the whole machine down at 115 of 249.
# Five uncapped Gradle builds ran on a 15 GB box that also hosts several
# long-lived dev stacks; at 19:42 the kernel OOM-killed two `java` processes
# holding 12.9 GB and 16.7 GB of address space, and by 19:53 it had worked its
# way to the user session's own systemd. That killed the tmux the sweep ran
# under, and the sweep with it -- so the run did not fail, it was collateral.
#
# Two settings, because a cap on its own does not protect the session:
#   --memory/--memory-swap  gives each run its own cgroup, so a build that
#                           wants more than its share dies as rc 137 inside
#                           that cgroup rather than starving the host. Swap is
#                           pinned equal to memory (i.e. none) because the
#                           box's 7.6 GB of zram is already 6.4 GB full.
#   --oom-score-adj=1000    makes these containers the kernel's first pick if
#                           the host runs short anyway. What dies is then
#                           always a repeatable eval run, never the session.
#
# rc 137 is recorded like any other failure, so a project killed at the cap
# stays distinguishable from one the tool genuinely could not read.
#: Ecosystems whose build genuinely needs the full cap. Everything else is a
#: lockfile parse or a small resolver, and giving it 4 GB reserves headroom
#: nothing will use.
#:
#: Sizing the cap per ecosystem is what makes three workers fit at all: the
#: box has about 8 GB of headroom, and 3 x 4 GB does not. With the
#: one-job-per-ecosystem rule below there can be at most one heavy build in
#: flight, so the worst case is 4 + 2 + 2 rather than 12.
_HEAVY_ECOSYSTEMS=" java kotlin scala android clojure "

if [ -n "${MEM:-}" ]; then
  :  # explicit override wins, for a single-project rerun
elif [[ $_HEAVY_ECOSYSTEMS == *" ${1:-} "* ]]; then
  MEM=4g
else
  MEM=2g
fi
# MEM=none removes the cap entirely, for judging a project the cap decided
# against. --oom-score-adj stays either way, and it is the part that actually
# protects the session: uncapped means the container may take the whole
# machine, and this makes the kernel pick the container first if it comes to
# that. Dropping the cap without keeping this is how the earlier sweep killed
# the tmux it was running under.
if [ "$MEM" = "none" ]; then
  LIMITS="--oom-score-adj=1000"
else
  LIMITS="--memory=$MEM --memory-swap=$MEM --oom-score-adj=1000"
fi

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

# The claim below is `mkdir "$OUT_ROOT/slots/$i.lock"`, and mkdir fails just as
# quietly when the parent is missing as when the lock is already held. Running
# this script outside the orchestrator -- a single-project smoke test, say --
# therefore spent twenty minutes waiting for a slot that could never appear,
# and would have spent eighty. Create the tree, then say so if a slot still
# cannot be had.
mkdir -p "$OUT_ROOT"/{meta,logs,out,repos,locks,slots,eco} 2>/dev/null || {
  echo "FATAL cannot create $OUT_ROOT" >&2
  exit 1
}

ecosystem=$1
slug=$2
target=$3
note=$4
#: The release to scan, or the sentinel @default for the 39 projects that have
#: never tagged anything. Carried into every record so a row can always say
#: what it measured -- a corpus that mixes released and unreleased software
#: without saying which is which is how the last one went wrong.
ref=${5:-@default}

key=$(printf '%s' "$slug" | tr '/:.' '___')
res=$OUT_ROOT/meta/$key.json

# Resume before claiming anything.
#
# This check used to sit after the slot claim, so a project that was already
# finished still queued for a slot in order to discover it had nothing to do.
# Normally that is a millisecond; with three stale slot locks it was eighty
# minutes of a worker sleeping to reach a one-line exit, and with the
# orchestrator now making repeated passes, every pass paid it for all 500.
# Nothing above this line touches shared state, so exiting here is free.
[ -s "$res" ] && { echo "SKIP $slug (done)"; exit 0; }

# A slot lock records its owner, so a lock left by a killed worker can be
# told from one that is genuinely held.
#
# pkill leaves them behind: bash does not run an EXIT trap when it is
# terminated while blocked in `sleep`, so every worker killed mid-wait leaks
# its slot. Three such locks meant no slot could ever be claimed and the whole
# sweep sat at zero utilisation with three healthy-looking processes.
slot=""
for _try in $(seq 1 480); do
  for i in $(seq 0 $((SLOTS-1))); do
    if mkdir "$OUT_ROOT/slots/$i.lock" 2>/dev/null; then
      echo $$ > "$OUT_ROOT/slots/$i.lock/owner"
      slot=$i
      break 2
    fi
    owner=$(cat "$OUT_ROOT/slots/$i.lock/owner" 2>/dev/null)
    if [ -n "$owner" ] && ! kill -0 "$owner" 2>/dev/null; then
      echo "reclaiming slot $i from dead worker $owner"
      rm -rf "$OUT_ROOT/slots/$i.lock"
    fi
  done
  sleep 10
done
[ -z "$slot" ] && { echo "NOSLOT $slug (all $SLOTS slots held for 80 minutes)"; exit 0; }
CACHE=$OUT_ROOT/slots/$slot.cache
mkdir -p "$CACHE"
CLONE_TIMEOUT=${CLONE_TIMEOUT:-900}
RUN_TIMEOUT=${RUN_TIMEOUT:-2100}
log=$OUT_ROOT/logs/$key.log
repo=$OUT_ROOT/repos/$key

# Re-checked now a slot is held: another worker in this pass may have finished
# the same project while this one waited. The cheap check above is the one that
# matters for throughput; this one closes the race.
[ -s "$res" ] && { echo "SKIP $slug (done while waiting)"; exit 0; }

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

# Arm the release the moment the lock exists, not once the run is set up.
#
# The trap used to be installed ~90 lines below this, after the ecosystem
# lock, the output directories and the clone. Every exit path in between left
# the project lock behind, and `run_one` treats an existing lock as "another
# worker has this" -- so the project was skipped for the rest of the sweep.
#
# That was survivable while those exits were rare. Shortening the ecosystem
# wait to 60 seconds made ECOBUSY the common case by design, and turned a rare
# leak into 44 of them: the sweep stopped at 456 of 500 with exactly 44
# orphaned locks and three passes that each skipped them instantly. The fix
# for the throughput problem created a correctness problem, and it was the
# ordering that made it possible.
#
# release_lock is defined below and only runs at exit, by which point it is;
# bash resolves the name when the trap fires, not when it is installed.
# The action runs as root and several generators build in-tree (setuptools
# leaves build/ and *.egg-info, gradle leaves .gradle), so the clone comes
# back with root-owned files we cannot unlink as ourselves. Delete it from a
# throwaway root container instead of asking for sudo.
release_lock() {
  rmdir "$lockdir" 2>/dev/null
  # rm -rf, not rmdir: the lock directory holds an `owner` file now, and
  # rmdir fails silently on a non-empty directory -- which would leak every
  # slot on every run and reproduce the stall this owner file exists to fix.
  [ -n "${slot:-}" ] && rm -rf "$OUT_ROOT/slots/$slot.lock" 2>/dev/null
  # Held only if we actually took it -- rmdir on someone else's ecosystem lock
  # would hand their ecosystem to a second worker, which is the one thing this
  # is here to prevent.
  [ -n "${eco_held:-}" ] && rmdir "${eco_lock:-}" 2>/dev/null
  # Gradle leaves a lock file behind on a hard kill; the rest of the slot
  # cache is worth keeping, since it holds the fetched bundles.
  rm -f "$CACHE"/xdg/sbomify/runtimes/bundle-jvm-*/.gradle/caches/journal-1/*.lock 2>/dev/null
  return 0
}

trap release_lock EXIT

# One project per ecosystem at a time.
#
# Two reasons, and the second is the one that matters. Two Gradle builds at
# once is what OOM-killed an earlier sweep, and it is also F16: the JVM bundle
# points GRADLE_USER_HOME at the shared runtime cache, so concurrent JVM builds
# corrupt each other's journal. Slot caches keep them apart today, but only
# because each worker has its own -- and that is a property of the harness, not
# something to keep relying on.
#
# With this rule, raising the worker count is safe: whatever three workers are
# doing, they are doing three different things, so at most one heavy build runs
# and the memory caps above add up to something the box has.
#
# The wait is bounded and gives up rather than hanging: the corpus is
# interleaved by ecosystem, so a worker should rarely find its ecosystem busy,
# and a project skipped here has no record and is simply picked up on the next
# pass -- resume is by record, not by position.
mkdir -p "$OUT_ROOT/eco"

# The heavy ecosystems share one lock, rather than having one each.
#
# This is a correction to the reasoning above, not a refinement of it. "One
# job per ecosystem" does not mean "one heavy build at a time": it stops two
# *java* jobs, not a java job beside a kotlin one, and there are five heavy
# ecosystems against three workers. Observed doing exactly that -- java and
# kotlin running together, both capped at 4 GB, the box at 0 free and swap
# 6 of 7 full.
#
# With one lock for the family the arithmetic is what it was claimed to be:
# at most one 4 GB build plus two 2 GB ones, which the host has room for. The
# cost is that the ~55 JVM-family projects serialise, which is the price of
# the guarantee rather than a regression.
lock_key=$ecosystem
[[ $_HEAVY_ECOSYSTEMS == *" $ecosystem "* ]] && lock_key=_heavy
eco_lock=$OUT_ROOT/eco/$lock_key.lock

# Wait briefly, then give the project back.
#
# Waiting long is worse than useless here. A worker blocked on this lock still
# occupies one of xargs' three parallel slots, so it cannot do anything else
# while it sleeps -- the wait buys nothing and costs a third of the machine.
#
# Observed at 85/500: all three workers on heavy projects at once
# (elasticsearch, kotlinx.coroutines, akka), one holding the lock and two
# asleep behind it, one container running on a three-worker sweep.
#
# That is not a scheduling accident and spreading the corpus cannot fix it.
# interleave_corpus.py places heavy projects at a stride so no window of three
# holds two, but light projects finish in seconds and heavy ones take twenty
# minutes, so the fast workers race ahead and pile up on the next heavy items
# regardless of stride. Any stride accumulates blocked workers eventually.
#
# So the wait is short and the project goes back in the queue. The orchestrator
# already makes repeated passes and resume is by record, so retrying is nearly
# free -- a finished project exits on the `[ -s "$res" ]` check before it
# claims anything. Sixty seconds is enough to catch a handoff that is about to
# happen without burning a slot on one that is not.
eco_held=""
for _try in $(seq 1 6); do
  if mkdir "$eco_lock" 2>/dev/null; then eco_held=1; break; fi
  sleep 10
done
if [ -z "$eco_held" ]; then
  echo "ECOBUSY $slug ($lock_key busy; returned to the queue for a later pass)"
  exit 0
fi

mkdir -p "$OUT_ROOT/meta" "$OUT_ROOT/logs" "$OUT_ROOT/out"
: > "$log"

emit() { printf '%s\n' "$1" > "$res"; }
jstr() { python3 -c 'import json,os,sys; print(json.dumps(sys.argv[1]))' "$1"; }


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
  # Its own directory too, for the same reason: the audit trail lands beside
  # OUTPUT_FILE, and a shared /out means one surviving trail for the lot.
  out_dir=$OUT_ROOT/out/$key/image
  mkdir -p "$out_dir"
  out=$out_dir/sbom.cdx.json
  timeout $RUN_TIMEOUT docker run --rm $LIMITS \
    -v "$CACHE":/cache -v "$out_dir":/out \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -e HOME=/cache/home -e XDG_CACHE_HOME=/cache/xdg -e SBOMIFY_CACHE_DIR=/cache/enrichment \
    -e DOCKER_IMAGE="$target" -e OUTPUT_FILE="/out/sbom.cdx.json" \
    -e UPLOAD=false -e AUGMENT=true -e ENRICH=true -e TELEMETRY=false \
    -e COMPONENT_NAME="$slug" \
    "$IMAGE" >>"$log" 2>&1
  rc=$?
  insp='{}'
  [ -s "$out" ] && insp=$(python3 "$EVAL_ROOT/inspect_sbom_v2.py" "$out")
  t_end=$(date +%s)
  emit "$(python3 - "$ecosystem" "$slug" "$note" "$rc" "$((t_end-t_start))" "$insp" "$ref" <<'PY'
import json,os,sys
eco,slug,note,rc,dur,insp,ref = sys.argv[1:8]
# A container is identified by its own tag, so the repository ref is not what
# was scanned here; recorded anyway so every row carries the same fields.
print(json.dumps({"ecosystem":eco,"slug":slug,"note":note,"image":os.environ.get("IMAGE",""),"kind":"container",
  "ref":ref,"released":ref!="@default",
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
# --branch takes a tag as happily as a branch, and with --depth 1 that fetches
# only the release commit -- the same shape a CI checkout has, at the ref a CI
# release build would be on.
clone_args=(--depth 1 --quiet)
[ "$ref" != "@default" ] && clone_args+=(--branch "$ref")
if ! timeout $CLONE_TIMEOUT git clone "${clone_args[@]}" "$target" "$repo" >>"$log" 2>&1; then
  emit "$(python3 - "$ecosystem" "$slug" "$note" "$ref" <<'PY'
import json,os,sys
eco,slug,note,ref = sys.argv[1:5]
print(json.dumps({"ecosystem":eco,"slug":slug,"note":note,"image":os.environ.get("IMAGE",""),"kind":"repo",
  "ref":ref,"released":ref!="@default",
  "error":"clone_failed","strict_rc":None,"discovered":[],"sbom":{}}))
PY
)"
  echo "CLONEFAIL $slug ($ref)"; exit 0
fi
repo_size=$(du -sm "$repo" 2>/dev/null | cut -f1)

# -------------------------------------------------------- discover and rank
# Both steps run inside the image, against the wizard's own discover() and its
# own _priority_of().
#
# The ranking used to be a copy of the wizard's priority table, kept here on
# the host. It had been truncated at Rust -- no Swift, no Ruby, no Dart, none
# of the .NET or JVM-adjacent entries -- so for any project whose real input
# was outside that subset, every candidate scored the default 99 and the tie
# broke alphabetically.
#
# Alamofire is what caught it. The wizard ranks Package.swift at 61 and has no
# entry for Gemfile.lock, so the wizard picks Package.swift. The copy here
# scored both 99, chose "Gemfile.lock" for coming first in the alphabet, and
# produced an SBOM describing Alamofire as pkg:gem/workspace@latest with 55
# fastlane gems in it. That is not a finding about the action; it is the
# harness feeding it the wrong file and then recording the result as the
# product's behaviour.
#
# Importing _priority_of instead of restating it is the same rule this project
# applies to sbom-tools: a second copy of a fact is a second thing to drift.
disc_and_lock=$(timeout 300 docker run --rm $LIMITS -v "$repo":/workspace:ro --entrypoint python3 "$IMAGE" -c '
import json
from pathlib import Path
from pathlib import PurePath
from sbomify_action.cli.wizard.discovery import discover, _priority_of
from sbomify_action.cli.wizard.screens.discover import _is_tooling
try:
    found = discover(Path("/workspace"), repo_name="'"$(basename "$slug")"'")
    rows = [{"path": str(f.rel_path), "ecosystem": f.ecosystem,
             "name": f.suggested_name,
             "depth": len(f.rel_path.parts),
             "nested_repo": f.nested_repo} for f in found]

    # Mirror the wizard'"'"'s _default_selected, which is what a user actually
    # arrives at: lockfiles inside submodules and vendored repos are listed
    # but NOT ticked, and only the shallowest depth that has anything
    # selectable is.
    #
    # Skipping that filter is how flutter/flutter came out targeting
    # third_party/wasmer/Cargo.toml -- a vendored Rust crate the wizard
    # would have left unticked -- and the resulting "Dart project resolved
    # as Rust" would have been recorded as the product falling through to an
    # incidental lockfile. It is the harness reaching past a guard the
    # product has.
    selectable = [r for r in rows if not r["nested_repo"]] or []

    # Tooling is excluded before the depth is measured, exactly as
    # _default_selected does it -- and this was missed the first time.
    #
    # The harness mirrored the nested-repo filter and the shallowest-depth
    # rule and simply omitted this one, so #367 -- the fix that stops the tool
    # defaulting to lockfiles describing how a project is built rather than
    # what it ships -- was never exercised by the corpus meant to demonstrate
    # it. curl was targeted at tests/requirements.txt, the precise case #367
    # exists to prevent, and 17 projects in all were handed an input the
    # product would not have chosen.
    #
    # Order matters as much as the filter: tooling is removed *first* and the
    # shallowest depth measured over what remains, so a tooling file nearer
    # the root cannot mask a real input deeper down. AutoMapper is the case --
    # docs/requirements.txt at depth 2 was hiding src/AutoMapper.csproj at
    # depth 3.
    #
    # `real or selectable` keeps the invariant the product holds: a repository
    # that is only tooling still gets scanned rather than yielding nothing.
    real = [r for r in selectable if not _is_tooling(PurePath(r["path"]))]
    selectable = real or selectable
    candidates = []
    if selectable:
        shallowest = min(r["depth"] for r in selectable)
        candidates = [r for r in selectable if r["depth"] == shallowest]
        # The wizard ticks every candidate at that depth; this evaluation
        # configures one component, so it takes the one the wizard ranks
        # first within the tier, by the wizard'"'"'s own _priority_of.
        #
        # ALL of them, not one. Taking the single best was a harness bug with
        # the same shape as the two above: _LOCKFILE_PRIORITY says in its own
        # comment that "priorities only compete within one ecosystem", and the
        # numbers are one global scale -- Python 10-14, JavaScript 20-24, Java
        # 50-53 -- so using it to break a tie *between* ecosystems does not
        # rank, it just prefers Python to everything.
        #
        # Measured over 114 records, 15 had a polyglot shallowest tier and
        # every one of them was scanned as the wrong language: rails/rails and
        # rust-lang/rust as yarn.lock, grafana/grafana as yarn.lock,
        # fastlane/fastlane as Package.resolved, apache/spark as
        # pyproject.toml. The wizard ticks every candidate at this depth and
        # the user gets a component for each; collapsing that to one was the
        # harness inventing a behaviour the product does not have.
        candidates.sort(key=lambda r: (_priority_of(r["path"].split("/")[-1]), r["path"]))
    print(json.dumps({"discovered": rows,
                      "targets": [{"path": r["path"], "ecosystem": r["ecosystem"]} for r in candidates]}))
except Exception as e:
    print(json.dumps({"discovered": [], "targets": [],
                      "error": f"{type(e).__name__}: {e}"}))
' 2>>"$log")
[ -z "$disc_and_lock" ] && disc_and_lock='{"discovered": [], "target": ""}'

disc=$(python3 -c 'import json,os,sys; print(json.dumps(json.loads(sys.argv[1]).get("discovered") or []))' "$disc_and_lock" 2>/dev/null || echo '[]')

# Every candidate the wizard would tick, as TAB-separated path and ecosystem.
#
# Capped, and the cap is recorded rather than applied quietly: a repository
# with a dozen root manifests would otherwise turn one project into a dozen
# container runs, and a corpus that silently scanned only some of what it
# found is the kind of thing this evaluation exists to catch in other people's
# tools.
targets_tsv=$(python3 -c '
import json,sys
ts = json.loads(sys.argv[1]).get("targets") or []
for t in ts[:5]:
    print(t["path"] + "\t" + (t.get("ecosystem") or ""))
' "$disc_and_lock" 2>/dev/null || echo "")
targets_found=$(python3 -c 'import json,sys; print(len(json.loads(sys.argv[1]).get("targets") or []))' "$disc_and_lock" 2>/dev/null || echo 0)
targets_run=$(printf '%s' "$targets_tsv" | grep -c . || true)
[ "${targets_found:-0}" -gt "${targets_run:-0}" ] &&
  echo "CAPPED $slug ($targets_found candidates at the shallowest depth, running $targets_run)"

lock=$(printf '%s' "$targets_tsv" | head -1 | cut -f1)

if [ -z "$lock" ]; then
  t_end=$(date +%s)
  emit "$(python3 - "$ecosystem" "$slug" "$note" "$disc" "$((t_end-t_start))" "${repo_size:-0}" "$ref" <<'PY'
import json,os,sys
eco,slug,note,disc,dur,size,ref = sys.argv[1:8]
print(json.dumps({"ecosystem":eco,"slug":slug,"note":note,"image":os.environ.get("IMAGE",""),"kind":"repo",
  "ref":ref,"released":ref!="@default",
  "error":"no_lockfile_discovered","strict_rc":None,"fallback_rc":None,
  "used_fallback":False,"duration_s":int(dur),"repo_mb":int(size),
  "discovered":json.loads(disc),"target_lockfile":None,"sbom":{}}))
PY
)"
  echo "NOLOCK $slug ($ref)"; exit 0
fi

# ------------------------------------------------------------------ run x2
# Every document produced is kept, under the mode that produced it.
#
# Both runs used to write the same path and the fallback deleted the strict
# output before starting, so any project that fell back lost its strict
# document -- and those are exactly the interesting ones. "Strict refused a
# perfectly good SBOM" and "strict was right and the fallback is worse" look
# identical once one of the two is gone, and the whole point of running twice
# is to tell them apart.
# One output directory per run, not one shared by all 500.
#
# The action writes its audit trail next to OUTPUT_FILE, so every project
# mounting the same /out wrote to the same `audit_trail.txt` and the last
# writer won: 500 runs, one surviving trail. The trail records where each
# augmented field came from, which is most of what "analyse the quality"
# means, so losing 499 of them empties the exercise.
#
# Per *run* rather than per project, because strict and fallback are separate
# containers and would otherwise clobber each other's trail the same way.
# Per target as well as per run, now that a polyglot root produces several.
target_slug() { printf '%s' "$1" | tr '/.' '__'; }

# The CI context a tag-triggered release workflow would supply.
#
# The corpus scans releases, and a release SBOM is produced by a workflow that
# ran *because* of the tag -- so GITHUB_REF is part of the scenario, not a
# thumb on the scale. Leaving it out measured something nobody runs.
#
# It is load-bearing. #371 fixes PHP by telling Composer the root package's
# version, and it sources that from COMPONENT_VERSION or the CI tag; with
# neither set the fix is inert. Measured on laravel/framework v13.24.0 with
# this image and nothing else changed:
#
#   without GITHUB_REF   strict rc 1, 0 components
#   with    GITHUB_REF   "Telling Composer this package is version 13.24.0",
#                        72 components
#
# So the first run of this sweep would have reported PHP as still broken, and
# the fault would have been the harness's.
#
# Only for projects that resolved to a real ref; the 39 default-branch
# projects get nothing, which is what an untagged build looks like.
ci_ref=""
[ "$ref" != "@default" ] && ci_ref="refs/tags/$ref"

run_action() {  # $1 = "" for strict, "1" for fallback; $2 = output dir; $3 = lock
  local fb=$1 dir=$2 this_lock=$3
  timeout $RUN_TIMEOUT docker run --rm $LIMITS \
    -v "$repo":/workspace -v "$CACHE":/cache -v "$dir":/out \
    -e HOME=/cache/home -e XDG_CACHE_HOME=/cache/xdg -e SBOMIFY_CACHE_DIR=/cache/enrichment \
    ${fb:+-e SBOMIFY_ALLOW_GENERATOR_FALLBACK=1} \
    -e WORKING_DIR=/workspace -e LOCK_FILE="$this_lock" \
    -e OUTPUT_FILE="/out/sbom.cdx.json" \
    -e UPLOAD=false -e AUGMENT=true -e ENRICH=true -e TELEMETRY=false \
    -e COMPONENT_NAME="$(basename "$slug")" \
    ${ci_ref:+-e GITHUB_REF="$ci_ref"} \
    "$IMAGE" >>"$log" 2>&1
}

# One pair of runs per candidate the wizard would have ticked.
runs_file=$OUT_ROOT/out/$key/runs.jsonl
# The per-target directories are created inside the loop below, so on a
# project whose output directory does not exist yet this truncate had nothing
# to write into and failed. It was survivable only by luck: the loop then
# created the directory and the appends worked, so the record came out right
# and the error went to stderr unread. Create it first.
mkdir -p "$OUT_ROOT/out/$key"
: > "$runs_file"

while IFS=$'\t' read -r this_lock this_eco; do
  [ -z "$this_lock" ] && continue
  tslug=$(target_slug "$this_lock")
  strict_dir=$OUT_ROOT/out/$key/$tslug/strict
  fallback_dir=$OUT_ROOT/out/$key/$tslug/fallback
  mkdir -p "$strict_dir" "$fallback_dir"
  strict_out=$strict_dir/sbom.cdx.json
  fallback_out=$fallback_dir/sbom.cdx.json

  echo "=== STRICT RUN (lock=$this_lock) ===" >>"$log"
  run_action "" "$strict_dir" "$this_lock"
  strict_rc=$?

  fallback_rc=null
  used_fallback=false
  if [ $strict_rc -ne 0 ]; then
    echo "=== FALLBACK RUN (lock=$this_lock) ===" >>"$log"
    run_action "1" "$fallback_dir" "$this_lock"
    fallback_rc=$?
    used_fallback=true
  fi

  # What a user would actually get: the strict document when strict succeeded,
  # otherwise the fallback's. Both stay on disk either way.
  out=$strict_out
  [ "$strict_rc" -ne 0 ] && [ -s "$fallback_out" ] && out=$fallback_out

  insp='{}'
  [ -s "$out" ] && insp=$(python3 "$EVAL_ROOT/inspect_sbom_v2.py" "$out")

  # Inspect the strict document separately when both exist, so the comparison
  # is in the record rather than something to recompute later.
  strict_insp='{}'
  if [ "$used_fallback" = true ] && [ -s "$strict_out" ]; then
    strict_insp=$(python3 "$EVAL_ROOT/inspect_sbom_v2.py" "$strict_out")
  fi

  python3 - "$this_lock" "$this_eco" "$strict_rc" "$fallback_rc" "$used_fallback" \
           "$insp" "$strict_insp" "$(basename "$(dirname "$out")")" >>"$runs_file" <<'PY'
import json,sys
lock,eco,src,fbrc,usedfb,insp,strict_insp,used_file = sys.argv[1:9]
print(json.dumps({"target_lockfile":lock,"target_ecosystem":eco,
  "sbom_file":used_file,
  "strict_sbom":json.loads(strict_insp) or None,
  "strict_rc":int(src),
  "fallback_rc":None if fbrc=="null" else int(fbrc),
  "used_fallback":usedfb=="true",
  "sbom":json.loads(insp)}))
PY
done <<< "$targets_tsv"

t_end=$(date +%s)

emit "$(python3 - "$ecosystem" "$slug" "$note" "$((t_end-t_start))" "${repo_size:-0}" \
        "$disc" "$ref" "$runs_file" "$targets_found" <<'PY'
import json,os,sys
eco,slug,note,dur,size,disc,ref,runs_file,found = sys.argv[1:10]
runs = [json.loads(l) for l in open(runs_file) if l.strip()]

# The headline run is the one whose input belongs to the project's own
# ecosystem, not the first by priority.
#
# rails/rails has yarn.lock and Gemfile.lock at the root; ranking them against
# each other picks the JavaScript one, and a table that then calls the row
# "ruby" is simply wrong. Every run is kept either way -- the polyglot answer
# is the interesting one -- but the row has to lead with the project's own
# language or the corpus reads as a survey of other people's asset pipelines.
head = next((r for r in runs if r.get("target_ecosystem") == eco), runs[0] if runs else None)

print(json.dumps({"ecosystem":eco,"slug":slug,"note":note,"image":os.environ.get("IMAGE",""),"kind":"repo",
  "ref":ref,"released":ref!="@default",
  "duration_s":int(dur),"repo_mb":int(size),
  "discovered":json.loads(disc),
  "targets_found":int(found),"runs":runs,
  # Flattened headline fields, so every consumer written against the
  # single-target record keeps working unchanged.
  "target_lockfile":(head or {}).get("target_lockfile"),
  "sbom_file":(head or {}).get("sbom_file"),
  "strict_sbom":(head or {}).get("strict_sbom"),
  "strict_rc":(head or {}).get("strict_rc"),
  "fallback_rc":(head or {}).get("fallback_rc"),
  "used_fallback":(head or {}).get("used_fallback", False),
  "sbom":(head or {}).get("sbom") or {}}))
PY
)"
echo "DONE $slug ($ref) ${targets_run} target(s)"
