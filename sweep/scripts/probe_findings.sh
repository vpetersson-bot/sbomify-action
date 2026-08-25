#!/usr/bin/env bash
# Re-check, against the pinned image, the findings that can be answered by
# inspecting the container rather than by running the corpus.
#
# The findings log was written across two sweeps while fixes were merging, and
# it has no status column, so some entries may already describe a build that
# no longer exists. The sweep will settle the behavioural ones; these are the
# ones that are just a question of what is in the image.
#
# Capped and deprioritised like everything else here: the 500-project sweep
# has two workers of its own in flight on a 15 GB box.
set -uo pipefail
IMAGE=ghcr.io/sbomify/sbomify-action@sha256:0a29db0020f59c8ed0b4d0ac3202346f2734d6fd6704b4139c8078207293da30
L="--memory=1g --memory-swap=1g --oom-score-adj=1000"

echo "image reports: $(docker run --rm $L --entrypoint python3 "$IMAGE" -c 'import sbomify_action as m; print(m.__version__)' 2>&1)"

echo
echo "F23 -- bootstrap tools a self-installing gradlew needs"
docker run --rm $L --entrypoint sh "$IMAGE" -c '
for t in curl wget unzip tar git; do
  command -v $t >/dev/null 2>&1 && echo "  present: $t" || echo "  MISSING: $t"
done' 2>&1

echo
echo "F18 -- PHP toolchain"
docker run --rm $L --entrypoint sh "$IMAGE" -c '
for t in php composer; do
  command -v $t >/dev/null 2>&1 && echo "  present: $t" || echo "  MISSING: $t"
done' 2>&1

echo
echo "F24 -- JDK shipped in the image"
docker run --rm $L --entrypoint sh "$IMAGE" -c '
if command -v java >/dev/null 2>&1; then java -version 2>&1 | head -1 | sed "s/^/  /"
else echo "  no java on PATH -- fetched as a runtime bundle instead"; fi' 2>&1

echo
echo "generators on PATH (the rest arrive as runtime bundles)"
docker run --rm $L --entrypoint sh "$IMAGE" -c '
for t in syft trivy cdxgen cyclonedx-py cargo-cyclonedx mvn gradle go npm; do
  command -v $t >/dev/null 2>&1 && echo "  present: $t" || echo "  absent:  $t"
done' 2>&1
