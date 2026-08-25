#!/usr/bin/env bash
# One real run of express against the locally built image.
#
# The unit tests cover the pieces; this checks the feature still works after
# the review pass rewrote the function around them -- the document is now
# mutated in place rather than deep-copied, and written compact rather than
# pretty-printed, and neither of those is visible to a unit test that only
# reads back properties.
set -uo pipefail
D=/home/ubuntu/sbomify-eval/scratch/recheck

docker run --rm --memory=4g --memory-swap=4g --oom-score-adj=1000 \
  -v "$D/repo":/workspace -v "$D/cache":/cache -v "$D/out":/out \
  -e HOME=/cache/home -e XDG_CACHE_HOME=/cache/xdg \
  -e WORKING_DIR=/workspace -e LOCK_FILE=package.json -e OUTPUT_FILE=/out/s.json \
  -e UPLOAD=false -e AUGMENT=true -e ENRICH=false -e TELEMETRY=false \
  -e COMPONENT_NAME=express \
  sbomify-action:pr377 > "$D/log" 2>&1
echo "exit=$?"

python3 - <<'PY'
import json, pathlib
d = json.loads(pathlib.Path("/home/ubuntu/sbomify-eval/scratch/recheck/out/s.json").read_text())
print("components:", len(d.get("components") or []))
for p in (d.get("metadata") or {}).get("properties") or []:
    if p["name"].startswith("sbomify:resolution"):
        print(" ", p["name"], "=", p["value"][:70])
root = (d.get("metadata") or {}).get("component") or {}
print("root:", root.get("name"), "|", root.get("purl"))
repo = pathlib.Path("/home/ubuntu/sbomify-eval/scratch/recheck/repo")
left = [f.name for f in repo.glob("bun.lock*")]
print("lock files we left behind:", left or "none")
raw = pathlib.Path("/home/ubuntu/sbomify-eval/scratch/recheck/out/s.json").read_text()
print("written compact:", "\n" not in raw.strip()[:-1])
PY
