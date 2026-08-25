#!/usr/bin/env python3
"""Emit every number the report quotes as one JSON blob.

Written so the narrative and the tables cannot drift apart: the report is
built from this output, not from separate ad-hoc queries.
"""

import json
import pathlib
import statistics
from collections import Counter, defaultdict

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
import sys
sys.path.insert(0, str(ROOT))
from aggregate import classify, eco_match, load  # noqa: E402


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None

FIELDS = ["license", "purl", "version", "description", "supplier",
          "author", "hashes", "extrefs", "vcs", "cpe"]


def main():
    recs = [r for r in load() if r.get("kind")]
    repos = [r for r in recs if r["kind"] == "repo"]
    withsbom = [r for r in recs if (r.get("sbom") or {}).get("components")]

    out = {"n_total": len(recs), "n_repos": len(repos),
           "n_containers": len(recs) - len(repos)}

    # Outcomes, overall and per stack.
    out["outcomes"] = dict(Counter(classify(r) for r in recs))
    by = defaultdict(Counter)
    for r in recs:
        by[r["ecosystem"]][classify(r)] += 1
    out["outcomes_by_ecosystem"] = {k: dict(v) for k, v in by.items()}

    # Did the wizard surface anything of the project's own stack?
    out["eco_match"] = {
        "matched": sum(1 for r in repos if eco_match(r)),
        "total": len(repos),
        "mismatched_with_sbom": [
            {"slug": r["slug"], "ecosystem": r["ecosystem"],
             "lockfile": r.get("target_lockfile"),
             "components": (r.get("sbom") or {}).get("components")}
            for r in repos
            if classify(r).startswith("ok") and not eco_match(r)],
    }

    # Field coverage over packages (files already excluded by the inspector).
    tot = 0
    got = Counter()
    for r in withsbom:
        s = r["sbom"]
        tot += s["components"]
        for f in FIELDS:
            got[f] += (s.get("counts") or {}).get(f, 0)
    out["packages_analysed"] = tot
    out["coverage_weighted"] = {f: pct(got[f], tot) for f in FIELDS}
    # Per-SBOM medians, so one huge document cannot carry the number.
    out["coverage_median_per_sbom"] = {
        f: round(statistics.median(
            [(r["sbom"].get("coverage") or {}).get(f) or 0 for r in withsbom]), 1)
        for f in FIELDS}

    # Container file noise.
    out["containers"] = [
        {"slug": r["slug"],
         "all": (r.get("sbom") or {}).get("components_all"),
         "files": (r.get("sbom") or {}).get("file_components"),
         "packages": (r.get("sbom") or {}).get("components"),
         "pkg_purl_pct": ((r.get("sbom") or {}).get("coverage") or {}).get("purl")}
        for r in recs if r["kind"] == "container"
        and (r.get("sbom") or {}).get("components")]

    # Enrichment attribution.
    src = Counter()
    enriched = 0
    for r in withsbom:
        for k, v in (r["sbom"].get("enrichment_sources") or {}).items():
            src[k] += v
        enriched += r["sbom"].get("enriched_components") or 0
    out["enrichment"] = {"stamped": enriched, "of_packages": tot,
                         "sources": dict(src.most_common())}

    # Generators actually used.
    tools = Counter()
    for r in withsbom:
        for t in r["sbom"].get("tools") or []:
            tools[t.split("@")[0]] += 1
    out["generators"] = dict(tools.most_common())
    out["spec_versions"] = dict(Counter(
        r["sbom"].get("spec_version") for r in withsbom))

    # Wizard: how much would it pre-select?
    counts = [len(r.get("discovered") or []) for r in repos]
    out["wizard"] = {
        "median_discovered": statistics.median(counts) if counts else 0,
        "mean_discovered": round(statistics.mean(counts), 1) if counts else 0,
        "over_10": sum(1 for c in counts if c > 10),
        "over_50": sum(1 for c in counts if c > 50),
        "at_cap": [r["slug"] for r in repos if len(r.get("discovered") or []) >= 200],
        "no_lockfile": [r["slug"] for r in repos
                        if r.get("error") == "no_lockfile_discovered"],
    }

    # Version hygiene and graph shape.
    out["quality"] = {
        "placeholder_versions": sum(
            r["sbom"].get("version_placeholder_count") or 0 for r in withsbom),
        "root_version_placeholder": sum(
            1 for r in withsbom if r["sbom"].get("root_version_placeholder")),
        "sboms": len(withsbom),
        "zero_dep_edges": sum(
            1 for r in withsbom if not r["sbom"].get("dependency_edges")),
        "empty_sboms": [r["slug"] for r in recs
                        if (r.get("sbom") or {}).get("components") == 0],
    }

    # Runtime.
    ds = sorted(r.get("duration_s", 0) for r in recs if r.get("duration_s"))
    if ds:
        out["duration_s"] = {
            "median": ds[len(ds) // 2], "p90": ds[int(len(ds) * .9)],
            "max": ds[-1], "total_hours": round(sum(ds) / 3600, 1)}

    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
