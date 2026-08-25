#!/usr/bin/env python3
"""Work list for the arm64 sweep: all 500, not just the worst 200.

This run is not a regression against the amd64 baseline -- it cannot be, the
architecture differs and sbomify-action ships a different tool bundle per
arch. It is a bug hunt on a platform that has never been swept, so breadth
beats comparability and every project is in scope.

Targets come from what v5 actually scanned, where it scanned anything. A
project with no recorded target gets none, and discovery decides -- which
exercises more of the product than replaying a fixed LOCK_FILE does.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
BASELINE = ROOT / "v5-meta"

refs = {}
for line in (ROOT / "projects_v5.tsv").read_text().splitlines():
    parts = line.split("\t")
    if len(parts) >= 5:
        refs[parts[1]] = parts[4]

rows, no_ref = [], 0
for f in sorted(BASELINE.glob("*.json")):
    if not f.stat().st_size:
        continue
    rec = json.loads(f.read_text())
    slug = rec.get("slug")
    if not slug:
        continue
    ref = refs.get(slug)
    if not ref:
        no_ref += 1
        continue
    runs = rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else [])
    target = ""
    for run in runs:
        if run.get("target_lockfile"):
            target = run["target_lockfile"]
            break
    rows.append((slug, ref, target, rec.get("ecosystem") or "?"))

out = ROOT / "arm64_all.tsv"
with out.open("w") as fh:
    for slug, ref, target, eco in rows:
        fh.write(f"{slug}\t{ref}\t{target}\t{eco}\n")

with_target = sum(1 for r in rows if r[2])
print(f"wrote {out} with {len(rows)} projects")
print(f"  {with_target} replay a recorded LOCK_FILE")
print(f"  {len(rows) - with_target} let discovery choose")
if no_ref:
    print(f"  {no_ref} skipped (no ref in projects_v5.tsv)")
