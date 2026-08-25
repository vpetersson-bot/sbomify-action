#!/usr/bin/env python3
"""One verdict and one reason for every project in the corpus.

The aggregate numbers cannot answer the question that matters -- did we do a
good job on *this* project, and if not, why. So each of the 500 gets a verdict
and a reason code derived from evidence, plus an explicit `unexplained`
bucket. That bucket is the point of the script: anything landing there is a
project whose outcome nobody has accounted for yet, and it should be worked
down to zero rather than averaged away.

Reasons are assigned from the record and, where the record is not enough, from
the run log. Nothing is inferred from the ecosystem alone -- "it is Perl, so of
course it failed" is the kind of reasoning that hides a real defect behind a
plausible story.
"""

import argparse
import json
import os
import pathlib
import re
from collections import Counter, defaultdict

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
CORPUS = ROOT / "projects_v5.tsv"
META = pathlib.Path(os.environ.get("SBOMIFY_EVAL_META") or (ROOT / "v5/meta"))
LOGS = ROOT / "v5/logs"

#: Languages the action has no lockfile entry for. Being here is a coverage
#: decision, not a bug -- but it is still an answer that has to be given
#: rather than assumed, so it is checked against the discovery result.
UNSUPPORTED = {"perl", "julia", "r", "zig", "lua", "ocaml", "nim", "nix", "other"}

#: Supported, but only via a lockfile. A library that gitignores its lockfile
#: presents nothing the action will read.
LOCK_ONLY = {"ruby", "elixir", "erlang", "cpp", "dart", "terraform"}


def log_text(key: str) -> str:
    p = LOGS / f"{key}.log"
    if not p.exists():
        return ""
    try:
        return p.read_text(errors="replace")[-200_000:]
    except Exception:
        return ""


def classify(rec: dict, key: str) -> tuple[str, str, str]:
    """(verdict, reason, detail) for one project."""
    eco = rec.get("ecosystem", "?")
    runs = rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else [])
    # key= rather than comparing tuples: two runs with the same component
    # count would otherwise fall through to comparing dicts, which raises.
    run = max(runs, key=lambda r: (r.get("sbom") or {}).get("components") or 0) if runs else None
    n = ((run or {}).get("sbom") or {}).get("components") or 0

    # --- produced something
    if n:
        sbom = run.get("sbom") or {}
        if sbom.get("root_version_placeholder") or "workspace" in (sbom.get("root_purl") or ""):
            return "good", "components, weak self-description", f"{n} components"
        return "good", "components", f"{n} components"

    # --- discovery found nothing
    if rec.get("error") == "no_lockfile_discovered":
        found = rec.get("discovered") or []
        if eco in UNSUPPORTED:
            return "expected gap", "language not supported", "no lockfile format for this language"
        if eco in LOCK_ONLY:
            return "fixable gap", "lockfile-only ecosystem", "project ships a manifest, action reads only lockfiles"
        if found:
            return "unexplained", "input found but not selected", f"{len(found)} candidate(s) discovered"
        return "unexplained", "nothing discovered in a supported language", ""

    text = log_text(key)

    # --- produced nothing, and the log says why
    if run is not None:
        target = run.get("target_lockfile") or ""
        if run.get("strict_rc") == 124:
            return "harness limit", "timed out", "killed at the harness timeout, not a tool failure"
        if "output file not created" in text:
            return "defect", "generator exited 0 without writing", target
        if "Error while parsing" in text or "TomlError" in text:
            return "defect", "generator crashed parsing the input", target
        if "could not be resolved to an installable set" in text:
            return "environmental", "dependency resolution failed", "resolver could not satisfy the graph"
        if re.search(r"No components with PURLs found", text):
            return "defect", "document written with no components", target
        if target.endswith(".sln") or target.endswith(".csproj"):
            return "expected gap", "project file declares no packages", target
        return "unexplained", "produced nothing, reason not identified", target

    return "unexplained", "no runs recorded", ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", help="print every project with this verdict")
    ap.add_argument("--reason", help="print every project with this reason")
    args = ap.parse_args()

    records = {}
    for f in sorted(META.glob("*.json")):
        if f.stat().st_size:
            rec = json.loads(f.read_text())
            records[rec["slug"]] = (rec, f.stem)

    rows = []
    for line in CORPUS.read_text().splitlines():
        if not line.strip():
            continue
        eco, slug = line.split("\t")[0], line.split("\t")[1]
        entry = records.get(slug)
        if not entry:
            rows.append((slug, eco, "unexplained", "no record", ""))
            continue
        rec, key = entry
        verdict, reason, detail = classify(rec, key)
        rows.append((slug, eco, verdict, reason, detail))

    verdicts = Counter(r[2] for r in rows)
    print(f"{len(rows)} projects\n")
    order = ["good", "expected gap", "fixable gap", "environmental", "defect", "harness limit", "unexplained"]
    for v in order:
        if verdicts[v]:
            print(f"   {verdicts[v]:4d}  {v}")

    print("\nby reason:")
    by_reason = Counter((r[2], r[3]) for r in rows)
    for (v, reason), n in sorted(by_reason.items(), key=lambda x: (order.index(x[0][0]), -x[1])):
        print(f"   {n:4d}  [{v}] {reason}")

    if args.show or args.reason:
        print()
        for slug, eco, verdict, reason, detail in sorted(rows):
            if args.show and verdict != args.show:
                continue
            if args.reason and reason != args.reason:
                continue
            print(f"   {eco:11s} {slug:36s} {reason:42s} {detail[:40]}")

    unexplained = [r for r in rows if r[2] == "unexplained"]
    if unexplained:
        print(f"\n{len(unexplained)} project(s) with no account of the outcome -- work these down:")
        by_eco = defaultdict(int)
        for r in unexplained:
            by_eco[r[1]] += 1
        for eco, n in sorted(by_eco.items(), key=lambda x: -x[1]):
            print(f"   {eco:11s} {n}")


if __name__ == "__main__":
    main()
