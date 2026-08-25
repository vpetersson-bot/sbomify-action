#!/usr/bin/env python3
"""Did the merged fixes change the outcome for the projects that failed?

Compares each re-measured project against the snapshot taken before the
re-run, so the answer is a difference between two builds rather than an
impression. Only projects whose record actually changed image are compared --
anything still carrying the old digest was not re-run and is reported as such
instead of being counted as "unchanged", which would quietly turn work that
did not happen into evidence that nothing improved.

Regressions are printed before improvements. A fix that helps forty projects
and breaks one is still a fix that broke one, and that is the number most
likely to be skipped over.
"""

import json
import pathlib
from collections import Counter, defaultdict

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
BEFORE = ROOT / "v5/meta-4238898-snapshot"
AFTER = ROOT / "v5/meta"

OLD_IMAGE = "36023aa8"
NEW_IMAGE = "de0d338f"


def load(d: pathlib.Path) -> dict[str, dict]:
    out = {}
    for f in sorted(d.glob("*.json")):
        if not f.stat().st_size:
            continue
        try:
            rec = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        out[rec["slug"]] = rec
    return out


def components(rec: dict) -> int | None:
    """Total components across every run, or None when nothing was produced."""
    runs = rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else [])
    counts = [(r.get("sbom") or {}).get("components") for r in runs]
    real = [c for c in counts if c]
    if not runs:
        return None
    return sum(real) if real else 0


def verdict(rec: dict) -> str:
    if rec.get("error") == "no_lockfile_discovered":
        return "no input"
    n = components(rec)
    if n is None:
        return "no runs"
    return "components" if n else "empty"


def main() -> None:
    before, after = load(BEFORE), load(AFTER)

    rerun, not_rerun = [], []
    for slug, new in after.items():
        old = before.get(slug)
        if old is None:
            continue
        if NEW_IMAGE in (new.get("image") or ""):
            rerun.append((slug, old, new))
        elif verdict(old) != "components":
            not_rerun.append(slug)

    print(f"re-measured on the new build : {len(rerun)}")
    print(f"still on the old build       : {len(not_rerun)} previously-failing project(s)")
    if not_rerun:
        for slug in sorted(not_rerun)[:10]:
            print(f"     {slug}")

    improved, regressed, same = [], [], []
    for slug, old, new in rerun:
        ob, nb = components(old), components(new)
        ov, nv = verdict(old), verdict(new)
        if (ob or 0) == (nb or 0) and ov == nv:
            same.append((slug, old, new))
        elif (nb or 0) > (ob or 0):
            improved.append((slug, old, new, ob, nb))
        else:
            regressed.append((slug, old, new, ob, nb))

    if regressed:
        print(f"\nREGRESSED ({len(regressed)}) -- read these first")
        for slug, old, _new, ob, nb in sorted(regressed):
            print(f"     {old['ecosystem']:11s} {slug:34s} {ob} -> {nb}")
    else:
        print("\nREGRESSED: none")

    print(f"\nIMPROVED ({len(improved)})")
    for slug, old, _new, ob, nb in sorted(improved, key=lambda x: -(x[4] or 0)):
        print(f"     {old['ecosystem']:11s} {slug:34s} {ob} -> {nb}")

    print(f"\nUNCHANGED ({len(same)})")
    by_eco: dict[str, int] = defaultdict(int)
    for slug, old, _new in same:
        by_eco[old["ecosystem"]] += 1
    for eco, n in sorted(by_eco.items(), key=lambda x: -x[1]):
        print(f"     {eco:11s} {n}")

    # PHP is the ecosystem #372 makes a specific prediction about, so it gets
    # its own answer rather than being averaged into a total.
    print("\nPHP, named in the #372 rationale:")
    php = [(s, o, n) for s, o, n in rerun if o["ecosystem"] == "php"]
    for slug, old, new in sorted(php):
        print(f"     {slug:34s} {components(old)} -> {components(new)}   ({verdict(old)} -> {verdict(new)})")
    if not php:
        print("     (no PHP project in the re-run set yet)")

    print("\nverdict movement:")
    moves = Counter(f"{verdict(o)} -> {verdict(n)}" for _s, o, n in rerun)
    for move, n in moves.most_common():
        print(f"   {n:4d}  {move}")


if __name__ == "__main__":
    main()
