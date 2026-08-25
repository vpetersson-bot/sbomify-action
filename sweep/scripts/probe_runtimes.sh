#!/usr/bin/env bash
# What runtime bundles does the pinned image know how to fetch?
#
# A bare `command -v php` says almost nothing now: #320 moved every non-Python
# tool out of the image and into bundles fetched on first use, so *everything*
# is absent from PATH in a cold container. The question F18 and F24 actually
# ask is whether a bundle exists and what it pins -- which lives in the
# runtimes registry, not on PATH.
set -uo pipefail
IMAGE=ghcr.io/sbomify/sbomify-action@sha256:0a29db0020f59c8ed0b4d0ac3202346f2734d6fd6704b4139c8078207293da30
L="--memory=1g --memory-swap=1g --oom-score-adj=1000"

# -i, because `python3 -` reads the script from stdin and docker does not
# forward stdin without it -- the container otherwise runs an empty program
# and exits silently, which looks exactly like "no output to give".
docker run --rm -i $L --entrypoint python3 "$IMAGE" - <<'PY' 2>&1
import inspect

from sbomify_action import runtimes

names = [n for n in dir(runtimes) if n.isupper()]
print("registry-ish module attributes:", ", ".join(names) or "(none)")

for n in names:
    v = getattr(runtimes, n)
    if isinstance(v, dict):
        print(f"\n{n}: {len(v)} entries")
        for k in sorted(map(str, v)):
            print(f"  {k}")
    elif isinstance(v, (list, tuple, set)) and len(v) < 60:
        print(f"\n{n}: {sorted(map(str, v))}")

src = inspect.getsource(runtimes)
print("\n--- mentions in runtimes.py ---")
for tool in ("php", "composer", "java", "jdk", "temurin", "gradle", "maven",
             "node", "go", "ruby", "dart", "swift", "elixir", "haskell",
             "erlang", "clojure", "curl", "unzip"):
    print(f"  {tool:9s}: {'yes' if tool in src.lower() else 'no'}")
PY
