#!/usr/bin/env python3
"""Do the 18 empty v4 records still matter, given v5 exists?

v5 is the corpus every published number came from. If v5 has a populated
record for each of these projects, the v4 holes are a dead artifact of an
older sweep and refilling them buys nothing.
"""

import json
import pathlib

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")

empty = sorted(p.stem for p in (ROOT / "v4/meta").glob("*.json") if not p.stat().st_size)

missing, no_runs, ok = [], [], []
for stem in empty:
    v5 = ROOT / "v5/meta" / f"{stem}.json"
    if not v5.exists() or not v5.stat().st_size:
        missing.append(stem)
        continue
    rec = json.loads(v5.read_text())
    runs = rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else [])
    (ok if runs else no_runs).append(stem)

print(f"v4 empty: {len(empty)}")
print(f"  covered by v5 with runs : {len(ok)}")
print(f"  in v5 but no runs       : {len(no_runs)}")
print(f"  absent/empty in v5 too   : {len(missing)}")
for label, group in (("NO RUNS IN V5", no_runs), ("ABSENT IN V5", missing)):
    if group:
        print(f"\n{label}:")
        for s in group:
            print("   ", s)
