#!/usr/bin/env python3
"""Coverage sweep over the 249 projects added in the second expansion.

A different question from the v2 comparison. These have no baseline, so there
is nothing to improve on: what they answer is whether the tool produces
anything at all when pointed at an ecosystem or a repository shape it has
never been measured against. Twelve of the ecosystems here had no coverage
before, and three of those (Haskell, Erlang, Clojure) gained it in #357, which
makes the remaining nine the honest measure of what is still missing.
"""

import json
import pathlib
from collections import defaultdict

V3 = pathlib.Path("/home/ubuntu/sbomify-eval/v3")
NEW_ECOSYSTEMS = {"haskell", "ocaml", "clojure", "erlang", "perl", "r",
                  "julia", "lua", "nim", "zig", "nix", "kotlin"}
NOW_SUPPORTED = {"haskell", "erlang", "clojure", "kotlin"}


def main():
    rows = []
    for f in V3.glob("meta/*.json"):
        try:
            rows.append(json.loads(f.read_text()))
        except Exception:
            continue

    eco = defaultdict(lambda: {"n": 0, "sbom": 0, "empty": 0, "nolock": 0, "comps": []})
    for r in rows:
        e = r.get("ecosystem") or "?"
        s = r.get("sbom") or {}
        b = eco[e]
        b["n"] += 1
        if r.get("error") == "no_lockfile_discovered":
            b["nolock"] += 1
        n = s.get("components")
        if n:
            b["sbom"] += 1
            b["comps"].append(n)
        elif n == 0:
            b["empty"] += 1

    out = []
    for name, b in sorted(eco.items(), key=lambda kv: (-kv[1]["n"], kv[0])):
        c = sorted(b["comps"])
        out.append({
            "ecosystem": name,
            "run": b["n"],
            "with_sbom": b["sbom"],
            "empty": b["empty"],
            "no_lockfile": b["nolock"],
            "median": c[len(c) // 2] if c else 0,
            "is_new": name in NEW_ECOSYSTEMS,
            "supported": name in NOW_SUPPORTED,
        })

    print(json.dumps({
        "done": len(rows),
        "total": 249,
        "with_sbom": sum(b["sbom"] for b in eco.values()),
        "no_lockfile": sum(b["nolock"] for b in eco.values()),
        "rows": out,
    }, indent=1))


if __name__ == "__main__":
    main()
