#!/usr/bin/env python3
"""For each silently-empty SBOM, count what its input actually declared.

"Zero components" is only a defect if the input had something to find. lodash
genuinely has no runtime dependencies, and a header-only C++ library has none
either -- so the finding needs the input side, not just the output side.

Fetches the input file from GitHub at the exact ref the run used, so the answer
is about the same bytes the tool saw. No clone, no container.
"""

import json
import pathlib
import re
import urllib.request

META = pathlib.Path("/home/ubuntu/sbomify-eval/v5/meta")
CORPUS = pathlib.Path("/home/ubuntu/sbomify-eval/projects_v5.tsv")


def refs() -> dict[str, str]:
    out = {}
    for line in CORPUS.read_text().splitlines():
        if not line.strip():
            continue
        _eco, slug, _url, _note, ref = line.split("\t")
        out[slug] = ref
    return out


def fetch(slug: str, ref: str, path: str) -> str | None:
    if ref == "@default":
        ref = "HEAD"
    url = f"https://raw.githubusercontent.com/{slug}/{ref}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        return f"__ERROR__{type(e).__name__}: {e}"


def declared(path: str, text: str) -> int | None:
    """How many dependencies the input names. None when we cannot tell."""
    name = path.rsplit("/", 1)[-1]
    try:
        if name == "composer.lock":
            d = json.loads(text)
            return len(d.get("packages") or []) + len(d.get("packages-dev") or [])
        if name == "package-lock.json":
            d = json.loads(text)
            # v2/v3 keep every installed tree under "packages", including the
            # root as "". v1 uses "dependencies".
            pkgs = d.get("packages")
            if pkgs is not None:
                return len([k for k in pkgs if k])
            return len(d.get("dependencies") or {})
        if name == "rebar.lock":
            # erlang term format; each dependency is a {<<"name">>,... tuple
            return len(re.findall(r"<<\"", text)) // 2 or None
        if name == "stack.yaml.lock":
            # one "completed:" block per pinned extra-dep
            return len(re.findall(r"^\s*-\s*completed:", text, re.M))
        if name == "stack.yaml":
            # extra-deps is the only place stack.yaml names packages; the
            # resolver line is a snapshot, not a dependency.
            block = re.search(r"^extra-deps:\s*$(.*?)(?=^\S|\Z)", text, re.M | re.S)
            return len(re.findall(r"^\s*-\s+\S", block.group(1), re.M)) if block else 0
        if name == "requirements.txt":
            return len([
                ln for ln in text.splitlines()
                if ln.strip() and not ln.lstrip().startswith(("#", "-r", "--"))
            ])
        if name == "pyproject.toml":
            # PEP 621 dependencies and poetry's table; counting entries rather
            # than parsing TOML, which is enough to answer "was there anything".
            deps = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.M | re.S)
            n = len(re.findall(r"[\"']", deps.group(1))) // 2 if deps else 0
            poetry = re.search(
                r"^\[tool\.poetry\.dependencies\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S
            )
            if poetry:
                n += len(re.findall(r"^\s*[A-Za-z0-9_.-]+\s*=", poetry.group(1), re.M))
            return n
        if name.endswith((".csproj", ".fsproj", ".vbproj")):
            return len(re.findall(r"<PackageReference\b", text))
        if name.endswith(".sln"):
            # A solution names projects, not packages. Nothing to lose here, so
            # an empty document is not evidence of anything.
            return None
        if name == "composer.json":
            d = json.loads(text)
            return len(d.get("require") or {}) + len(d.get("require-dev") or {})
    except Exception:
        return None
    return None


def collect() -> list[tuple[str, str, int | None | str, str]]:
    """Every silently-empty document, with what its input declared.

    Exposed so final_report.py can use the same classification rather than
    keeping its own. One fact, one implementation.
    """
    ref_of = refs()
    rows = []
    for f in sorted(META.glob("*.json")):
        if not f.stat().st_size:
            continue
        rec = json.loads(f.read_text())
        for run in rec.get("runs") or [rec]:
            sbom = run.get("sbom") or {}
            if run.get("strict_rc") != 0 or sbom.get("components") != 0:
                continue
            slug = rec["slug"]
            path = run.get("target_lockfile")
            if not path:
                continue
            text = fetch(slug, ref_of.get(slug, "HEAD"), path)
            if text is None or text.startswith("__ERROR__"):
                rows.append((slug, path, "unfetchable", (text or "")[:40]))
                continue
            rows.append((slug, path, declared(path, text), f"{len(text)} bytes"))
    return rows


def main() -> None:
    rows = collect()
    print(f"{'project':32s} {'input':26s} {'declared':>9s}  note")
    lost = 0
    for slug, path, n, note in rows:
        print(f"{slug:32s} {str(path)[:26]:26s} {str(n):>9s}  {note}")
        if isinstance(n, int) and n > 0:
            lost += 1
    print()
    print(f"{lost} of {len(rows)} empty documents came from an input that declared dependencies")


if __name__ == "__main__":
    main()
