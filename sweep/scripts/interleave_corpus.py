#!/usr/bin/env python3
"""Order the corpus so three workers rarely block on each other.

Two constraints, and the first version only knew about one of them.

  * One project per ecosystem at a time.
  * One project from the *heavy* family at a time -- java, kotlin, scala,
    clojure share a single lock, because three 4 GB builds do not fit on this
    host and "one per ecosystem" does not prevent java beside kotlin.

Round-robin across ecosystems satisfies the first and actively works against
the second: kotlin, scala and clojure are three separate ecosystems, so the
round robin cheerfully emits them consecutively and all three workers land on
heavy work at once. Observed doing exactly that -- kotlin, scala and clojure in
flight together, one holding the lock and two spinning out a thirty-minute wait
for nothing.

So heavy projects are spread deliberately: at most one in any window of three,
by placing them at a fixed stride through the non-heavy stream. With ~59 heavy
projects in 500 the stride is comfortable, and the tail -- where only heavy
work is left -- serialises, which is correct rather than unfortunate.
"""

import pathlib
from collections import defaultdict

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
CORPUS = ROOT / "projects_v5.tsv"

#: Must match _HEAVY_ECOSYSTEMS in run_one_v5.sh. Kept in step by the check at
#: the bottom, which fails loudly rather than drifting quietly.
HEAVY = {"java", "kotlin", "scala", "android", "clojure"}


def round_robin(rows: list[list[str]]) -> list[list[str]]:
    """Largest ecosystem first, one at a time, so no two neighbours match."""
    by_eco: dict[str, list[list[str]]] = defaultdict(list)
    for row in rows:
        by_eco[row[0]].append(row)
    queues = sorted(by_eco.values(), key=len, reverse=True)
    out: list[list[str]] = []
    while any(queues):
        for q in queues:
            if q:
                out.append(q.pop(0))
    return out


def main() -> None:
    rows = [ln.rstrip("\n").split("\t") for ln in CORPUS.read_text().splitlines() if ln.strip()]

    heavy = round_robin([r for r in rows if r[0] in HEAVY])
    light = round_robin([r for r in rows if r[0] not in HEAVY])

    # Spread the heavy ones evenly through the light stream. Stride is chosen
    # from the ratio so they run out at roughly the same point rather than
    # leaving a heavy-only tail longer than it needs to be.
    stride = max(3, len(light) // max(1, len(heavy)))
    merged: list[list[str]] = []
    hi = 0
    for i, row in enumerate(light):
        merged.append(row)
        if (i + 1) % stride == 0 and hi < len(heavy):
            merged.append(heavy[hi])
            hi += 1
    merged.extend(heavy[hi:])

    assert len(merged) == len(rows), "reordering lost or duplicated a project"
    CORPUS.write_text("".join("\t".join(r) + "\n" for r in merged))

    windows = len(merged) - 2
    eco_repeat = sum(
        1 for i in range(windows) if len({merged[i][0], merged[i + 1][0], merged[i + 2][0]}) < 3
    )
    heavy_clash = sum(
        1 for i in range(windows) if sum(1 for j in range(3) if merged[i + j][0] in HEAVY) > 1
    )
    tail = next((i for i, r in enumerate(merged) if all(x[0] in HEAVY for x in merged[i:])), len(merged))

    print(f"reordered {len(merged)} projects: {len(heavy)} heavy, {len(light)} light, stride {stride}")
    print(f"windows of 3 with a repeated ecosystem: {eco_repeat} of {windows}")
    print(f"windows of 3 with >1 heavy project:     {heavy_clash} of {windows}")
    print(f"heavy-only tail begins at:              {tail} of {len(merged)}")
    print("\nfirst 12:")
    for row in merged[:12]:
        mark = "HEAVY" if row[0] in HEAVY else ""
        print(f"  {row[0]:12s} {row[1]:34s} {mark}")


if __name__ == "__main__":
    main()
