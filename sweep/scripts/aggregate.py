#!/usr/bin/env python3
"""Aggregate the per-project records into the numbers the report quotes.

The one derived judgement made here is *ecosystem match*: whether anything
the wizard discovered actually belongs to the language the project is written
in. A run that exits 0 having described a C project's Python test harness is
not a success, and no per-project field records that on its own -- it needs
the project's declared stack, which lives in projects.tsv.
"""

import json
import pathlib
import sys
from collections import Counter, defaultdict

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")

# Which lockfile ecosystems count as "describes this project" for a project
# whose primary stack is X. The wizard labels ecosystems with these names.
ECO_OK = {
    "python": {"python"},
    "javascript": {"javascript"},
    "go": {"go"},
    "rust": {"rust"},
    "java": {"java"},
    "ruby": {"ruby"},
    "php": {"php"},
    "dotnet": {"dotnet"},
    "cpp": {"cpp"},
    "elixir": {"elixir"},
    "dart": {"dart"},
    "swift": {"swift"},
    "scala": {"scala", "java"},   # sbt projects are read via the JVM tooling
    "terraform": {"terraform"},
    # Polyglot projects are genuinely several stacks; any real hit counts.
    "polyglot": {"python", "javascript", "go", "php", "dart", "ruby", "java", "rust"},
    # These are the deliberately-unsupported controls (Haskell, Lua, Perl,
    # Julia, Crystal, Zig, OCaml, Erlang). Nothing can legitimately match.
    "other": set(),
}


def load():
    out = []
    for f in sorted((ROOT / "meta").glob("*.json")):
        try:
            r = json.loads(f.read_text())
        except Exception:
            continue
        # The orchestrator's csv.writer terminates rows with \r\n, so the
        # last field arrives with a trailing CR. Cosmetic, but it would
        # otherwise show up inside quoted notes in the report.
        if isinstance(r.get("note"), str):
            r["note"] = r["note"].rstrip("\r")
        out.append(r)
    return out


def classify(r):
    """Bucket one record into a single outcome label."""
    if r.get("error") == "clone_failed":
        return "clone_failed"
    if r.get("error") == "no_lockfile_discovered":
        return "no_lockfile"
    comps = (r.get("sbom") or {}).get("components")
    if r.get("strict_rc") == 0:
        return "ok_strict" if comps else "empty_sbom"
    if r.get("fallback_rc") == 0:
        return "ok_only_with_fallback" if comps else "empty_sbom"
    return "failed"


def eco_match(r):
    """True when at least one discovered lockfile is of the project's stack."""
    allowed = ECO_OK.get(r["ecosystem"], set())
    if not allowed:
        return False
    return any(d.get("ecosystem") in allowed for d in r.get("discovered") or [])


def main():
    recs = [r for r in load() if r.get("kind")]
    n = len(recs)
    print(f"# records: {n}\n")

    # ---------------------------------------------------------- outcomes
    out = Counter(classify(r) for r in recs)
    print("## Outcome")
    for k, v in out.most_common():
        print(f"  {k:26s} {v:4d}  {100*v/n:5.1f}%")

    # -------------------------------------------------- outcome by stack
    print("\n## Outcome by ecosystem")
    by = defaultdict(Counter)
    for r in recs:
        by[r["ecosystem"]][classify(r)] += 1
    hdr = ["ok_strict", "ok_only_with_fallback", "failed", "no_lockfile",
           "empty_sbom", "clone_failed"]
    print(f"  {'stack':12s} {'n':>3s} " + " ".join(f"{h[:9]:>9s}" for h in hdr))
    for eco in sorted(by):
        c = by[eco]
        tot = sum(c.values())
        print(f"  {eco:12s} {tot:3d} " + " ".join(f"{c[h]:9d}" for h in hdr))

    # ------------------------------------------------- wrong-stack SBOMs
    print("\n## Ecosystem mismatch (SBOM produced, but not of this stack)")
    mismatch = [r for r in recs
                if r["kind"] == "repo" and classify(r).startswith("ok")
                and not eco_match(r)]
    print(f"  {len(mismatch)} of {len([r for r in recs if r['kind']=='repo'])} repos")
    for r in sorted(mismatch, key=lambda r: r["ecosystem"]):
        s = r.get("sbom") or {}
        print(f"    {r['ecosystem']:10s} {r['slug']:45s} -> {r.get('target_lockfile')} "
              f"({s.get('components')} comps)")

    # ------------------------------------------------- quality (coverage)
    print("\n## Field coverage, weighted by component (repos with an SBOM)")
    fields = ["license", "purl", "version", "description", "supplier",
              "author", "hashes", "extrefs", "vcs", "cpe"]
    tot_comps = 0
    got = Counter()
    for r in recs:
        s = r.get("sbom") or {}
        c = s.get("components") or 0
        if not c:
            continue
        tot_comps += c
        for f in fields:
            got[f] += (s.get("counts") or {}).get(f, 0)
    print(f"  components analysed: {tot_comps}")
    for f in fields:
        print(f"    {f:12s} {100*got[f]/tot_comps:5.1f}%")

    # ------------------------------------------------------------- NTIA
    # The seven NTIA minimum elements, as far as they can be judged from the
    # document alone. "Author" and "timestamp" are document-level and are
    # reported per SBOM; the rest are per component and are reported as the
    # share of components carrying them.
    print("\n## NTIA minimum elements")
    docs = [r for r in recs if (r.get("sbom") or {}).get("components")]
    ts = sum(1 for r in docs if (r.get("sbom") or {}).get("timestamp"))
    print(f"  document timestamp        {ts}/{len(docs)} SBOMs")
    print(f"  supplier name             {100*got['supplier']/tot_comps:5.1f}% of components")
    print(f"  component name            100.0% (structurally required)")
    print(f"  component version         {100*got['version']/tot_comps:5.1f}%")
    print(f"  unique identifier (purl)  {100*got['purl']/tot_comps:5.1f}%")
    withdeps = sum(1 for r in docs if (r.get("sbom") or {}).get("dependency_edges"))
    print(f"  dependency relationships  {withdeps}/{len(docs)} SBOMs have any edge")
    # An SBOM is only NTIA-complete if every element is present at once.
    complete = sum(1 for r in docs
                   if (r.get("sbom") or {}).get("timestamp")
                   and (r.get("sbom") or {}).get("dependency_edges")
                   and ((r.get("sbom") or {}).get("coverage") or {}).get("supplier") == 100.0
                   and ((r.get("sbom") or {}).get("coverage") or {}).get("version") == 100.0
                   and ((r.get("sbom") or {}).get("coverage") or {}).get("purl") == 100.0)
    print(f"  --> all elements at once: {complete}/{len(docs)} SBOMs")

    # ----------------------------------------------------- enrichment mix
    print("\n## Enrichment source attribution (components stamped)")
    src = Counter()
    enriched = 0
    for r in recs:
        s = r.get("sbom") or {}
        for k, v in (s.get("enrichment_sources") or {}).items():
            src[k] += v
        enriched += s.get("enriched_components") or 0
    print(f"  components carrying an enrichment stamp: {enriched} "
          f"({100*enriched/tot_comps:.1f}% of {tot_comps})")
    for k, v in src.most_common():
        print(f"    {k:22s} {v:6d}  {100*v/max(enriched,1):5.1f}%")

    # --------------------------------------------------- version quality
    print("\n## Version quality")
    ph = sum((r.get("sbom") or {}).get("version_placeholder_count") or 0 for r in recs)
    rootph = sum(1 for r in recs if (r.get("sbom") or {}).get("root_version_placeholder"))
    withsbom = [r for r in recs if (r.get("sbom") or {}).get("components")]
    print(f"  components with a placeholder version: {ph}")
    print(f"  root components versioned 'latest'/empty: {rootph} of {len(withsbom)}")

    # ------------------------------------------------------ graph quality
    print("\n## Dependency graph")
    flat = [r for r in withsbom if not (r.get("sbom") or {}).get("dependency_edges")]
    print(f"  SBOMs with zero dependency edges: {len(flat)} of {len(withsbom)}")

    # ------------------------------------------------------------- specs
    print("\n## Spec versions / generators")
    print("  spec:", dict(Counter((r.get("sbom") or {}).get("spec_version")
                                  for r in withsbom)))
    tools = Counter()
    for r in withsbom:
        for t in (r.get("sbom") or {}).get("tools") or []:
            tools[t.split("@")[0]] += 1
    print("  generator:", dict(tools.most_common()))

    # --------------------------------------------------------- durations
    ds = sorted(r.get("duration_s", 0) for r in recs)
    if ds:
        print(f"\n## Runtime  median {ds[len(ds)//2]}s  p90 {ds[int(len(ds)*0.9)]}s  max {ds[-1]}s")


if __name__ == "__main__":
    main()
