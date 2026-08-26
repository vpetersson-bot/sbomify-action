#!/usr/bin/env python3
"""Work list for the projects the sweep's own concurrency rate-limited.

Six parallel workers all pulling from repo.maven.apache.org earned 44 HTTP
429s -- roughly a third of the JVM corpus. Those runs measured the sweep, not
the product, so they are neither a pass nor a defect until re-run slowly.

Only includes projects that produced nothing. A project that hit a 429 on one
generator and still produced a document was not actually blocked.
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
META = ROOT / "arm64/meta"
LOGS = ROOT / "arm64/logs"

#: Signatures of the network refusing us, as opposed to the project failing.
THROTTLED = (
    "429",
    "CantDownloadModule",
    "Error downloading",
    "Could not transfer",
    "Connection reset",
    "Read timed out",
)

refs = {}
for line in (ROOT / "arm64_all.tsv").read_text().splitlines():
    parts = line.split("\t")
    if len(parts) >= 3:
        refs[parts[0]] = (parts[1], parts[2])

rows, had_output = [], 0
for f in sorted(META.glob("*.json")):
    if not f.stat().st_size:
        continue
    rec = json.loads(f.read_text())
    if rec.get("error"):
        continue
    slug = rec["slug"]
    s = rec.get("strict_sbom") or {}
    fb = rec.get("fallback_sbom") or {}
    if (s.get("components") or 0) or (fb.get("components") or 0):
        continue  # produced something despite the noise

    log = LOGS / (slug.replace("/", "_") + ".log")
    if not log.exists():
        continue
    try:
        text = log.read_text(errors="ignore")
    except OSError:
        continue
    if not any(m in text for m in THROTTLED):
        continue

    ref, target = refs.get(slug, (None, ""))
    if ref:
        rows.append((slug, ref, target))

out = ROOT / "ratelimited.tsv"
with out.open("w") as fh:
    for slug, ref, target in rows:
        fh.write(f"{slug}\t{ref}\t{target}\n")

print(f"wrote {out} with {len(rows)} projects throttled AND empty")
for slug, _ref, target in rows:
    print(f"   {slug:40s} {target[:36]}")
