#!/usr/bin/env python3
"""Which empty documents are actually defects.

"Defect" has to mean something falsifiable or it is just a label for
everything we did not like. The definition used here:

    the input names runtime dependencies, and the document has none.

Everything else that comes back empty is correct behaviour wearing a
suspicious shape -- a `.sln` names projects rather than packages, a `.csproj`
can have no PackageReference at all, and plenty of well-known projects have no
runtime dependencies whatsoever.

This is the second time the denominator has decided the answer. Comparing
against lockfile entries produced "lodash: 493 declared, 0 found", which was
reported as the clearest defect in the corpus. lodash's package.json declares
**zero** runtime dependencies; the 493 were its dev tree, which the action
deliberately excludes. The document was right and the measurement was wrong.
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

MANIFEST_FOR = {
    "package-lock.json": "package.json",
    "pnpm-lock.yaml": "package.json",
    "yarn.lock": "package.json",
    "package.json": "package.json",
    "composer.lock": "composer.json",
    "composer.json": "composer.json",
    "Cargo.lock": "Cargo.toml",
    "Cargo.toml": "Cargo.toml",
    "pyproject.toml": "pyproject.toml",
    "requirements.txt": "requirements.txt",
    "Gemfile.lock": "Gemfile.lock",
    "go.mod": "go.mod",
    "go.sum": "go.mod",
}


def refs() -> dict[str, str]:
    return {
        line.split("\t")[1]: line.split("\t")[4]
        for line in CORPUS.read_text().splitlines()
        if line.strip()
    }


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


def runtime_deps(manifest: str, text: str) -> int | None:
    try:
        if manifest == "package.json":
            return len(json.loads(text).get("dependencies") or {})
        if manifest == "composer.json":
            req = json.loads(text).get("require") or {}
            return len([k for k in req if k != "php" and not k.startswith(("ext-", "lib-"))])
        if manifest == "Cargo.toml":
            block = re.search(r"^\[dependencies\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
            if not block:
                return 0
            lines = re.findall(r"^\s*[A-Za-z0-9_-]+\s*=.*$", block.group(1), re.M)
            return len([ln for ln in lines if not re.search(r"optional\s*=\s*true", ln)])
        if manifest == "pyproject.toml":
            m = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.M | re.S)
            return len(re.findall(r"[\"']", m.group(1))) // 2 if m else 0
        if manifest == "requirements.txt":
            return len([
                ln for ln in text.splitlines()
                if ln.strip() and not ln.lstrip().startswith(("#", "-r", "--"))
            ])
        if manifest == "Gemfile.lock":
            block = re.search(r"^GEM\b.*?^\s*specs:\s*$(.*?)(?=^\S|\Z)", text, re.M | re.S)
            return len(re.findall(r"^    [a-zA-Z0-9_.-]+ \(", block.group(1), re.M)) if block else None
        if manifest == "go.mod":
            block = re.search(r"^require\s*\((.*?)^\)", text, re.M | re.S)
            return len(re.findall(r"^\s+\S+\s+v", block.group(1), re.M)) if block else None
    except Exception:
        return None
    return None


def main() -> None:
    ref_of = refs()
    empties = []
    for f in sorted(META.glob("*.json")):
        if not f.stat().st_size:
            continue
        rec = json.loads(f.read_text())
        runs = rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else [])
        if not runs or any((r.get("sbom") or {}).get("components") for r in runs):
            continue
        for run in runs:
            target = run.get("target_lockfile") or ""
            base = target.rsplit("/", 1)[-1]
            if base in MANIFEST_FOR:
                empties.append((rec, run, target, base))
                break

    def work(item):
        rec, run, target, base = item
        manifest = MANIFEST_FOR[base]
        prefix = target[: -len(base)]
        text = fetch(rec["slug"], ref_of.get(rec["slug"], "HEAD"), prefix + manifest)
        if text is None:
            return (rec, target, None)
        return (rec, target, runtime_deps(manifest, text))

    with ThreadPoolExecutor(max_workers=12) as pool:
        rows = list(pool.map(work, empties))

    real = [(r, t, d) for r, t, d in rows if isinstance(d, int) and d > 0]
    correct = [(r, t, d) for r, t, d in rows if d == 0]
    unknown = [(r, t, d) for r, t, d in rows if d is None]

    print(f"empty documents with a countable manifest: {len(rows)}\n")
    print(f"   {len(real):4d}  DEFECT: the input names runtime dependencies and none appear")
    print(f"   {len(correct):4d}  correct: the project declares no runtime dependencies")
    print(f"   {len(unknown):4d}  cannot tell from the manifest")

    if real:
        print("\nthe real ones:")
        for rec, target, d in sorted(real, key=lambda x: -(x[2] or 0)):
            print(f"   {rec['ecosystem']:11s} {rec['slug']:32s} {target[:26]:26s} {d:3d} declared -> 0")

    if correct:
        print("\ncorrectly empty (a sample):")
        for rec, target, _d in sorted(correct, key=lambda x: x[0]["slug"])[:10]:
            print(f"   {rec['ecosystem']:11s} {rec['slug']:32s} {target[:26]}")


if __name__ == "__main__":
    main()
