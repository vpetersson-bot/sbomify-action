#!/usr/bin/env bash
# What does a run leave in the caller's checkout?
#
# Reading the code says "one lock file, removed in a finally". That is what the
# code intends; this asks the filesystem. bun may write a cache, a node_modules,
# or something nobody thought about, and the cleanup only removes the single
# path the resolver returns.
set -uo pipefail
D=/home/ubuntu/sbomify-eval/scratch/litter
rm -rf "$D"; mkdir -p "$D/out" "$D/cache"

git clone --depth 1 --branch v5.2.1 --quiet https://github.com/expressjs/express.git "$D/repo"
( cd "$D/repo" && find . -not -path './.git/*' -not -name .git | sort ) > "$D/before.txt"

docker run --rm --memory=4g --memory-swap=4g --oom-score-adj=1000 \
  -v "$D/repo":/workspace -v "$D/cache":/cache -v "$D/out":/out \
  -e HOME=/cache/home -e XDG_CACHE_HOME=/cache/xdg \
  -e WORKING_DIR=/workspace -e LOCK_FILE=package.json -e OUTPUT_FILE=/out/s.json \
  -e UPLOAD=false -e AUGMENT=true -e ENRICH=false -e TELEMETRY=false \
  -e COMPONENT_NAME=express \
  sbomify-action:pr377 > "$D/log" 2>&1
echo "run exit=$?"

( cd "$D/repo" && find . -not -path './.git/*' -not -name .git | sort ) > "$D/after.txt"
echo "--- left behind in the checkout:"
diff "$D/before.txt" "$D/after.txt" | grep '^>' || echo "  nothing"
echo "--- removed from the checkout:"
diff "$D/before.txt" "$D/after.txt" | grep '^<' || echo "  nothing"
