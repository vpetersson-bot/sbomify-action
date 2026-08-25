#!/usr/bin/env python3
"""Early check that the harness fixes are actually taking effect.

Two changes went in just before this run, and both are the kind that fail
silently: the checkout ref, and the input ranking. Verifying them at 26
records costs nothing; discovering at 500 that every row scanned master would
cost the whole run.
"""

import json
import pathlib
from collections import Counter

V5 = pathlib.Path("/home/ubuntu/sbomify-eval/v5")

rows = []
for f in sorted(V5.glob("meta/*.json")):
    try:
        rows.append(json.loads(f.read_text()))
    except Exception:
        print(f"UNPARSEABLE: {f.name}")

print(f"{len(rows)} records\n")

refs = Counter("@default" if r.get("ref") == "@default" else "release/tag" for r in rows)
print("checkout:")
for k, v in refs.items():
    print(f"  {v:3d}  {k}")
missing = [r["slug"] for r in rows if "ref" not in r]
print(f"  records with no ref field at all: {len(missing)} {missing[:3]}")

print("\ntarget input chosen, by ecosystem:")
by_eco: dict[str, Counter] = {}
for r in rows:
    by_eco.setdefault(r.get("ecosystem") or "?", Counter())[r.get("target_lockfile") or "(none)"] += 1
for eco in sorted(by_eco):
    picks = ", ".join(f"{k}×{v}" for k, v in by_eco[eco].most_common(4))
    print(f"  {eco:12s} {picks}")

# The Alamofire failure mode: a project whose chosen input belongs to a
# different ecosystem than the one the corpus assigned it.
ECO_FILES = {
    "swift": {"Package.swift", "Package.resolved"},
    "ruby": {"Gemfile.lock"},
    "python": {"uv.lock", "poetry.lock", "Pipfile.lock", "requirements.txt", "pyproject.toml"},
    "rust": {"Cargo.lock", "Cargo.toml"},
    "go": {"go.mod", "go.sum"},
    "php": {"composer.json", "composer.lock"},
}
print("\ninput from a different ecosystem than the corpus assigned:")
odd = 0
for r in rows:
    eco, target = r.get("ecosystem"), r.get("target_lockfile")
    if not target or eco not in ECO_FILES:
        continue
    name = target.split("/")[-1]
    owner = next((e for e, files in ECO_FILES.items() if name in files), None)
    if owner and owner != eco:
        print(f"  {r['slug']:34s} corpus={eco:8s} chose={target} ({owner})")
        odd += 1
print(f"  {odd} found")

out = Counter()
for r in rows:
    s = r.get("sbom") or {}
    n = s.get("components")
    if r.get("error"):
        out[r["error"]] += 1
    elif n:
        out["sbom with components"] += 1
    elif n == 0:
        out["EMPTY, reported success"] += 1
    else:
        out["no sbom"] += 1
print("\noutcomes so far:")
for k, v in out.most_common():
    print(f"  {v:3d}  {k}")
