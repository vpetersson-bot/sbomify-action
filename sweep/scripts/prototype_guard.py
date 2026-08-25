#!/usr/bin/env python3
"""Which projects would a foreign-subject guard fire on, and would it be right?

The rule under test: a repository declares its language at its root, even when
we cannot read that file. rabbitmq-server has rebar.config; curl has
CMakeLists.txt. If the input we ended up scanning belongs to a different
ecosystem, the document is describing something other than the project.

Run against the corpus before writing any of it, because a guard that fires on
polyglot monorepos -- where several ecosystems legitimately live at the root --
would be worse than the problem. The question is not whether the rule catches
rabbitmq; it is what else it catches.
"""

import json
import pathlib
from collections import Counter

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
META = ROOT / "v5/meta"

#: Files that say "this repository is written in X", whether or not the tool
#: can read them. Deliberately wider than the set of supported inputs: the
#: point is to know the project's language, not to scan it.
ROOT_MARKERS = {
    "erlang": ("rebar.config", "erlang.mk"),
    "elixir": ("mix.exs",),
    "go": ("go.mod",),
    "rust": ("Cargo.toml",),
    "python": ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"),
    "javascript": ("package.json",),
    "php": ("composer.json",),
    "ruby": ("Gemfile", "Rakefile"),
    "java": ("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"),
    "scala": ("build.sbt",),
    "clojure": ("deps.edn", "project.clj"),
    "dart": ("pubspec.yaml",),
    "swift": ("Package.swift",),
    "haskell": ("stack.yaml", "cabal.project"),
    "cpp": ("CMakeLists.txt", "configure.ac", "meson.build", "conanfile.txt", "conanfile.py"),
    "dotnet": (),  # matched by suffix below
}


def root_ecosystems(discovered: list[dict]) -> set[str]:
    """Ecosystems evidenced at depth 1, from what discovery already recorded."""
    found = set()
    for row in discovered:
        if row.get("depth") != 1:
            continue
        name = row["path"].rsplit("/", 1)[-1]
        for eco, markers in ROOT_MARKERS.items():
            if name in markers:
                found.add(eco)
        if name.endswith((".csproj", ".fsproj", ".vbproj", ".sln")):
            found.add("dotnet")
    return found


def main() -> None:
    fires, quiet, no_signal = [], 0, 0
    for f in sorted(META.glob("*.json")):
        if not f.stat().st_size:
            continue
        rec = json.loads(f.read_text())
        discovered = [d for d in (rec.get("discovered") or []) if not d.get("nested_repo")]
        runs = rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else [])
        if not runs or not discovered:
            continue

        roots = root_ecosystems(discovered)
        if not roots:
            no_signal += 1
            continue

        for run in runs:
            target = run.get("target_lockfile")
            if not target:
                continue
            scanned = next((d["ecosystem"] for d in discovered if d["path"] == target), None)
            if scanned and scanned not in roots:
                fires.append(
                    (rec["ecosystem"], rec["slug"], target, scanned, sorted(roots),
                     (run.get("sbom") or {}).get("components"))
                )
            else:
                quiet += 1

    print(f"would fire on {len(fires)} run(s); {quiet} quiet; {no_signal} project(s) with no root signal\n")
    for eco, slug, target, scanned, roots, n in sorted(fires, key=lambda x: -(x[5] or 0)):
        print(f"   {eco:11s} {slug:30s} scanned {scanned:11s} {str(target)[:34]:34s} "
              f"root says {','.join(roots):22s} {n} components")

    print("\nby project ecosystem:")
    for eco, n in Counter(x[0] for x in fires).most_common():
        print(f"   {eco:12s} {n}")


if __name__ == "__main__":
    main()
