#!/usr/bin/env python3
"""Are the refs this corpus resolved actually the projects' releases?

Two suspicious rows in the first 28 records prompted this:

  phoenixframework/phoenix  v1.5.3                    -- Phoenix is on 1.7.x
  dart-lang/sdk             meta-v1.3.0-nullsafety.2  -- that is the `meta`
                                                         package, not the SDK

Both come from resolve_releases.py and both are wrong in a way that scanning
master was wrong: the subject is not what a user would scan.

  * GitHub's `releases/latest` is a mutable flag a maintainer sets. Phoenix's
    still points at v1.5.3, four minor versions back.
  * The tag fallback sorts by `-v:refname`, which in a monorepo that tags per
    package happily returns `meta-v1.3.0-nullsafety.2`.

Classifies every resolved ref so the scale is known before anything is redone.
"""

import json
import pathlib
import re
from collections import Counter

REFS = json.loads(pathlib.Path("/home/ubuntu/sbomify-eval/v5_refs.json").read_text())

#: A release of the project itself: optional v, then digits and dots, then an
#: optional prerelease/build suffix.
PLAIN = re.compile(r"^v?\d+(\.\d+)*([.\-+][0-9A-Za-z.\-+]*)?$")
#: A package-scoped tag in a monorepo: <name>-v1.2.3 or <name>/v1.2.3 or @scope.
SCOPED = re.compile(r"^[A-Za-z][\w.\-]*?[-/@]v?\d")


def classify(ref: str) -> str:
    if ref == "@default":
        return "default branch (no release, no tag)"
    if PLAIN.match(ref):
        return "plain version"
    if SCOPED.match(ref):
        return "PACKAGE-SCOPED (wrong subject)"
    return "unrecognised shape"


kinds: Counter[str] = Counter()
suspect = []
for slug, ref in sorted(REFS.items()):
    kind = classify(ref)
    kinds[kind] += 1
    if kind != "plain version" and ref != "@default":
        suspect.append((slug, ref, kind))

print(f"{len(REFS)} resolved refs\n")
for kind, n in kinds.most_common():
    print(f"  {n:4d}  {kind}")

print(f"\n{len(suspect)} not a plain version:")
for slug, ref, kind in suspect[:40]:
    print(f"  {slug:38s} {ref[:44]:46s} {kind}")
if len(suspect) > 40:
    print(f"  … {len(suspect) - 40} more")
