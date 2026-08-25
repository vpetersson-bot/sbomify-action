#!/usr/bin/env python3
"""Work list for re-running the projects the 2g cap starved.

A capped run that killed the build is not a result. These produced nothing
because the Gradle daemon was OOM-killed inside the cgroup, not because the
product or the architecture failed -- arrow-kt gave 0 components at 2g and
1280 at 8g. They need re-running uncapped before anything is concluded about
them, and until then they are neither a pass nor a defect.

Detected from the log rather than the record, because "Gradle build daemon
disappeared unexpectedly" is the signature and it predates the `killed` flag.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
META = ROOT / "arm64/meta"
LOGS = ROOT / "arm64/logs"

STARVED_MARKERS = (
    "daemon disappeared unexpectedly",
    "Out of memory",
    "OutOfMemoryError",
    "Killed",
    "MemoryError",
)

refs = {}
for line in (ROOT / "arm64_all.tsv").read_text().splitlines():
    parts = line.split("\t")
    if len(parts) >= 3:
        refs[parts[0]] = (parts[1], parts[2])

rows = []
for f in sorted(META.glob("*.json")):
    if not f.stat().st_size:
        continue
    rec = json.loads(f.read_text())
    if rec.get("error"):
        continue
    slug = rec["slug"]
    s = rec.get("strict_sbom") or {}
    fb = rec.get("fallback_sbom") or {}
    got = (s.get("components") or 0) or (fb.get("components") or 0)
    if got:
        continue  # produced something; not starved

    log = LOGS / (slug.replace("/", "_") + ".log")
    starved = bool(rec.get("killed"))
    if not starved and log.exists():
        try:
            text = log.read_text(errors="ignore")
            starved = any(m in text for m in STARVED_MARKERS)
        except OSError:
            pass
    # A timeout is the same story told differently: the build was still going
    # when the clock ran out, so the run says nothing about correctness.
    if rec.get("strict_rc") == 124 and rec.get("fallback_rc") == 124:
        starved = True
    if not starved:
        continue

    ref, target = refs.get(slug, (None, ""))
    if ref:
        rows.append((slug, ref, target))

out = ROOT / "starved.tsv"
with out.open("w") as fh:
    for slug, ref, target in rows:
        fh.write(f"{slug}\t{ref}\t{target}\n")

print(f"wrote {out} with {len(rows)} projects to re-run uncapped")
for slug, _ref, target in rows[:25]:
    print(f"   {slug:38s} {target[:40]}")
