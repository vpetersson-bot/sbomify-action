#!/usr/bin/env python3
"""Do the generator's own dependencies end up in the SBOMs it produces?

`cyclonedx-gomod mod -json -output … /workspace` was seen shelling out to
`go mod why -m -vendor github.com/CycloneDX/cyclonedx-go` while scanning
hashicorp/vault, and cyclonedx-go appears in neither vault's go.mod nor its
go.sum. Either cyclonedx-gomod asks about modules that are not in the target's
graph (harmless, just slow), or it is mixing its own build info into the
target's (contamination, and a real defect).

The SBOMs already on disk settle it: if the tool's own dependencies leak, they
will be listed as components of projects that never depended on them.
"""

import json
import pathlib
from collections import Counter

MARKERS = (
    "cyclonedx-go",
    "cyclonedx-gomod",
)


def scan(out_dir: pathlib.Path) -> None:
    hits: list[tuple[str, str, str]] = []
    checked = 0
    tools_only = Counter()

    for f in sorted(out_dir.glob("*.json")):
        try:
            doc = json.loads(f.read_text())
        except Exception:
            continue
        checked += 1

        # The tools block is *supposed* to name the generator. That is not a
        # leak; it is provenance. Only components count.
        for comp in doc.get("components") or []:
            name = (comp.get("name") or "").lower()
            purl = (comp.get("purl") or "").lower()
            for marker in MARKERS:
                if marker in name or marker in purl:
                    hits.append((f.stem, comp.get("name", ""), comp.get("version", "")))

        meta_tools = (doc.get("metadata") or {}).get("tools") or {}
        for t in (meta_tools.get("components") or []) if isinstance(meta_tools, dict) else []:
            tools_only[t.get("name", "?")] += 1

    print(f"\n{out_dir}: {checked} documents")
    print(f"  components matching {MARKERS}: {len(hits)}")
    for stem, name, version in hits[:20]:
        print(f"    {stem:38s} {name} {version}")
    if tools_only:
        print("  named in metadata.tools (expected, this is provenance):")
        for name, n in tools_only.most_common(5):
            print(f"    {n:4d}  {name}")


for d in (pathlib.Path("/home/ubuntu/sbomify-eval/v4/out"), pathlib.Path("/home/ubuntu/sbomify-eval/v5/out")):
    if d.is_dir():
        scan(d)
