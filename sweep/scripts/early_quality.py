#!/usr/bin/env python3
"""What the sweep has found so far, by ecosystem and by failure shape.

Reads only completed records, so it is safe to run mid-sweep. The point is to
catch a systemic problem early rather than discover it at 500 -- the last two
sweeps both had one that was visible by 60 records and was not looked for.
"""

import json
import pathlib
from collections import Counter, defaultdict

META = pathlib.Path("/home/ubuntu/sbomify-eval/v5/meta")


def main() -> None:
    records = []
    for f in sorted(META.glob("*.json")):
        if not f.stat().st_size:
            continue
        try:
            records.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            print(f"unreadable record: {f.name}")

    print(f"{len(records)} records\n")

    images = Counter(r.get("image", "")[-12:] for r in records)
    print(f"images: {dict(images)}\n")

    by_eco: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_eco[r.get("ecosystem", "?")].append(r)

    empty, failed, ok = [], [], []
    for r in records:
        sbom = r.get("sbom") or {}
        n = sbom.get("components")
        strict = r.get("strict_rc")
        if strict != 0 and r.get("fallback_rc") not in (0, None):
            failed.append(r)
        elif not n:
            # The failure this whole exercise keeps finding: a document that
            # exits 0 and describes nothing.
            empty.append(r)
        else:
            ok.append(r)

    print(f"produced components: {len(ok)}")
    print(f"empty SBOM (exit 0, no components): {len(empty)}")
    print(f"no SBOM at all: {len(failed)}\n")

    print(f"{'ecosystem':14s} {'n':>3s} {'ok':>3s} {'empty':>5s} {'fail':>4s}  median components")
    for eco in sorted(by_eco, key=lambda e: -len(by_eco[e])):
        rows = by_eco[eco]
        counts = sorted((r.get("sbom") or {}).get("components") or 0 for r in rows)
        median = counts[len(counts) // 2] if counts else 0
        e = sum(1 for r in rows if r in empty)
        f = sum(1 for r in rows if r in failed)
        print(f"{eco:14s} {len(rows):3d} {len(rows) - e - f:3d} {e:5d} {f:4d}  {median}")

    if empty:
        print("\nempty SBOMs so far:")
        for r in empty[:15]:
            print(f"  {r.get('ecosystem'):12s} {r.get('slug'):38s} {r.get('target_lockfile')}")

    if failed:
        print("\nno SBOM at all:")
        for r in failed[:15]:
            print(f"  {r.get('ecosystem'):12s} {r.get('slug'):38s} {r.get('target_lockfile')}")


if __name__ == "__main__":
    main()
