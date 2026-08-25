#!/usr/bin/env python3
"""Generate the 500-row results table for the write-up.

Reads the corpus (every project and the release it was pinned to) and joins it
against whatever v5 has produced so far, so the table can be regenerated as the
sweep finishes rather than transcribed by hand.

Projects with no record yet are rendered as "pending" rather than omitted. A
table that silently drops the rows it has no answer for would overstate how
much of the corpus has been measured, which is the mistake this whole re-run
exists to stop repeating.
"""

import argparse
import json
import os
import pathlib
from collections import Counter

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
CORPUS = ROOT / "projects_v5.tsv"

#: Which set of records to read. Defaults to the live one, but the post's
#: table must come from a single build, and the live set is deliberately mixed
#: now that the previously-failing projects have been re-measured on a newer
#: image. SBOMIFY_EVAL_META points it at the snapshot instead.
META = pathlib.Path(os.environ.get("SBOMIFY_EVAL_META") or (ROOT / "v5/meta"))


#: Ecosystems that share a build system, so a project labelled with one can
#: legitimately be built by an input labelled with another.
#:
#: apache/spark is the case that named this. The corpus calls it scala, its
#: root inputs are pom.xml (java) and pyproject.toml (python), and an exact
#: match on "scala" finds neither -- so the choice fell through to
#: _priority_of, which prefers Python to everything and led the row with a
#: pyproject.toml that yields 0 components while pom.xml yields 343.
_FAMILY = {
    "java": "jvm",
    "kotlin": "jvm",
    "scala": "jvm",
    "clojure": "jvm",
    "android": "jvm",
}


def headline(rec: dict) -> dict:
    """The run that best represents the project, computed here rather than
    baked into the record, so the rule can be corrected without re-running
    five hundred projects. ``runs`` holds every result either way."""
    runs = rec.get("runs")
    if not runs:
        return rec  # single-target record from before the harness was fixed
    eco = rec.get("ecosystem")
    exact = [r for r in runs if r.get("target_ecosystem") == eco]
    if exact:
        return exact[0]
    family = [r for r in runs if _FAMILY.get(r.get("target_ecosystem") or "") == _FAMILY.get(eco or "")]
    if family and _FAMILY.get(eco or ""):
        return family[0]
    # Nothing matched the project's own language -- "polyglot", or an
    # ecosystem with no support at all. Any pick here is arbitrary, so say so
    # in the detail rather than choosing quietly.
    return runs[0]


def outcome(rec: dict | None) -> tuple[str, str]:
    """A short verdict and the detail behind it."""
    if rec is None:
        return "pending", ""

    err = rec.get("error")
    if err == "clone_failed":
        return "clone failed", ""
    if err == "no_lockfile_discovered":
        n = len(rec.get("discovered") or [])
        return "no recognised input", f"{n} candidate(s) found" if n else "nothing found"

    head = headline(rec)
    sbom = head.get("sbom") or {}
    components = sbom.get("components")
    target = head.get("target_lockfile") or ""

    # A polyglot root produces a component per input, which is what the wizard
    # ticks and what the user gets. Reporting only one of them would repeat the
    # harness bug this table exists to describe.
    others = [r for r in (rec.get("runs") or []) if r is not head]
    extra = ""
    if others:
        parts = [
            f"`{r.get('target_lockfile')}` {(r.get('sbom') or {}).get('components')}"
            for r in others
        ]
        extra = "; also " + ", ".join(parts)

    if components:
        detail = f"{components} components from `{target}`" if target else f"{components} components"
        if head.get("used_fallback") and head.get("fallback_rc") == 0:
            detail += ", strict mode declined it"
        return "SBOM", detail + extra
    if components == 0:
        return "empty SBOM", (f"from `{target}`" if target else "") + extra
    return "no SBOM", (f"generators failed on `{target}`" if target else "generators failed") + extra


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, help="write the table here instead of stdout")
    args = ap.parse_args()

    records: dict[str, dict] = {}
    for f in META.glob("*.json"):
        try:
            rec = json.loads(f.read_text())
        except Exception:
            continue  # zero-byte or truncated; counted as pending below
        records[rec["slug"]] = rec

    rows = []
    verdicts: Counter[str] = Counter()
    for line in CORPUS.read_text().splitlines():
        if not line.strip():
            continue
        eco, slug, _url, _note, ref = line.split("\t")
        verdict, detail = outcome(records.get(slug))
        verdicts[verdict] += 1
        version = "default branch" if ref == "@default" else ref
        rows.append((slug, eco, version, verdict, detail))

    out = []
    out.append(f"<!-- generated by make_blog_table.py from {len(records)} of {len(rows)} records -->")
    out.append("")
    out.append("| Project | Ecosystem | Version tested | Result | Detail |")
    out.append("| --- | --- | --- | --- | --- |")
    for slug, eco, version, verdict, detail in sorted(rows, key=lambda r: r[0].lower()):
        out.append(
            f"| [{slug}](https://github.com/{slug}) | {eco} | `{version}` | {verdict} | {detail} |"
        )
    table = "\n".join(out) + "\n"

    if args.out:
        args.out.write_text(table)
        print(f"wrote {len(rows)} rows to {args.out}")
    else:
        print(table)

    print("\nverdicts:")
    total = sum(verdicts.values())
    for v, n in verdicts.most_common():
        print(f"  {n:4d}  {100 * n / total:5.1f}%  {v}")

    # Provenance, checked rather than remembered.
    #
    # The write-up says every row was measured on one build of the action, and
    # that sentence is only true if the records agree. They have disagreed
    # before: an earlier sweep mixed results from before and after a merge, and
    # nothing in the data said so -- it was caught by recalling which image was
    # pinned when, which is not evidence. Each record now carries the digest it
    # ran under, so the claim can be tested here and fails loudly if it breaks.
    images = Counter(r.get("image", "(unstamped)") for r in records.values())
    print("\nimages:")
    for image, n in images.most_common():
        print(f"  {n:4d}  {image}")
    if len(images) > 1:
        print("\n  WARNING: rows come from more than one build; the corpus is not comparable")


if __name__ == "__main__":
    main()
