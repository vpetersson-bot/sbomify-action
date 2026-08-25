#!/usr/bin/env python3
"""How often is the root component's version something a consumer can use?

F6: cdxgen writes `version: "latest"` with a matching `...@latest` purl, and
syft writes a bare content hash. Neither can be matched against a CVE feed,
which is most of what a consumer does with a root version.

Counts against whichever corpus directories exist, reported separately --
v2 was produced by an older build and v4 by the pinned one, and mixing them
would hide any change.
"""

import json
import pathlib
import re
import sys
from collections import Counter

SHA = re.compile(r"^(sha256:)?[0-9a-f]{32,}$", re.I)


def classify(version: str | None) -> str:
    if not version:
        return "missing"
    v = version.strip()
    if not v:
        return "missing"
    if v.lower() in {"latest", "unknown", "none", "n/a"}:
        return "placeholder"
    if SHA.match(v):
        return "content hash"
    if re.match(r"^v?\d", v):
        return "usable"
    return "other"


def survey(out_dir: pathlib.Path) -> None:
    kinds: Counter[str] = Counter()
    examples: dict[str, str] = {}
    total = 0
    for f in sorted(out_dir.glob("*.json")):
        try:
            doc = json.loads(f.read_text())
        except Exception:
            continue
        root = (doc.get("metadata") or {}).get("component") or {}
        if not root:
            continue
        total += 1
        kind = classify(root.get("version"))
        kinds[kind] += 1
        examples.setdefault(kind, f"{f.stem}: {root.get('version')!r}")

    if not total:
        print(f"{out_dir}: no documents with a root component")
        return

    print(f"\n{out_dir} -- {total} documents with a root component")
    for kind, n in kinds.most_common():
        print(f"  {kind:14s} {n:4d}  {100 * n / total:5.1f}%   e.g. {examples[kind]}")


def main() -> None:
    roots = sys.argv[1:] or ["/home/ubuntu/sbomify-eval/v2/out", "/home/ubuntu/sbomify-eval/v4/out"]
    for r in roots:
        p = pathlib.Path(r)
        if p.is_dir():
            survey(p)


if __name__ == "__main__":
    main()
