#!/usr/bin/env bash
# Enumerate every tool the pinned image knows how to fetch, and what it pins.
#
# This is the honest version of "is PHP supported?". Since #320 nothing but
# Python is baked into the image, so `command -v php` returning nothing says
# only that the image is lazy, not that PHP is unsupported. The manifest is
# the actual answer, and it is loaded through load_tools()/load_bundles()
# rather than exposed as a module-level dict.
set -uo pipefail
IMAGE=ghcr.io/sbomify/sbomify-action@sha256:0a29db0020f59c8ed0b4d0ac3202346f2734d6fd6704b4139c8078207293da30
L="--memory=1g --memory-swap=1g --oom-score-adj=1000"

docker run --rm -i $L --entrypoint python3 "$IMAGE" - <<'PY' 2>&1
import dataclasses

from sbomify_action import tool_manifest as tm

tools = tm.load_tools()
bundles = tm.load_bundles()

print(f"{len(tools)} tools, {len(bundles)} bundles\n")

print("bundles:")
for name in sorted(bundles):
    b = bundles[name]
    members = getattr(b, "tools", None) or getattr(b, "members", None) or []
    print(f"  {name:12s} {', '.join(sorted(map(str, members)))}")

print("\ntools:")
for key in sorted(tools):
    t = tools[key]
    d = {f.name: getattr(t, f.name) for f in dataclasses.fields(t)}
    ver = d.get("version") or d.get("pinned_version") or ""
    stage = d.get("stage", "")
    print(f"  {key:24s} {str(ver):20s} {stage}")

print("\nlooked for specifically:")
for want in ("php", "composer", "jdk", "java", "temurin", "maven", "gradle",
             "sbt", "go", "node", "bun", "ruby", "dart", "swift", "elixir",
             "cabal", "rebar", "clojure", "curl", "unzip"):
    hit = [k for k in tools if want in k.lower()]
    print(f"  {want:9s}: {', '.join(sorted(hit)) if hit else 'NOT IN MANIFEST'}")
PY
