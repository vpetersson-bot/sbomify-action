#!/usr/bin/env python3
"""Merge the two corpora into the single 500-project list for the final run.

The evaluation grew in two stages -- 251 projects, then 249 more chosen to
cover ecosystems and repository shapes the first pass never touched -- and
each was measured against whatever the image was that day. Roughly fifteen
fixes landed in between, so neither set of numbers describes the tool as it
ships now. This merges them so the whole 500 can be re-run against one pinned
build and the results can be quoted without a footnote about which half.

Both files are already four tab-separated fields (ecosystem, slug, target,
note) with no header on the v2 side and one on the v3 side. Validated here
rather than at run time: a malformed row should stop the corpus being built,
not surface twenty hours into a sweep.
"""

import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
SOURCES = [("v2", ROOT / "v2/all.tsv"), ("v3", ROOT / "v3/all.tsv")]
OUT = ROOT / "v4/all.tsv"


def rows(path: pathlib.Path, origin: str) -> list[tuple[str, list[str]]]:
    out = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        f = line.split("\t")
        if f[0] == "ecosystem" and i == 1:  # v3 keeps its header
            continue
        if len(f) != 4:
            sys.exit(f"{path}:{i}: {len(f)} fields, expected 4 -- {line!r}")
        if any("\t" in x for x in f):
            sys.exit(f"{path}:{i}: embedded tab")
        out.append((origin, f))
    return out


def main() -> None:
    collected = []
    for origin, path in SOURCES:
        r = rows(path, origin)
        print(f"{origin}: {len(r)} projects from {path.name}")
        collected.extend(r)

    # A slug in both corpora would be run twice and counted twice. Keep the
    # first and say so, rather than silently carrying a duplicate into a
    # headline number that is supposed to be exactly 500.
    seen: dict[str, str] = {}
    merged, dupes = [], []
    for origin, f in collected:
        slug = f[1]
        if slug in seen:
            dupes.append((slug, seen[slug], origin))
            continue
        seen[slug] = origin
        merged.append(f)

    if dupes:
        print(f"\n{len(dupes)} duplicate slug(s) dropped:")
        for slug, first, second in dupes:
            print(f"  {slug} (in {first} and {second})")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join("\t".join(f) + "\n" for f in merged))

    eco = Counter(f[0] for f in merged)
    print(f"\nwrote {len(merged)} projects to {OUT}")
    print(f"{len(eco)} ecosystems:")
    for name, n in eco.most_common():
        print(f"  {n:3d}  {name}")


if __name__ == "__main__":
    main()
