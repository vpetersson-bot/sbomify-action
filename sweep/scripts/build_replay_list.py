#!/usr/bin/env python3
"""Join the worst-200 with their v5 refs and targets into a work list.

The ref matters as much as the target: v5 scanned release tags, not default
branches, because nobody generates an SBOM for master. Replaying at HEAD would
change the input and make every diff unattributable.
"""

import pathlib

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")

refs = {}
for line in (ROOT / "projects_v5.tsv").read_text().splitlines():
    if not line.strip():
        continue
    parts = line.split("\t")
    if len(parts) >= 5:
        refs[parts[1]] = parts[4]

rows, missing = [], []
for line in (ROOT / "worst200.tsv").read_text().splitlines():
    if not line.strip():
        continue
    slug, eco, why, target, _comps = (line.split("\t") + ["", "", "", "", ""])[:5]
    ref = refs.get(slug)
    if not ref:
        missing.append(slug)
        continue
    rows.append((slug, ref, target, eco, why))

out = ROOT / "replay200.tsv"
with out.open("w") as fh:
    for slug, ref, target, eco, why in rows:
        fh.write(f"{slug}\t{ref}\t{target}\t{eco}\t{why}\n")

print(f"wrote {out} with {len(rows)} projects")
if missing:
    print(f"no ref for {len(missing)}: {missing[:5]}")
no_target = sum(1 for r in rows if not r[2])
print(f"  {no_target} have no recorded target (discovery decides)")
print(f"  {len(rows) - no_target} replay a fixed LOCK_FILE")
