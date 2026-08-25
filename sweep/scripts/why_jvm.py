#!/usr/bin/env python3
"""Why each JVM-family project produced nothing.

"The Gradle build failed" is not a reason, it is a restatement. These builds
fail for at least two unrelated causes and they have opposite owners:

  * the daemon being killed, which is the harness capping the container at
    4 GB and has nothing to do with the tool;
  * the build script rejecting the injected plugin, which is a real limit of
    generating an SBOM by running someone else's build.

Counting them together would let a harness constraint masquerade as a product
defect, which is the mistake this evaluation has already made several times.
"""

import json
import os
import pathlib
import re
from collections import Counter, defaultdict

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
META = pathlib.Path(os.environ.get("SBOMIFY_EVAL_META") or (ROOT / "v5/meta"))
LOGS = ROOT / "v5/logs"

#: Ordered: the first matching signature wins, so put the unambiguous ones
#: first. Each is (reason, owner, pattern).
SIGNATURES = [
    ("gradle daemon killed", "harness (memory cap)", r"daemon disappeared unexpectedly"),
    ("out of memory", "harness (memory cap)", r"OutOfMemoryError|Java heap space|Killed"),
    ("build script rejects the plugin", "tool limit", r"Could not get unknown property|Could not find method|No such property"),
    ("build needs a different JDK", "environment", r"Unsupported class file major version|requires Java \d+|invalid source release"),
    ("build downloads at configure time", "environment", r"Could not resolve all (files|dependencies)|Could not download"),
    ("compile failure in the project", "project", r"error: cannot find symbol|compileJava.*FAILED"),
    ("wrapper refused to run", "tool limit", r"Unable to access jarfile|checksum"),
    ("swift needs Package.resolved", "explained refusal", r"declares version ranges; SwiftPM"),
    ("sbt build failed", "tool limit", r"sbt.*(error|failed)"),
]


def main() -> None:
    rows = []
    for f in sorted(META.glob("*.json")):
        if not f.stat().st_size:
            continue
        rec = json.loads(f.read_text())
        runs = rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else [])
        if not runs or any((r.get("sbom") or {}).get("components") for r in runs):
            continue
        log = LOGS / f"{f.stem}.log"
        text = log.read_text(errors="replace")[-400_000:] if log.exists() else ""
        reason = owner = None
        for name, who, pattern in SIGNATURES:
            if re.search(pattern, text, re.I):
                reason, owner = name, who
                break
        rows.append((rec["ecosystem"], rec["slug"], reason or "unidentified", owner or "?"))

    by_reason = Counter((r[3], r[2]) for r in rows)
    print(f"{len(rows)} projects produced nothing; grouped by cause:\n")
    for (owner, reason), n in sorted(by_reason.items(), key=lambda x: -x[1]):
        print(f"   {n:4d}  [{owner}] {reason}")

    print("\nby owner:")
    for owner, n in Counter(r[3] for r in rows).most_common():
        print(f"   {n:4d}  {owner}")

    unid = [r for r in rows if r[2] == "unidentified"]
    if unid:
        print(f"\nstill unidentified ({len(unid)}):")
        for eco, slug, _r, _o in sorted(unid):
            print(f"   {eco:11s} {slug}")

    print("\nharness-capped projects (would need more memory to judge the tool):")
    for eco, slug, reason, owner in sorted(rows):
        if owner.startswith("harness"):
            print(f"   {eco:11s} {slug}")


if __name__ == "__main__":
    main()
