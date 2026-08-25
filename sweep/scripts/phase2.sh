#!/usr/bin/env bash
# Pass 2: for every repo whose pass-1 target was off-stack, re-run against
# the best *on-stack* lockfile the wizard actually discovered.
#
# Answers the question pass 1 cannot: when discovery does surface the right
# lockfile and something else merely outranked it, does the tool produce a
# good SBOM from it? A yes means the defect is routing (cheap to fix); a no
# means the ecosystem genuinely is not readable (a real coverage gap).

set -uo pipefail
EVAL_ROOT=/home/ubuntu/sbomify-eval
cd "$EVAL_ROOT"

# Emit "ecosystem<TAB>slug<TAB>url<TAB>on-stack-lockfile" for the mismatches.
python3 - <<'PY' > /tmp/phase2.tsv
import csv, json, pathlib, sys
sys.path.insert(0, "/home/ubuntu/sbomify-eval")
from aggregate import ECO_OK, classify, eco_match, load

urls = {}
for row in csv.reader(open("/home/ubuntu/sbomify-eval/projects.tsv"), delimiter="\t"):
    if len(row) >= 4:
        urls[row[1]] = row[2]

# Rank on-stack candidates the way the wizard's own priority table does,
# preferring the shallowest path so a monorepo's root wins over its leaves.
PRI = {"uv.lock":10,"poetry.lock":11,"Pipfile.lock":12,"requirements.txt":13,"pyproject.toml":14,
       "bun.lock":20,"pnpm-lock.yaml":21,"yarn.lock":22,"package-lock.json":23,"package.json":24,
       "composer.lock":30,"composer.json":31,"go.sum":40,"go.mod":41,
       "gradle.lockfile":50,"build.gradle":51,"build.gradle.kts":52,"pom.xml":53,
       "Cargo.lock":55,"Cargo.toml":56,"Gemfile.lock":60,"pubspec.lock":61,
       "mix.lock":62,"conan.lock":63,"packages.lock.json":64,
       "Package.resolved":65,"Package.swift":66,"build.sbt":67,".terraform.lock.hcl":68}

out = []
for r in load():
    if r.get("kind") != "repo":
        continue
    # Only repos that produced something off-stack, or produced nothing at
    # all while an on-stack lockfile was sitting there unused.
    allowed = ECO_OK.get(r["ecosystem"], set())
    if not allowed or eco_match(r) is False:
        # eco_match False means no on-stack candidate exists -> nothing to retry.
        continue
    if classify(r).startswith("ok") and eco_match(r):
        continue  # already used the right stack
    cands = [d for d in r.get("discovered") or [] if d.get("ecosystem") in allowed]
    if not cands:
        continue
    best = min(cands, key=lambda d: (d["path"].count("/"),
                                     PRI.get(d["path"].split("/")[-1], 99), d["path"]))
    if best["path"] == r.get("target_lockfile"):
        continue  # pass 1 already pointed here; rerunning proves nothing
    url = urls.get(r["slug"])
    if url:
        out.append([r["ecosystem"], r["slug"], url, best["path"]])

csv.writer(sys.stdout, delimiter="\t", lineterminator="\n").writerows(out)
PY

n=$(wc -l < /tmp/phase2.tsv)
echo "phase 2: $n projects to re-run against an on-stack lockfile"
[ "$n" -eq 0 ] && exit 0

tr '\t' '\n' < /tmp/phase2.tsv | xargs -P "${JOBS:-4}" -n 4 "$EVAL_ROOT/run_best.sh"
echo "phase 2 complete: $(ls "$EVAL_ROOT/meta2" 2>/dev/null | wc -l) records"
