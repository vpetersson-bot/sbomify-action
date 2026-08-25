#!/usr/bin/env bash
# Which of the digests the push job mentioned is the build we actually want.
#
# Three merges landed on master within a minute and every one of their
# pipelines pushed :latest, so the tag records whichever finished last rather
# than whichever is newest. Here that is b3552bd (#374) while master's head is
# 589ee0c (#372) -- and #372 is the fix the re-run is meant to measure.
#
# So the tag is not usable as a way of naming a build. Ask each digest what
# version it reports instead.
set -uo pipefail
for d in "$@"; do
  ref="ghcr.io/sbomify/sbomify-action@sha256:$d"
  if docker pull -q "$ref" >/dev/null 2>&1; then
    v=$(docker run --rm --memory=1g --memory-swap=1g --entrypoint python3 "$ref" \
          -c 'import sbomify_action as m; print(m.__version__)' 2>/dev/null | tail -1)
    echo "${d:0:12} -> ${v:-(not a runnable image)}"
  else
    echo "${d:0:12} -> not pullable (likely an attestation or index entry)"
  fi
done
