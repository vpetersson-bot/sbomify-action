#!/usr/bin/env python3
"""How often is the SBOM built from the project's tooling rather than the project?

curl is the case that named this. At curl-8_21_0 discovery finds no root input
-- it is a C project with no lockfile the tool supports -- so the candidates
are `.github/scripts/requirements.txt`, `tests/requirements.txt`,
`tests/http/requirements.txt` and a Windows solution template. The wizard ticks
the shallowest selectable depth, which is `tests/requirements.txt`, and the run
produces a one-component SBOM whose root is "curl". It describes curl's test
harness, and says nothing that is true of curl.

Counted over the v4 corpus by replaying the *wizard's* rule against each
record's discovered list, rather than by trusting the target v4 recorded --
v4's own choice came from a truncated priority table and is not the product's.

The distinction that matters: no root-level input at all. A project with a
lockfile at its root is not at risk; one without falls to whatever is
shallowest, and in a C or C++ repository that is usually CI tooling.
"""

import json
import pathlib
from collections import Counter

V4 = pathlib.Path("/home/ubuntu/sbomify-eval/v4/meta")

#: Directories whose contents describe how the project is built, tested or
#: documented -- not what it ships.
TOOLING = (
    "test", "tests", "testing", ".github", ".ci", "ci", "docs", "doc",
    "examples", "example", "samples", "benchmark", "benchmarks", "bench",
    "scripts", "tools", "contrib", "utils", "demo", "demos", "e2e",
)


def first_segment(path: str) -> str:
    return path.split("/")[0].lower() if "/" in path else ""


def main() -> None:
    at_risk = []          # no root-level candidate at all
    tooling_pick = []     # and the wizard's pick lands in a tooling directory
    eco_counts: Counter[str] = Counter()

    total = 0
    for f in sorted(V4.glob("*.json")):
        try:
            rec = json.loads(f.read_text())
        except Exception:
            continue
        discovered = rec.get("discovered") or []
        if not discovered:
            continue
        total += 1

        paths = [d["path"] for d in discovered]
        if any("/" not in p for p in paths):
            continue  # a root-level input exists; the wizard ticks that tier
        at_risk.append(rec["slug"])

        # The wizard ticks the shallowest depth; take the shallowest path.
        shallowest = min(p.count("/") for p in paths)
        picks = sorted(p for p in paths if p.count("/") == shallowest)
        if any(first_segment(p) in TOOLING for p in picks):
            tooling_pick.append((rec["slug"], rec.get("ecosystem"), picks[0]))
            eco_counts[rec.get("ecosystem") or "?"] += 1

    print(f"{total} records with any discovered input")
    print(f"{len(at_risk)} have no root-level input at all")
    print(f"{len(tooling_pick)} of those would be built from a tooling directory\n")

    for slug, eco, path in sorted(tooling_pick, key=lambda x: str(x[1]))[:25]:
        print(f"  {str(eco):11s} {slug:34s} {path}")
    if len(tooling_pick) > 25:
        print(f"  … {len(tooling_pick) - 25} more")

    print("\nby ecosystem:")
    for eco, n in eco_counts.most_common():
        print(f"  {n:3d}  {eco}")


if __name__ == "__main__":
    main()
