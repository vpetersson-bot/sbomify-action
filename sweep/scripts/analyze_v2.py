#!/usr/bin/env python3
"""Compare the re-run against the first survey and emit one JSON blob.

Three axes, because the first comparison only had one and a half of them:

  generation    does an SBOM come out, how many components, and -- separately
                -- does it come out *without* SBOMIFY_ALLOW_GENERATOR_FALLBACK.
                Several fixes changed only the second, so counting components
                alone reported "unchanged" for the entire point of them.

  enrichment    field coverage over dependency components, plus which source
                filled what, taken from the sbomify:enrichment:source property.

  augmentation  the document-level metadata augmentation writes. The first
                survey scored five root fields and nothing else, so a
                regression here could not have been seen.

The "before" for generation comes from the stored survey records; for
enrichment and augmentation it comes from re-inspecting the retained output
SBOMs with the current inspector, since the old records predate those fields.
Only projects present on both sides are compared -- 189 of the 251 kept an
output document, and pretending the other 62 were zeroes would invent
improvements that did not happen.
"""

import json
import pathlib
import sys
from collections import Counter, defaultdict

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
V2 = ROOT / "v2"
COVERAGE_FIELDS = ("license", "purl", "version", "description", "supplier", "hashes", "extrefs", "vcs")
AUG_FIELDS = ("metadata.supplier", "metadata.manufacturer", "metadata.authors", "metadata.licenses",
              "metadata.lifecycles", "metadata.tools", "root.licenses", "root.supplier",
              "root.externalReferences", "root.vcs")


def load_records(directory):
    out = {}
    for f in directory.glob("*.json"):
        try:
            r = json.loads(f.read_text())
        except Exception:
            continue
        if slug := r.get("slug"):
            out[slug] = r
    return out


def key_of(slug):
    return slug.replace("/", "_").replace(":", "_").replace(".", "_")


def components(rec):
    return ((rec or {}).get("sbom") or {}).get("components")


def rc_of(rec):
    """The JVM runner emits `rc`; the general one emits `strict_rc`."""
    if rec is None:
        return None
    return rec.get("strict_rc", rec.get("rc"))


def needed_fallback(rec):
    if rec is None:
        return None
    if rec.get("used_fallback") is not None:
        return bool(rec.get("used_fallback"))
    return None


def main():
    before = load_records(ROOT / "meta")
    # For JVM projects the shared-cache survey in meta/ is not a usable
    # baseline -- that is F16, and it is why those were re-run in isolation
    # into meta_jvm/. Prefer the isolated number where one exists; where none
    # does, there is no trustworthy before at all, and inventing a comparison
    # against a contaminated figure is how the first validation nearly
    # reported a regression that did not exist.
    before_jvm = load_records(ROOT / "meta_jvm")
    before.update(before_jvm)
    no_baseline = {s for s, r in before.items()
                   if r.get("ecosystem") in ("java", "scala") and s not in before_jvm}
    after = load_records(V2 / "meta")
    before_sbom = json.loads((V2 / "before_reinspected.json").read_text())

    done = len(after)
    rows, eco = [], defaultdict(lambda: {"n": 0, "improved": 0, "regressed": 0, "same": 0})
    improved = regressed = same = new_sbom = lost_sbom = refused = unknown = 0

    for slug, a in sorted(after.items()):
        b = before.get(slug)
        bn, an = components(b), components(a)
        e = a.get("ecosystem", "?")
        eco[e]["n"] += 1

        if slug in no_baseline:
            rows.append({"slug": slug, "ecosystem": e, "before": None, "after": an,
                         "verdict": "no isolated baseline", "rc": rc_of(a),
                         "fallback": needed_fallback(a)})
            eco[e]["unknown"] = eco[e].get("unknown", 0) + 1
            unknown += 1
            continue

        if bn is None and an is not None:
            verdict, new_sbom = "gained an SBOM", new_sbom + 1
            eco[e]["improved"] += 1
            improved += 1
        elif bn == 0 and an is None:
            # Not a regression. A document with zero components is worthless --
            # it certifies nothing and cannot be enriched -- and #351 replaced
            # exactly that with a refusal naming the missing file and the
            # command that produces it. Counting it as a loss would score the
            # fix as damage. Verified in the logs: these are the Package.swift
            # decline, not a crash.
            verdict, refused = "empty SBOM now refused", refused + 1
            eco[e]["improved"] += 1
            improved += 1
        elif bn is not None and an is None:
            verdict, lost_sbom = "LOST a real SBOM", lost_sbom + 1
            eco[e]["regressed"] += 1
            regressed += 1
        elif bn == an:
            # Same count is not necessarily "no change": a project that used to
            # need the fallback flag and now does not is a fix, at equal count.
            if needed_fallback(b) and needed_fallback(a) is False:
                verdict, improved = "no flag needed now", improved + 1
                eco[e]["improved"] += 1
            else:
                verdict, same = "unchanged", same + 1
                eco[e]["same"] += 1
        elif (an or 0) > (bn or 0):
            verdict, improved = f"+{(an or 0) - (bn or 0)} components", improved + 1
            eco[e]["improved"] += 1
        else:
            verdict, regressed = f"-{(bn or 0) - (an or 0)} components", regressed + 1
            eco[e]["regressed"] += 1

        rows.append({"slug": slug, "ecosystem": e, "before": bn, "after": an,
                     "verdict": verdict, "rc": rc_of(a),
                     "fallback": needed_fallback(a)})

    # Enrichment and augmentation, over the projects comparable on both sides.
    def agg(recs, get_sbom):
        cov, aug, src = defaultdict(list), Counter(), Counter()
        n = 0
        for slug in recs:
            s = get_sbom(slug)
            if not s or not s.get("components"):
                continue
            n += 1
            for f in COVERAGE_FIELDS:
                v = (s.get("coverage") or {}).get(f)
                if v is not None:
                    cov[f].append(v)
            for f, present in (s.get("augmentation") or {}).items():
                if present:
                    aug[f] += 1
            src.update(s.get("enrichment_sources") or {})
        return ({f: round(sum(v) / len(v), 1) if v else None for f, v in cov.items()},
                dict(aug), dict(src), n)

    # Paired: only projects that produced a document in *both* runs.
    #
    # Filtering each side independently moved the denominator from 152 to 160
    # and every field fell by 1.6 to 4.7 points at once -- a uniform drop
    # across unrelated fields is composition, not regression. The eight extra
    # documents are projects that previously produced none, and a first SBOM
    # from an awkward project is enriched worse than the established average,
    # so adding them lowers the mean while nothing gets worse. Comparing the
    # same projects on both sides is the only way to read this honestly.
    def has_components(s):
        return bool((s or {}).get("components"))

    common = [s for s in after
              if key_of(s) in before_sbom
              and has_components(before_sbom.get(key_of(s)))
              and has_components(after[s].get("sbom") or {})]
    b_cov, b_aug, b_src, b_n = agg(common, lambda s: before_sbom.get(key_of(s)))
    a_cov, a_aug, a_src, a_n = agg(common, lambda s: (after[s].get("sbom") or {}))

    # Enrichment per package ecosystem, attributed by each document's dominant
    # purl type. This is where the headline "coverage fell 2 points" resolves:
    # it did not fall because anything got worse, it fell because .NET
    # generation started working and .NET is the one ecosystem our sources do
    # not cover.
    eco_tot, eco_enr = Counter(), Counter()
    for rec in after.values():
        s_ = rec.get("sbom") or {}
        pt = s_.get("purl_types") or {}
        if not s_.get("components") or not pt:
            continue
        dominant = max(pt.items(), key=lambda x: x[1])[0]
        eco_tot[dominant] += sum(pt.values())
        eco_enr[dominant] += sum((s_.get("enrichment_sources") or {}).values())
    by_purl = [{"type": t, "components": n, "enriched": eco_enr[t],
                "ratio": round(eco_enr[t] / n, 2) if n else 0}
               for t, n in eco_tot.most_common(12)]

    print(json.dumps({
        "done": done, "total": 251,
        "generation": {"improved": improved, "regressed": regressed, "same": same,
                       "gained": new_sbom, "lost": lost_sbom, "refused": refused,
                       "no_baseline": unknown},
        "rows": rows,
        "ecosystems": {k: v for k, v in sorted(eco.items())},
        "comparable": len(common),
        "enrichment": {"before": b_cov, "after": a_cov,
                       "before_sources": b_src, "after_sources": a_src,
                       "before_n": b_n, "after_n": a_n},
        "by_purl": by_purl,
        "augmentation": {"before": b_aug, "after": a_aug,
                         "fields": list(AUG_FIELDS),
                         "before_n": b_n, "after_n": a_n},
    }, indent=1))


if __name__ == "__main__":
    sys.exit(main())
