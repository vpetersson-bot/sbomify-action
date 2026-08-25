#!/usr/bin/env bash
# Is the PHP wiring from #360 actually present and reachable in this image?
#
# laravel/framework produced an empty SBOM with "Error running composer:" and
# no bundle fetch in the log, which is either #360 not doing what it should or
# composer failing for its own reasons. Worth knowing which before starting a
# ten-hour run whose PHP results depend on it.
set -uo pipefail
IMAGE=ghcr.io/sbomify/sbomify-action@sha256:4eb54dcafef3629fee22f8fc8e38c83d443972d78d8b8d476117ca3b3b13c300
L="--memory=1g --memory-swap=1g --oom-score-adj=1000"

docker run --rm -i $L --entrypoint python3 "$IMAGE" - <<'PY' 2>&1
import inspect

from sbomify_action._generation.generators import cdxgen
from sbomify_action import tool_manifest as tm

src = inspect.getsource(cdxgen)
print("ensure_php_installed referenced:", "ensure_php_installed" in src)
for line in src.splitlines():
    if "composer.json" in line or "ensure_php" in line:
        print("    ", line.strip())

print()
print("php bundle declared:", "php" in tm.load_bundles())
print("bundle_for('composer'):", tm.bundle_for("composer"))
PY
