#!/usr/bin/env python3
"""Re-resolve only the projects the audit flagged, and patch the corpus.

Re-running all 500 costs forty minutes of API calls to change four rows. This
re-resolves the four, plus every project whose current ref would now be
rejected by the tightened classifier, and rewrites projects_v5.tsv in place.

Prints a before/after for each so the change is reviewable rather than
implicit.
"""

import json
import pathlib
import sys

sys.path.insert(0, "/home/ubuntu/sbomify-eval")
from resolve_releases import _is_release_tag, _sort_key, newest_release, newest_tag  # noqa: E402

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
CORPUS = ROOT / "projects_v5.tsv"

rows = [ln.rstrip("\n").split("\t") for ln in CORPUS.read_text().splitlines() if ln.strip()]

# Anything whose current ref the tightened rules would no longer accept.
suspect = []
for eco, slug, url, note, ref in rows:
    if ref == "@default":
        continue
    if not _is_release_tag(ref, slug):
        suspect.append((slug, ref))

print(f"{len(suspect)} project(s) hold a ref the tightened classifier rejects:")
for slug, ref in suspect:
    print(f"  {slug:40s} {ref}")

if not suspect:
    print("\nnothing to patch")
    raise SystemExit

fixed, unchanged = {}, []
for slug, old in suspect:
    url = next(r[2] for r in rows if r[1] == slug)
    found = [c for c in (newest_release(slug), newest_tag(slug, url)) if c]
    new = max(found, key=lambda c: _sort_key(c[0]))[0] if found else "@default"
    if new != old:
        fixed[slug] = new
    else:
        unchanged.append(slug)

print("\nre-resolved:")
for slug, new in fixed.items():
    was = dict(suspect)[slug]
    print(f"  {slug:40s} {was:26s} -> {new}")
for slug in unchanged:
    print(f"  {slug:40s} unchanged")

patched = [[*r[:4], fixed.get(r[1], r[4])] for r in rows]
CORPUS.write_text("".join("\t".join(r) + "\n" for r in patched))
(ROOT / "v5_refs.json").write_text(json.dumps({r[1]: r[4] for r in patched}, indent=1))
print(f"\npatched {len(fixed)} row(s) in {CORPUS.name}")
