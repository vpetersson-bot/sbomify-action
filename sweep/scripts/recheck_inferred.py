#!/usr/bin/env python3
"""How many of the 500 would now be told their versions were inferred.

The count only means something if the classification is right, and it changed
twice: go.mod left the inferred set because its format cannot express a range,
and requirements.txt is now decided by reading it rather than by its name.

Fetches each input at the ref the run used, so requirements.txt is judged on
the bytes the tool saw rather than on an assumption about them.
"""

import json
import pathlib
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from sbomify_action._generation.registry import UNRESOLVED_MANIFESTS, _requirements_txt_is_pinned

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
META = ROOT / "v5/meta-4238898-snapshot"
CACHE = ROOT / ".req-cache"

#: What the corpus classified as inferred before this change.
PREVIOUSLY_INFERRED = UNRESOLVED_MANIFESTS | {"go.mod", "requirements.txt"}


def refs() -> dict[str, str]:
    return {
        line.split("\t")[1]: line.split("\t")[4]
        for line in (ROOT / "projects_v5.tsv").read_text().splitlines()
        if line.strip()
    }


def fetch_requirements(slug: str, ref: str, path: str) -> pathlib.Path | None:
    CACHE.mkdir(exist_ok=True)
    key = CACHE / (slug.replace("/", "_") + "__" + path.replace("/", "_"))
    if not key.exists():
        url = f"https://raw.githubusercontent.com/{slug}/{'HEAD' if ref == '@default' else ref}/{path}"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                key.write_bytes(r.read(2 * 1024 * 1024))
        except Exception:
            key.write_text("")
    return key if key.stat().st_size else None


def main() -> None:
    ref_of = refs()
    rows = []
    for f in sorted(META.glob("*.json")):
        if not f.stat().st_size:
            continue
        rec = json.loads(f.read_text())
        for run in rec.get("runs") or [rec]:
            target = run.get("target_lockfile")
            if target and (run.get("sbom") or {}).get("components"):
                rows.append((rec["slug"], target, target.rsplit("/", 1)[-1]))

    def judge(row):
        slug, target, base = row
        was = base in PREVIOUSLY_INFERRED
        if base == "requirements.txt":
            local = fetch_requirements(slug, ref_of.get(slug, "HEAD"), target)
            now = not (local and _requirements_txt_is_pinned(str(local)))
        elif base == "go.mod":
            now = False
        else:
            now = base in UNRESOLVED_MANIFESTS
        return slug, base, was, now

    with ThreadPoolExecutor(max_workers=12) as pool:
        judged = list(pool.map(judge, rows))

    before = sum(1 for _s, _b, was, _now in judged if was)
    after = sum(1 for _s, _b, _was, now in judged if now)
    print(f"successful runs with an input: {len(judged)}")
    print(f"  called inferred before : {before}")
    print(f"  called inferred now    : {after}")

    changed = Counter(base for _s, base, was, now in judged if was != now)
    print("\nchanged classification:")
    for base, n in changed.most_common():
        print(f"   {n:4d}  {base}")

    pinned = [(s, b) for s, b, was, now in judged if b == "requirements.txt" and was and not now]
    if pinned:
        print(f"\nrequirements.txt files that are fully pinned, so no longer accused ({len(pinned)}):")
        for slug, _b in pinned[:12]:
            print(f"   {slug}")


if __name__ == "__main__":
    main()
