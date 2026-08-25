#!/usr/bin/env python3
"""The 500-project result, against one pinned build.

Every number here comes from
ghcr.io/sbomify/sbomify-action@sha256:0a29db00…93da30 (26.7.0+688841c), so
unlike the two earlier sweeps there is no footnote about which half was
measured against what.

Strict mode is the default and is what a user gets. The fallback run only
happens after strict fails, and separates two outcomes that otherwise look
identical: no tool in the image can read this project (a coverage gap) versus
a working SBOM existed and strict mode refused it (a routing bug).
"""

import json
import pathlib
from collections import Counter, defaultdict

V4 = pathlib.Path("/home/ubuntu/sbomify-eval/v4")


def main() -> None:
    rows = []
    for f in sorted(V4.glob("meta/*.json")):
        try:
            rows.append(json.loads(f.read_text()))
        except Exception:
            continue

    total = len(rows)
    outcome: Counter[str] = Counter()
    eco = defaultdict(lambda: {"n": 0, "sbom": 0, "empty": 0, "nolock": 0, "comps": []})
    fallback_rescued = []
    empty_but_ok = []

    for r in rows:
        s = r.get("sbom") or {}
        n = s.get("components")
        e = eco[r.get("ecosystem") or "?"]
        e["n"] += 1

        if r.get("error") == "clone_failed":
            outcome["clone failed"] += 1
            continue
        if r.get("error") == "no_lockfile_discovered":
            outcome["no input recognised"] += 1
            e["nolock"] += 1
            continue

        if n:
            outcome["SBOM with components"] += 1
            e["sbom"] += 1
            e["comps"].append(n)
            if r.get("used_fallback") and r.get("fallback_rc") == 0:
                fallback_rescued.append((r["slug"], n))
        elif n == 0:
            outcome["SBOM with ZERO components"] += 1
            e["empty"] += 1
            empty_but_ok.append(r["slug"])
        else:
            outcome["no SBOM produced"] += 1

    print(f"500-project sweep, one pinned build -- {total} records\n")
    for k, v in outcome.most_common():
        print(f"  {v:4d}  {100 * v / total:5.1f}%  {k}")

    comps = sorted(c for e in eco.values() for c in e["comps"])
    if comps:
        print(f"\ncomponents per SBOM: median {comps[len(comps) // 2]}, max {comps[-1]}, total {sum(comps):,}")

    print(f"\nrescued only by the fallback run: {len(fallback_rescued)}")
    for slug, n in sorted(fallback_rescued, key=lambda x: -x[1])[:10]:
        print(f"    {slug:42s} {n:5d} components")

    print(f"\nempty documents reported as success: {len(empty_but_ok)}")
    for slug in empty_but_ok[:10]:
        print(f"    {slug}")

    print("\nper ecosystem (run / with SBOM / empty / no input / median):")
    for name, b in sorted(eco.items(), key=lambda kv: (-kv[1]["n"], kv[0])):
        c = sorted(b["comps"])
        med = c[len(c) // 2] if c else 0
        print(f"  {name:12s} {b['n']:4d} {b['sbom']:4d} {b['empty']:4d} {b['nolock']:4d}  {med:5d}")


if __name__ == "__main__":
    main()
