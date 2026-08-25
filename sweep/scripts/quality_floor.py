#!/usr/bin/env python3
"""Does the component count clear the floor the project's own manifest sets?

The obvious comparison -- components against entries in the lockfile -- is
wrong, and produced a spectacular false finding before this script existed:
twbs/bootstrap "reporting 1 component from a lockfile of 1346", microsoft
/TypeScript "1 of 394". Both are correct. A lockfile resolves *everything*
including the dev tree, the action reports required dependencies only, and
TypeScript has zero runtime dependencies against forty-two dev ones. The
denominator was measuring the wrong thing and every ratio built on it was
meaningless.

So the expectation used here is a floor rather than a target: whatever a
project lists as its own runtime dependencies must appear, because the
transitive closure of a set cannot be smaller than the set. Coming in *above*
the floor is the normal, healthy case -- that is transitivity. Coming in below
it means the document is missing something the project explicitly declares,
which needs no ratio to be a defect.
"""

import json
import os
import pathlib
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
CORPUS = ROOT / "projects_v5.tsv"
META = pathlib.Path(os.environ.get("SBOMIFY_EVAL_META") or (ROOT / "v5/meta"))
CACHE = ROOT / ".manifest-cache"

#: Where a project states its own runtime dependencies, per input. Only inputs
#: whose manifest is unambiguous are listed; anything else is skipped rather
#: than guessed at.
MANIFEST_FOR = {
    "package-lock.json": "package.json",
    "pnpm-lock.yaml": "package.json",
    "yarn.lock": "package.json",
    "bun.lock": "package.json",
    "package.json": "package.json",
    "composer.lock": "composer.json",
    "composer.json": "composer.json",
    "Cargo.lock": "Cargo.toml",
    "Cargo.toml": "Cargo.toml",
}


def refs() -> dict[str, str]:
    out = {}
    for line in CORPUS.read_text().splitlines():
        if line.strip():
            f = line.split("\t")
            out[f[1]] = f[4]
    return out


def fetch(slug: str, ref: str, path: str) -> str | None:
    CACHE.mkdir(exist_ok=True)
    key = CACHE / (slug.replace("/", "_") + "__" + path.replace("/", "_"))
    if key.exists():
        return key.read_text() or None
    url = f"https://raw.githubusercontent.com/{slug}/{'HEAD' if ref == '@default' else ref}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            data = r.read(4 * 1024 * 1024).decode("utf-8", "replace")
    except Exception:
        key.write_text("")
        return None
    key.write_text(data)
    return data


def direct_runtime_deps(manifest: str, text: str) -> int | None:
    """How many runtime dependencies the project declares for itself."""
    try:
        if manifest == "package.json":
            d = json.loads(text)
            # dependencies only. devDependencies are build-time and are exactly
            # what --required-only is meant to leave out.
            return len(d.get("dependencies") or {})
        if manifest == "composer.json":
            d = json.loads(text)
            req = d.get("require") or {}
            # php itself and ext-* are platform requirements, not packages.
            return len([k for k in req if k != "php" and not k.startswith("ext-")])
        if manifest == "Cargo.toml":
            block = re.search(r"^\[dependencies\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
            if not block:
                return 0
            return len(re.findall(r"^\s*[A-Za-z0-9_-]+\s*=", block.group(1), re.M))
    except Exception:
        return None
    return None


def main() -> None:
    ref_of = refs()
    runs = []
    for f in sorted(META.glob("*.json")):
        if not f.stat().st_size:
            continue
        rec = json.loads(f.read_text())
        for run in rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else []):
            n = (run.get("sbom") or {}).get("components")
            target = run.get("target_lockfile") or ""
            base = target.rsplit("/", 1)[-1]
            if n and base in MANIFEST_FOR:
                runs.append((rec, run, n, target, base))

    def work(item):
        rec, run, n, target, base = item
        manifest = MANIFEST_FOR[base]
        # The manifest sits beside the lockfile, not necessarily at the root.
        prefix = target[: -len(base)]
        text = fetch(rec["slug"], ref_of.get(rec["slug"], "HEAD"), prefix + manifest)
        if text is None:
            return None
        return (rec, run, n, target, direct_runtime_deps(manifest, text))

    with ThreadPoolExecutor(max_workers=12) as pool:
        rows = [r for r in pool.map(work, runs) if r and isinstance(r[4], int)]

    print(f"runs with a countable manifest: {len(rows)} of {len(runs)}\n")

    below = [r for r in rows if r[2] < r[4]]
    at_zero = [r for r in rows if r[4] == 0]
    healthy = [r for r in rows if r[2] >= r[4] and r[4] > 0]

    print(f"   clears the floor           {len(healthy):4d}")
    print(f"   project declares none      {len(at_zero):4d}  (a 1-component document is correct here)")
    print(f"   BELOW the floor            {len(below):4d}  <- misses something the project declares")

    if below:
        print("\ndocuments missing dependencies the project explicitly declares:")
        for rec, run, n, target, floor in sorted(below, key=lambda x: x[4] - x[2], reverse=True):
            print(f"   {rec['ecosystem']:11s} {rec['slug']:32s} {target[:24]:24s} {n:4d} components, "
                  f"{floor:3d} declared direct")

    print("\nfor contrast, the largest healthy expansions (transitivity working):")
    for rec, run, n, target, floor in sorted(healthy, key=lambda x: -(x[2] / max(x[4], 1)))[:8]:
        print(f"   {rec['ecosystem']:11s} {rec['slug']:32s} {floor:3d} declared -> {n:5d} components")


if __name__ == "__main__":
    main()
