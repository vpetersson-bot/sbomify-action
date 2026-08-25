#!/usr/bin/env python3
"""Every input the 500-project run actually targeted, against the new maps.

Three maps have to agree for the disclosure to be right, and each answers a
different question:

  UNRESOLVED_MANIFESTS    is this input a manifest rather than a resolution
  COMMITTED_RESOLUTION_FOR  what file beside it would mean the versions were recorded
  RECOMMENDED_ACTION      what the user should run to produce that file

A manifest missing from the second gets a false "your versions were inferred"
when its lock file is sitting right there. A manifest missing from the third
gets told it has a problem and not how to fix it. Both have already happened
on this branch -- Cargo.toml and go.mod for the first, gradle.lockfile for a
variant of it -- which is why this checks the real corpus instead of the names
someone remembered.
"""

import json
import pathlib
from collections import Counter

from sbomify_action._generation.registry import (
    COMMITTED_RESOLUTION_FOR,
    LOCKFILE_FOR_MANIFEST,
    RECOMMENDED_ACTION,
    UNRESOLVED_MANIFESTS,
)
from sbomify_action._generation.utils import ALL_LOCK_FILES

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
META = ROOT / "v5/meta-4238898-snapshot"

#: Inputs matched by extension rather than by name.
SUFFIXES = (".csproj", ".fsproj", ".vbproj", ".sln")

#: Manifests whose ecosystem has no lock file to commit. Having no entry in
#: COMMITTED_RESOLUTION_FOR is the correct answer for these -- they are always
#: inferred, and saying so is true rather than a gap. Listing them explicitly
#: is what separates "no lock file exists" from "we forgot one", which is the
#: distinction this check exists to make.
NO_LOCK_FILE_EXISTS = {
    "pom.xml",  # Maven has no lock file
    "build.sbt",  # sbt has none as standard
    "deps.edn",  # tools.deps resolves at build time
    "project.clj",  # Leiningen the same
    "requirements.txt",  # can be pinned in place, but nothing says whether it is
}


def main() -> None:
    seen: Counter[str] = Counter()
    for f in sorted(META.glob("*.json")):
        if not f.stat().st_size:
            continue
        rec = json.loads(f.read_text())
        for run in rec.get("runs") or [rec]:
            target = run.get("target_lockfile")
            if target:
                seen[target.rsplit("/", 1)[-1]] += 1

    print(f"{len(seen)} distinct inputs targeted across the corpus\n")
    print(f"{'input':26s} {'runs':>5s}  {'manifest?':10s} {'resolution known':17s} {'remedy':7s}")

    gaps = []
    for name, count in seen.most_common():
        if name.endswith(SUFFIXES):
            kind = "project file"
            print(f"{name[:26]:26s} {count:5d}  {kind:10s} {'n/a':17s} {'n/a':7s}")
            continue

        is_manifest = name in UNRESOLVED_MANIFESTS
        has_resolution = name in COMMITTED_RESOLUTION_FOR
        has_remedy = name in RECOMMENDED_ACTION
        known_input = name in ALL_LOCK_FILES

        note = ""
        if is_manifest and not has_resolution and name not in NO_LOCK_FILE_EXISTS:
            note = "NO RESOLUTION MAPPED -- false 'inferred' when the lock file exists"
            gaps.append((name, count, note))
        elif is_manifest and not has_resolution:
            note = "always inferred (no lock file exists in this ecosystem)"
        elif is_manifest and not has_remedy:
            note = "NO REMEDY -- told it is inferred, not told what to do"
            gaps.append((name, count, note))
        elif not is_manifest and not known_input:
            note = "not a recognised input at all"
            gaps.append((name, count, note))

        print(
            f"{name[:26]:26s} {count:5d}  {'yes' if is_manifest else 'no':10s} "
            f"{('yes' if has_resolution else '-'):17s} {('yes' if has_remedy else '-'):7s} {note}"
        )

    print()
    if gaps:
        print(f"{len(gaps)} gap(s):")
        for name, count, note in gaps:
            print(f"   {name:24s} {count:4d} run(s)  {note}")
    else:
        print("no gaps: every manifest the corpus met has a resolution and a remedy")

    # The reverse direction: names in the maps the corpus never exercised.
    untested = sorted(UNRESOLVED_MANIFESTS - set(seen))
    if untested:
        print(f"\nin the map but never seen in 500 projects (untested by this corpus):")
        print("   " + ", ".join(untested))

    mismatched = sorted(set(LOCKFILE_FOR_MANIFEST) - set(COMMITTED_RESOLUTION_FOR))
    if mismatched:
        print(f"\npromoted but with no committed-resolution entry: {', '.join(mismatched)}")


if __name__ == "__main__":
    main()
