#!/usr/bin/env python3
"""If the action used the CI tag as the component version, how often would the
tag need normalising first?

The resolver had to learn every convention these 500 projects use. That
knowledge is reusable: on a tag-triggered build the tag is in the environment,
and a consumer matching a CVE feed wants 8.21.0, not curl-8_21_0.

Counts the population that would benefit from using the tag at all, and the
subset where using it verbatim would produce a version no registry knows.
"""

import json
import pathlib
import re
import sys
from collections import Counter

sys.path.insert(0, "/home/ubuntu/sbomify-eval")

REFS = json.loads(pathlib.Path("/home/ubuntu/sbomify-eval/v5_refs.json").read_text())
CLEAN = re.compile(r"^v?\d+(\.\d+)*$")

usable = {s: r for s, r in REFS.items() if r != "@default"}
verbatim_fine = {s: r for s, r in usable.items() if CLEAN.match(r)}
needs_work = {s: r for s, r in usable.items() if not CLEAN.match(r)}

print(f"{len(REFS)} projects")
print(f"  {len(usable):3d}  have a release tag the action could use as a version")
print(f"  {len(REFS) - len(usable):3d}  have none (nothing to use, nothing to invent)")
print()
print(f"  {len(verbatim_fine):3d}  the tag is already a clean version (v1.2.3)")
print(f"  {len(needs_work):3d}  using the tag verbatim would give something no registry knows")

shapes: Counter[str] = Counter()
for slug, ref in needs_work.items():
    if "/" in ref:
        shapes["path-prefixed (rel/release-3.5.0)"] += 1
    elif "_" in ref and re.search(r"\d_\d", ref):
        shapes["underscore-separated (curl-8_21_0)"] += 1
    elif "@" in ref:
        shapes["name@version (svelte@5.56.8)"] += 1
    elif re.match(r"^[A-Za-z].*?[-_]\d", ref):
        shapes["name-prefixed (camel-4.22.0)"] += 1
    elif re.search(r"\.(Final|RELEASE|GA)$", ref, re.I):
        shapes["finality suffix (netty-4.2.17.Final)"] += 1
    else:
        shapes["other"] += 1

print("\n  shapes needing normalisation:")
for shape, n in shapes.most_common():
    print(f"    {n:3d}  {shape}")

print("\n  examples:")
for slug, ref in sorted(needs_work.items())[:10]:
    print(f"    {slug:32s} {ref}")
