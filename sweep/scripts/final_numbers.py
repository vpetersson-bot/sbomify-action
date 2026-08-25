#!/usr/bin/env python3
"""Final corpus numbers, with the JVM rows taken from the isolated pass.

The main pass ran up to ten containers against one runtime cache, which F16
shows cannot measure a JVM project: Gradle's journal lock is inside that cache
and the second container dies before reaching the build. So for java and scala
the per-stack table uses `meta_jvm/` — one isolated cache per concurrent slot —
and the main-pass rows for those two stacks are discarded rather than reported.

Everything else comes from the main pass, which the contention does not affect.
"""

import json
import pathlib
import statistics
import sys
from collections import Counter, defaultdict

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
sys.path.insert(0, str(ROOT))
from aggregate import classify, eco_match, load  # noqa: E402

JVM_STACKS = {"java", "scala"}


def jvm_records():
    """Isolated JVM results, shaped like main-pass records so classify() works."""
    out = []
    for f in sorted((ROOT / "meta_jvm").glob("*.json")):
        try:
            r = json.loads(f.read_text())
        except Exception:
            continue
        out.append({
            "ecosystem": r["ecosystem"], "slug": r["slug"], "kind": "repo",
            # The isolated pass always ran with the fallback enabled, so a
            # non-zero rc means every generator failed, not that strict mode
            # refused a degraded result.
            "strict_rc": r["rc"], "fallback_rc": None, "used_fallback": False,
            "duration_s": r.get("duration_s"), "discovered": [],
            "target_lockfile": r.get("lockfile"), "sbom": r.get("sbom") or {},
        })
    return out


def main():
    main_recs = [r for r in load() if r.get("kind")]
    kept = [r for r in main_recs if r["ecosystem"] not in JVM_STACKS]
    jvm = jvm_records()
    recs = kept + jvm

    print(f"corpus: {len(recs)} records "
          f"({len(kept)} main pass + {len(jvm)} isolated JVM; "
          f"{len(main_recs) - len(kept)} contaminated JVM rows discarded)\n")

    out = Counter(classify(r) for r in recs)
    usable = out["ok_strict"] + out["ok_only_with_fallback"]
    print("## Outcome")
    for k, v in out.most_common():
        print(f"  {k:24s} {v:4d}  {100*v/len(recs):5.1f}%")
    print(f"  {'--> usable SBOM':24s} {usable:4d}  {100*usable/len(recs):5.1f}%")

    print("\n## By stack (usable = ok_strict + fallback-only, non-empty)")
    by = defaultdict(Counter)
    for r in recs:
        by[r["ecosystem"]][classify(r)] += 1
    hdr = ["ok_strict", "ok_only_with_fallback", "failed", "no_lockfile",
           "empty_sbom", "clone_failed"]
    rows = []
    for eco, c in by.items():
        tot = sum(c.values())
        ok = c["ok_strict"] + c["ok_only_with_fallback"]
        rows.append((ok / tot, eco, tot, c, ok))
    print(f"  {'stack':12s} {'n':>3s} {'ok':>3s} {'fb':>3s} {'fail':>4s} "
          f"{'nolock':>6s} {'empty':>5s}  usable")
    for _, eco, tot, c, ok in sorted(rows):
        print(f"  {eco:12s} {tot:3d} {c['ok_strict']:3d} "
              f"{c['ok_only_with_fallback']:3d} {c['failed']:4d} "
              f"{c['no_lockfile']:6d} {c['empty_sbom']:5d}  {100*ok/tot:5.1f}%")

    withsbom = [r for r in recs if (r.get("sbom") or {}).get("components")]
    fields = ["license", "purl", "version", "description", "supplier",
              "author", "hashes", "extrefs", "vcs", "cpe"]
    tot = sum(r["sbom"]["components"] for r in withsbom)
    got = Counter()
    for r in withsbom:
        for f in fields:
            got[f] += (r["sbom"].get("counts") or {}).get(f, 0)
    print(f"\n## Coverage over {tot} packages ({len(withsbom)} SBOMs)")
    for f in fields:
        print(f"  {f:12s} {100*got[f]/tot:5.1f}%")

    print("\n## Empty SBOMs (exit 0, zero components)")
    empties = [r["slug"] for r in recs if (r.get("sbom") or {}).get("components") == 0]
    print(f"  {len(empties)}: {', '.join(sorted(empties)[:14])}"
          f"{' …' if len(empties) > 14 else ''}")

    print("\n## Wrong-stack SBOMs")
    mm = [r for r in recs if classify(r).startswith("ok") and r.get("discovered")
          and not eco_match(r)]
    print(f"  {len(mm)} projects produced an SBOM of another ecosystem")

    ds = sorted(r["duration_s"] for r in recs if r.get("duration_s"))
    print(f"\n## Runtime  median {ds[len(ds)//2]}s  p90 {ds[int(len(ds)*.9)]}s  "
          f"max {ds[-1]}s  total {sum(ds)/3600:.1f}h")


if __name__ == "__main__":
    main()
