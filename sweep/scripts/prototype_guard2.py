#!/usr/bin/env python3
"""The refined rule, tested against real repository roots.

First attempt derived the project's language from discovery's own records,
which only list inputs the tool can read -- so rabbitmq, whose root holds
rebar.config and erlang.mk and nothing scannable, produced no signal at all
and never appeared. The rule has to read the root.

Refined, and the second clause is what removes the noise:

    the input is *nested*, and its ecosystem is nowhere at the root

A root-level input is the project's own, however many languages share that
root -- Chart.js keeps a composer.json beside its package.json and both are
legitimate. It is a foreign ecosystem found only in a subdirectory that means
we are describing somebody else's sub-project.

Root listings come from the GitHub API at the same ref each run used.
"""

import json
import os
import pathlib
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
META = ROOT / "v5/meta"
CACHE = ROOT / ".roots-cache"

ROOT_MARKERS = {
    "erlang": ("rebar.config", "rebar.lock", "erlang.mk"),
    "elixir": ("mix.exs", "mix.lock"),
    "go": ("go.mod", "go.sum"),
    "rust": ("Cargo.toml", "Cargo.lock"),
    "python": ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile", "poetry.lock", "uv.lock"),
    "javascript": ("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock"),
    "php": ("composer.json", "composer.lock"),
    "ruby": ("Gemfile", "Gemfile.lock", "Rakefile", "*.gemspec"),
    "java": ("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"),
    "kotlin": ("build.gradle.kts", "settings.gradle.kts"),
    "scala": ("build.sbt",),
    "clojure": ("deps.edn", "project.clj"),
    "dart": ("pubspec.yaml", "pubspec.lock"),
    "swift": ("Package.swift", "Package.resolved"),
    "haskell": ("stack.yaml", "stack.yaml.lock", "cabal.project"),
    "cpp": ("CMakeLists.txt", "configure.ac", "meson.build", "conanfile.txt", "conanfile.py", "Makefile.am"),
    "lua": ("*.rockspec",),
    "nix": ("flake.nix", "default.nix"),
}


def refs() -> dict[str, str]:
    return {
        line.split("\t")[1]: line.split("\t")[4]
        for line in (ROOT / "projects_v5.tsv").read_text().splitlines()
        if line.strip()
    }


def root_listing(slug: str, ref: str) -> list[str]:
    CACHE.mkdir(exist_ok=True)
    key = CACHE / slug.replace("/", "_")
    if key.exists():
        return json.loads(key.read_text() or "[]")
    url = f"https://api.github.com/repos/{slug}/contents/?ref={'HEAD' if ref == '@default' else ref}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            names = [e["name"] for e in json.load(r) if e.get("type") == "file"]
    except Exception:
        names = []
    key.write_text(json.dumps(names))
    return names


def ecosystems_at_root(names: list[str]) -> set[str]:
    found = set()
    for eco, markers in ROOT_MARKERS.items():
        for marker in markers:
            if marker.startswith("*."):
                if any(n.endswith(marker[1:]) for n in names):
                    found.add(eco)
            elif marker in names:
                found.add(eco)
    if any(n.endswith((".csproj", ".fsproj", ".vbproj", ".sln")) for n in names):
        found.add("dotnet")
    return found


def main() -> None:
    ref_of = refs()
    records = []
    for f in sorted(META.glob("*.json")):
        if not f.stat().st_size:
            continue
        rec = json.loads(f.read_text())
        runs = rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else [])
        discovered = [d for d in (rec.get("discovered") or []) if not d.get("nested_repo")]
        if runs and discovered:
            records.append((rec, runs, discovered))

    with ThreadPoolExecutor(max_workers=10) as pool:
        listings = dict(
            zip(
                [r[0]["slug"] for r in records],
                pool.map(lambda r: root_listing(r[0]["slug"], ref_of.get(r[0]["slug"], "HEAD")), records),
            )
        )

    fires, quiet, unknown = [], 0, 0
    for rec, runs, discovered in records:
        names = listings.get(rec["slug"]) or []
        if not names:
            unknown += 1
            continue
        roots = ecosystems_at_root(names)
        for run in runs:
            target = run.get("target_lockfile")
            if not target:
                continue
            row = next((d for d in discovered if d["path"] == target), None)
            if not row:
                continue
            # The root has to say something before its silence can be
            # evidence. A monorepo with nothing at the top -- AutoGPT,
            # dotnet/runtime, localsend -- declares no language, so every
            # nested input looked foreign and the rule fired on all of them.
            nested = row["depth"] > 1
            foreign = bool(roots) and row["ecosystem"] not in roots
            if nested and foreign:
                fires.append(
                    (rec["ecosystem"], rec["slug"], target, row["ecosystem"],
                     sorted(roots), (run.get("sbom") or {}).get("components"))
                )
            else:
                quiet += 1

    print(f"fires on {len(fires)} run(s); {quiet} quiet; {unknown} project(s) whose root could not be read\n")
    for eco, slug, target, scanned, roots, n in sorted(fires, key=lambda x: -(x[5] or 0)):
        print(f"   {eco:11s} {slug:30s} {str(target)[:38]:38s} is {scanned:11s} "
              f"root: {','.join(roots)[:26]:26s} {n}")

    print("\nby project ecosystem:")
    for eco, n in Counter(x[0] for x in fires).most_common():
        print(f"   {eco:12s} {n}")


if __name__ == "__main__":
    main()
