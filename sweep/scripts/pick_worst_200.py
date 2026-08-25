#!/usr/bin/env python3
"""Rank the 500 by how badly the v5 sweep served them, and take the worst 200.

Worst means the user got something they could not use, in this order:

  1. crashed          -- non-zero exit, no document at all
  2. empty document   -- exit 0 and zero components, the silent failure
  3. no runs          -- nothing was even attempted for the project
  4. wrong subject    -- the target was tooling/docs, so the SBOM describes
                         the harness rather than what ships
  5. inferred         -- versions resolved at run time from a manifest
  6. thin             -- suspiciously few components for the ecosystem

Every one of these is something a shipped fix was supposed to change, so the
set doubles as the regression surface.
"""

import json
import pathlib

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
META = ROOT / "v5/meta"

TOOLING_DIRS = {
    ".ci", ".github", ".gitlab", "bench", "benchmark", "benchmarks", "ci",
    "contrib", "demo", "demos", "doc", "docs", "e2e", "example", "examples",
    "samples", "script", "scripts", "test", "testing", "tests", "tools",
}

MANIFESTS = {
    "pyproject.toml", "package.json", "composer.json", "Cargo.toml",
    "build.gradle", "build.gradle.kts", "pom.xml", "build.sbt", "deps.edn",
    "project.clj", "stack.yaml", "mix.exs", "Package.swift",
}


def is_tooling(path: str) -> bool:
    parts = path.split("/")
    return len(parts) > 1 and parts[0].lower() in TOOLING_DIRS


rows = []
for f in sorted(META.glob("*.json")):
    if not f.stat().st_size:
        continue
    rec = json.loads(f.read_text())
    runs = rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else [])
    slug = rec["slug"]
    eco = rec.get("ecosystem") or "?"

    if not runs:
        rows.append((1000, slug, eco, "no runs", None, None))
        continue

    for run in runs:
        target = run.get("target_lockfile") or ""
        sbom = run.get("sbom") or {}
        comps = sbom.get("components")
        rc = run.get("fallback_rc") if run.get("used_fallback") else run.get("strict_rc")
        if rc is None:
            rc = run.get("strict_rc")

        if rc not in (0, None):
            score, why = 3000, f"crashed rc={rc}"
        elif comps == 0 or comps is None:
            score, why = 2000, "empty document"
        elif is_tooling(target):
            score, why = 900, "tooling subject"
        elif target.split("/")[-1] in MANIFESTS:
            score, why = 500, "inferred versions"
        elif comps is not None and comps < 5:
            score, why = 300, f"thin ({comps})"
        else:
            continue
        rows.append((score, slug, eco, why, target, comps))

# One entry per project: keep its worst run.
worst: dict[str, tuple] = {}
for row in rows:
    if row[1] not in worst or row[0] > worst[row[1]][0]:
        worst[row[1]] = row

ranked = sorted(worst.values(), key=lambda r: (-r[0], r[1]))[:200]

out = ROOT / "worst200.tsv"
with out.open("w") as fh:
    for score, slug, eco, why, target, comps in ranked:
        fh.write(f"{slug}\t{eco}\t{why}\t{target or ''}\t{comps if comps is not None else ''}\n")

from collections import Counter  # noqa: E402

print(f"{len(worst)} projects had at least one problem; taking {len(ranked)}\n")
for why, n in Counter(r[3].split(" rc=")[0].split(" (")[0] for r in ranked).most_common():
    print(f"   {why:18s} {n}")
print("\nby ecosystem:")
for eco, n in Counter(r[2] for r in ranked).most_common(12):
    print(f"   {eco:12s} {n}")
print(f"\nwrote {out}")
