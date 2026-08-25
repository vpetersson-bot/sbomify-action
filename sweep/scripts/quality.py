#!/usr/bin/env python3
"""Are the SBOMs any good, and do they match what they were made from?

Two questions, and only the second is hard.

Field coverage comes straight from the documents. "Does it make sense given
the input" needs the input, so each lockfile is fetched at the same ref the
run used and its entries counted. A lockfile enumerates a resolved dependency
set, so its entry count is a defensible expectation for the component count --
not an exact one, because tools differ on whether the root package, dev
dependencies, or platform packages are components, but close enough that an
order-of-magnitude gap is a finding rather than noise.

Counting is deliberately conservative: only formats with an unambiguous entry
marker are counted, and anything else is reported as unknown rather than
guessed at. A ratio computed from a bad denominator would manufacture exactly
the kind of finding this project keeps having to withdraw.
"""

import argparse
import json
import os
import pathlib
import re
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
CORPUS = ROOT / "projects_v5.tsv"
META = pathlib.Path(os.environ.get("SBOMIFY_EVAL_META") or (ROOT / "v5/meta"))
CACHE = ROOT / ".input-cache"
MAX_BYTES = 12 * 1024 * 1024


def refs() -> dict[str, str]:
    out = {}
    for line in CORPUS.read_text().splitlines():
        if line.strip():
            f = line.split("\t")
            out[f[1]] = f[4]
    return out


def fetch(slug: str, ref: str, path: str) -> str | None:
    CACHE.mkdir(exist_ok=True)
    key = CACHE / (slug.replace("/", "_") + "__" + path.replace("/", "_"))[:200]
    if key.exists():
        return key.read_text()
    url = f"https://raw.githubusercontent.com/{slug}/{'HEAD' if ref == '@default' else ref}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=45) as r:
            data = r.read(MAX_BYTES).decode("utf-8", "replace")
    except Exception:
        return None
    key.write_text(data)
    return data


def declared(path: str, text: str) -> int | None:
    """Entries the input enumerates, or None when we cannot count reliably."""
    name = path.rsplit("/", 1)[-1]
    try:
        if name == "package-lock.json":
            d = json.loads(text)
            pkgs = d.get("packages")
            if pkgs is not None:
                return len([k for k in pkgs if k])
            return len(d.get("dependencies") or {})
        if name == "composer.lock":
            d = json.loads(text)
            return len(d.get("packages") or []) + len(d.get("packages-dev") or [])
        if name in ("Cargo.lock", "poetry.lock", "uv.lock", "Pipfile.lock"):
            if name == "Pipfile.lock":
                d = json.loads(text)
                return len(d.get("default") or {}) + len(d.get("develop") or {})
            return len(re.findall(r"^\[\[package\]\]", text, re.M))
        if name == "Gemfile.lock":
            # Indented two spaces under specs:, one per resolved gem.
            block = re.search(r"^GEM\b.*?^\s*specs:\s*$(.*?)(?=^\S|\Z)", text, re.M | re.S)
            return len(re.findall(r"^    [a-zA-Z0-9_.-]+ \(", block.group(1), re.M)) if block else None
        if name == "pnpm-lock.yaml":
            block = re.search(r"^(packages|snapshots):\s*$(.*)", text, re.M | re.S)
            return len(re.findall(r"^  [^\s:][^:]*:\s*$", block.group(2), re.M)) if block else None
        if name == "go.sum":
            return len({ln.split()[0] for ln in text.splitlines() if ln.strip()})
        if name == "yarn.lock":
            return len(re.findall(r"^\"?[^#\s].*:\s*$", text, re.M))
        if name == "mix.lock":
            return len(re.findall(r"^\s+\"", text, re.M))
        if name == "pubspec.lock":
            block = re.search(r"^packages:\s*$(.*?)(?=^\w|\Z)", text, re.M | re.S)
            return len(re.findall(r"^  [a-zA-Z0-9_]+:\s*$", block.group(1), re.M)) if block else None
    except Exception:
        return None
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only inspect this many runs")
    args = ap.parse_args()

    ref_of = refs()
    runs = []
    for f in sorted(META.glob("*.json")):
        if not f.stat().st_size:
            continue
        rec = json.loads(f.read_text())
        for run in rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else []):
            n = (run.get("sbom") or {}).get("components")
            if n:
                runs.append((rec, run, n))
    if args.limit:
        runs = runs[: args.limit]

    print(f"successful runs: {len(runs)}\n")

    # ---- field coverage, straight from the documents
    fields = ["purl", "version", "license", "hashes", "supplier", "author", "description", "vcs", "cpe"]
    weighted: dict[str, float] = {k: 0.0 for k in fields}
    total_components = 0
    for _rec, run, n in runs:
        cov = (run.get("sbom") or {}).get("coverage") or {}
        total_components += n
        for k in fields:
            weighted[k] += (cov.get(k) or 0) / 100 * n

    print(f"field coverage across {total_components} components (component-weighted):")
    for k in fields:
        pct = 100 * weighted[k] / total_components if total_components else 0
        bar = "#" * int(pct / 4)
        print(f"   {k:12s} {pct:5.1f}%  {bar}")

    # ---- root component sanity
    placeholder = sum(1 for _r, run, _n in runs if (run.get("sbom") or {}).get("root_version_placeholder"))
    mount = sum(1 for _r, run, _n in runs if "workspace" in ((run.get("sbom") or {}).get("root_purl") or ""))
    no_root_licence = sum(1 for _r, run, _n in runs if not (run.get("sbom") or {}).get("root_has_license"))
    print(f"\nroot component:")
    print(f"   placeholder version        {placeholder:4d} of {len(runs)}")
    print(f"   purl names the mount point {mount:4d} of {len(runs)}")
    print(f"   no licence on the root     {no_root_licence:4d} of {len(runs)}")

    # ---- does the count make sense against the input
    print("\nfetching inputs to compare declared entries against components...")
    def work(item):
        rec, run, n = item
        path = run.get("target_lockfile")
        if not path:
            return None
        text = fetch(rec["slug"], ref_of.get(rec["slug"], "HEAD"), path)
        if text is None:
            return (rec, run, n, None)
        return (rec, run, n, declared(path, text))

    with ThreadPoolExecutor(max_workers=12) as pool:
        compared = [r for r in pool.map(work, runs) if r]

    known = [c for c in compared if isinstance(c[3], int) and c[3] > 0]
    unknown = len(compared) - len(known)
    print(f"   comparable: {len(known)}   not countable: {unknown}\n")

    buckets = Counter()
    under, over = [], []
    for rec, run, n, d in known:
        ratio = n / d
        if ratio < 0.5:
            buckets["fewer than half"] += 1
            under.append((rec, run, n, d, ratio))
        elif ratio > 2:
            buckets["more than double"] += 1
            over.append((rec, run, n, d, ratio))
        elif 0.9 <= ratio <= 1.1:
            buckets["within 10%"] += 1
        else:
            buckets["within a factor of 2"] += 1

    print("components vs entries the input declares:")
    for k in ("within 10%", "within a factor of 2", "more than double", "fewer than half"):
        if buckets[k]:
            print(f"   {buckets[k]:4d}  {k}")

    print(f"\nworst under-reporting (component count far below what the input lists):")
    for rec, run, n, d, ratio in sorted(under, key=lambda x: x[4])[:15]:
        print(f"   {rec['ecosystem']:11s} {rec['slug']:32s} {str(run.get('target_lockfile'))[:20]:20s} {n:5d} of {d:5d}  ({ratio:.0%})")

    if over:
        print(f"\nmore components than the input declares (usually the root, or dev/optional trees):")
        for rec, run, n, d, ratio in sorted(over, key=lambda x: -x[4])[:8]:
            print(f"   {rec['ecosystem']:11s} {rec['slug']:32s} {str(run.get('target_lockfile'))[:20]:20s} {n:5d} of {d:5d}  ({ratio:.1f}x)")


if __name__ == "__main__":
    main()
