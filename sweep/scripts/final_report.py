#!/usr/bin/env python3
"""Every number the write-up needs, computed from the records in one pass.

The write-up has twice stated a figure that was true of an earlier run: the
ref split was the old resolver's, and the count of harness bugs was the count
at the time of writing. Both were caught by re-deriving them. So the numbers
go in the post by being generated here, not by being remembered.

Imports the declared-input check from empty_inputs rather than restating it.
Two copies of a fact is the mistake this evaluation has now made four times.
"""

import json
import pathlib
from collections import Counter, defaultdict

import empty_inputs

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
META = ROOT / "v5/meta"
CORPUS = ROOT / "projects_v5.tsv"

#: Ecosystems the action has no lock file entry for at all. Finding nothing in
#: these is correct behaviour; they are a roadmap question, not a defect, and
#: mixing them into a "no input" headline makes the tool look broken where it
#: is merely absent.
UNSUPPORTED = {"perl", "julia", "r", "zig", "lua", "ocaml", "nim", "nix", "other"}

#: Supported, but only through a lock file -- no manifest fallback. A library
#: that gitignores its lock file therefore presents nothing readable.
LOCK_ONLY = {"ruby", "elixir", "erlang", "cpp", "dart", "terraform"}


def load() -> tuple[list[dict], list[tuple[str, str]]]:
    records = []
    for f in sorted(META.glob("*.json")):
        if not f.stat().st_size:
            continue
        try:
            records.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            print(f"  !! unreadable record: {f.name}")
    corpus = [
        (line.split("\t")[0], line.split("\t")[1])
        for line in CORPUS.read_text().splitlines()
        if line.strip()
    ]
    return records, corpus


def runs_of(rec: dict) -> list[dict]:
    return rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else [])


def section(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def main() -> None:
    records, corpus = load()
    by_slug = {r["slug"]: r for r in records}

    section(f"COVERAGE  ({len(records)} of {len(corpus)} projects)")
    refs = [line.split("\t")[4] for line in CORPUS.read_text().splitlines() if line.strip()]
    print(f"  pinned to a release or tag : {sum(1 for r in refs if r != '@default')}")
    print(f"  never tagged, default branch: {sum(1 for r in refs if r == '@default')}")

    images = Counter(r.get("image", "(unstamped)") for r in records)
    print(f"  distinct images            : {len(images)}")
    if len(images) > 1:
        print("  !! NOT COMPARABLE: records span more than one build")
        for img, n in images.most_common():
            print(f"       {n:4d}  {img}")

    section("OUTCOMES, per run")
    all_runs = [(r, run) for r in records for run in runs_of(r)]
    print(f"  runs with an exit code: {len(all_runs)}")
    produced = [(r, x) for r, x in all_runs if (x.get("sbom") or {}).get("components")]
    empty = [(r, x) for r, x in all_runs if (x.get("sbom") or {}).get("components") == 0]
    nothing = [(r, x) for r, x in all_runs if (x.get("sbom") or {}).get("components") is None]
    print(f"    produced components   : {len(produced)}")
    print(f"    empty document        : {len(empty)}")
    print(f"    no document at all    : {len(nothing)}")
    timeouts = [(r, x) for r, x in all_runs if x.get("strict_rc") == 124]
    print(f"    killed by the harness timeout (excluded from strict analysis): {len(timeouts)}")

    section("NO RECOGNISED INPUT, split by cause")
    noinput = [r for r in records if r.get("error") == "no_lockfile_discovered"]
    unsup = [r for r in noinput if r["ecosystem"] in UNSUPPORTED]
    lockonly = [r for r in noinput if r["ecosystem"] in LOCK_ONLY]
    other = [r for r in noinput if r["ecosystem"] not in UNSUPPORTED | LOCK_ONLY]
    print(f"  total                          : {len(noinput)} of {len(records)}")
    print(f"    ecosystem unsupported entirely: {len(unsup)}")
    print(f"    supported, lock file only     : {len(lockonly)}  <- F25, the actionable half")
    print(f"    neither of the above          : {len(other)}")
    for r in other:
        print(f"       {r['ecosystem']:11s} {r['slug']}")

    have_fallback = defaultdict(int)
    for r in records:
        if r["ecosystem"] not in UNSUPPORTED | LOCK_ONLY:
            have_fallback[r.get("error") == "no_lockfile_discovered"] += 1
    print(f"  ecosystems WITH a manifest fallback: {have_fallback[False]} found an input, "
          f"{have_fallback[True]} did not")

    section("SILENT EMPTY DOCUMENTS  (exit 0, zero components)")
    print("  classified against what the input declared; see empty_inputs.py")
    rows = empty_inputs.collect()
    real = [x for x in rows if isinstance(x[2], int) and x[2] > 0]
    honest = [x for x in rows if x[2] == 0 or x[2] is None]
    print(f"  empty documents      : {len(rows)}")
    print(f"    genuinely lost deps: {len(real)}   <- the defect")
    print(f"    legitimately empty : {len(honest)}")
    for slug, path, n, _note in sorted(real, key=lambda x: -(x[2] or 0)):
        print(f"       {slug:30s} {str(path)[:26]:26s} {n} declared -> 0")

    section("ROOT COMPONENT IDENTITY")
    purls = Counter()
    for _r, run in all_runs:
        p = (run.get("sbom") or {}).get("root_purl")
        if p:
            purls[p] += 1
    ws = {p: n for p, n in purls.items() if "workspace" in p}
    print(f"  documents with a root purl      : {sum(purls.values())}")
    print(f"  naming the mount dir 'workspace': {sum(ws.values())}")
    collisions = {p: n for p, n in purls.items() if n > 1}
    print(f"  purls shared by more than one run: {len(collisions)}")
    for p, n in sorted(collisions.items(), key=lambda x: -x[1])[:8]:
        who = sorted({r["slug"] for r, run in all_runs if (run.get("sbom") or {}).get("root_purl") == p})
        print(f"       {n}x  {p:44s} {', '.join(who[:4])}")

    section("POLYGLOT PROJECTS  (more than one input at the shallowest depth)")
    multi = [r for r in records if len(runs_of(r)) > 1]
    print(f"  {len(multi)} projects produced more than one document")
    for r in sorted(multi, key=lambda x: x["slug"]):
        parts = [
            f"{x.get('target_lockfile')}={(x.get('sbom') or {}).get('components')}"
            for x in runs_of(r)
        ]
        print(f"       {r['ecosystem']:11s} {r['slug']:30s} {'  '.join(parts)}")

    section("COMPONENT COUNTS")
    counts = sorted(
        ((x.get("sbom") or {}).get("components") or 0, r["slug"], x.get("target_lockfile"))
        for r, x in produced
    )
    if counts:
        mid = counts[len(counts) // 2]
        print(f"  median: {mid[0]} ({mid[1]})")
        print("  largest:")
        for n, slug, tgt in counts[-5:][::-1]:
            print(f"       {n:6d}  {slug:30s} {tgt}")


if __name__ == "__main__":
    main()
