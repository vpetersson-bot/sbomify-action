#!/usr/bin/env python3
"""The projects worth re-running against a newer build, and why each qualifies.

"Failed" needs defining or the re-run measures the wrong thing.

  * **no components** -- every run for the project came back with no document
    or an empty one. These are the failures the merged fixes could plausibly
    change, and they are the whole point of the exercise.

  * **no recognised input** -- discovery found nothing to scan. Nothing in
    #372, #373 or #374 touches discovery, so re-running these can only confirm
    they are still unsupported. Listed separately and excluded by default
    rather than silently dropped, because "we did not re-run 94 projects" is a
    fact the write-up needs either way.

  * **partial** -- a polyglot project where some inputs produced components
    and others did not. Included: the fixes act per run, so a project can
    improve without having failed outright.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
META = ROOT / "v5/meta"


def classify(rec: dict) -> str:
    if rec.get("error") == "no_lockfile_discovered":
        return "no recognised input"
    runs = rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else [])
    if not runs:
        return "no runs"
    counts = [(r.get("sbom") or {}).get("components") for r in runs]
    if all(not c for c in counts):
        return "no components"
    if any(not c for c in counts):
        return "partial"
    return "ok"


def main() -> None:
    include_no_input = "--include-no-input" in sys.argv

    rows = {
        line.split("\t")[1]: line
        for line in (ROOT / "projects_v5.tsv").read_text().splitlines()
        if line.strip()
    }

    buckets: dict[str, list[str]] = {}
    for f in sorted(META.glob("*.json")):
        if not f.stat().st_size:
            continue
        rec = json.loads(f.read_text())
        buckets.setdefault(classify(rec), []).append(rec["slug"])

    for name in sorted(buckets):
        print(f"  {len(buckets[name]):4d}  {name}")

    wanted = buckets.get("no components", []) + buckets.get("partial", []) + buckets.get("no runs", [])
    if include_no_input:
        wanted += buckets.get("no recognised input", [])

    out = ROOT / "rerun_failures.tsv"
    out.write_text("".join(rows[s] + "\n" for s in sorted(wanted)))
    print(f"\nselected {len(wanted)} projects -> {out}")
    if not include_no_input:
        print(f"excluded {len(buckets.get('no recognised input', []))} 'no recognised input' "
              f"(no merged fix touches discovery; pass --include-no-input to add them)")


if __name__ == "__main__":
    main()
