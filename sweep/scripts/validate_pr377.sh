#!/usr/bin/env bash
# The 15 projects that produce nothing today, run against both images.
#
# Selected from the corpus rather than chosen: these are every project in the
# 500 whose input was a manifest and whose document came back empty. Picking
# the ones likely to improve would prove nothing, and the failures here are
# as informative as the fixes -- a project with no runtime dependencies should
# still come back empty, and if this change "fixes" one of those it has
# invented dependencies.
#
# Both images run the same way, from the same clone, so the only variable is
# the code under test.
set -uo pipefail
ROOT=/home/ubuntu/sbomify-eval
OLD=ghcr.io/sbomify/sbomify-action@sha256:de0d338ff134cbbb78d0ff04742a7e9a9e568aceb3af4b199784712540023f00
NEW=sbomify-action:pr377
OUT=$ROOT/validate377
rm -rf "$OUT"; mkdir -p "$OUT"

run_one() {
  local image=$1 label=$2 repo=$3 lock=$4 name=$5 ref=$6 dir
  dir=$OUT/$name/$label
  mkdir -p "$dir"
  timeout 1800 docker run --rm --memory=4g --memory-swap=4g --oom-score-adj=1000 \
    -v "$repo":/workspace -v "$OUT/cache-$label":/cache -v "$dir":/out \
    -e HOME=/cache/home -e XDG_CACHE_HOME=/cache/xdg -e SBOMIFY_CACHE_DIR=/cache/enrichment \
    -e WORKING_DIR=/workspace -e LOCK_FILE="$lock" -e OUTPUT_FILE=/out/sbom.cdx.json \
    -e UPLOAD=false -e AUGMENT=true -e ENRICH=false -e TELEMETRY=false \
    -e COMPONENT_NAME="$name" ${ref:+-e GITHUB_REF="refs/tags/$ref"} \
    "$image" > "$dir/log" 2>&1
  echo $?
}

components() {
  python3 -c "
import json,sys
try:
    d=json.load(open('$1'))
    print(len(d.get('components') or []))
except Exception:
    print('-')
" 2>/dev/null
}

printf '%-30s %-28s %8s %8s   %s\n' PROJECT INPUT BEFORE AFTER NOTICE
while IFS=$'\t' read -r slug lock ref; do
  [ -z "${slug:-}" ] && continue
  name=$(basename "$slug")
  repo=$OUT/repos/$name
  git clone --depth 1 ${ref:+--branch "$ref"} --quiet "https://github.com/$slug.git" "$repo" 2>/dev/null || {
    printf '%-30s %-28s %8s %8s   clone failed\n' "$slug" "$lock" - -; continue; }

  run_one "$OLD" before "$repo" "$lock" "$name" "$ref" > /dev/null
  run_one "$NEW" after  "$repo" "$lock" "$name" "$ref" > /dev/null

  b=$(components "$OUT/$name/before/sbom.cdx.json")
  a=$(components "$OUT/$name/after/sbom.cdx.json")
  # grep -c already prints 0 when it matches nothing, and exits 1 while
  # doing it -- so `|| echo 0` appends a second zero and the variable
  # becomes "0\n0", which is not "0", which marked every single row as
  # disclosed. The harness was inventing the result it was built to check.
  mark="-"
  grep -q "INFERRED, NOT RECORDED" "$OUT/$name/after/log" 2>/dev/null && mark="disclosed"
  printf '%-30s %-28s %8s %8s   %s\n' "$slug" "$lock" "${b:--}" "${a:--}" "$mark"
done < "$ROOT/validate377.tsv"
