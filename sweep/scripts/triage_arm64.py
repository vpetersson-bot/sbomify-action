#!/usr/bin/env python3
"""Triage the arm64 sweep for defects, not for scores.

Three questions, in descending order of how much they mean:

  1. Did the product crash?  An unhandled exception is unambiguously a bug.
  2. Did it break *only* on arm64?  A project that produced components on
     amd64 and produces none here is an architecture defect -- the one class
     of finding this sweep exists to surface, and the only place the amd64
     baseline is legitimately used, since "worked there, not here" is a
     defect claim rather than a benchmark.
  3. Did it fail without saying why?  rc!=0 with no recommended action is a
     usability defect even when refusing is correct.

Deliberately does NOT rank by component count. Counts differ across
architectures for reasons that are not defects, and chasing them is how a bug
hunt turns into a benchmark.
"""

import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
ARM = ROOT / "arm64/meta"
BASE = ROOT / "v5-meta"


def components(rec):
    for key in ("strict_sbom", "fallback_sbom"):
        s = rec.get(key) or {}
        if s.get("components"):
            return s["components"]
    return 0


#: Lock files whose ecosystem is a project's *tooling* rather than the project
#: -- fastlane for Swift, Rake for C. v5 scanned these by mistake and recorded
#: real-looking component counts for them.
_TOOLING_FOR = {
    "swift": {"Gemfile.lock", "Gemfile"},
    "cpp": {"Gemfile.lock", "Gemfile"},
    "c": {"Gemfile.lock", "Gemfile"},
    "objective-c": {"Gemfile.lock", "Gemfile"},
}


def baseline_is_trustworthy(rec, run):
    """Whether a v5 record can be used as evidence of what *should* happen.

    It often cannot. The v5 harness kept a truncated copy of the wizard's
    priority table, so for ecosystems past Rust every candidate scored the
    default and the tie broke alphabetically. Alamofire -- a Swift package --
    was scanned via its fastlane `Gemfile.lock` and recorded 55 components at
    `pkg:generic/alamofire@latest`. Comparing a correct arm64 refusal against
    that number produces a regression that never existed.

    A baseline is only evidence if it described the right subject. Two
    signatures give the bad ones away: a `pkg:generic/...@latest` root, which
    means nothing resolved the identity, and a target whose ecosystem is the
    project's tooling rather than the project.
    """
    sbom = run.get("sbom") or {}
    purl = sbom.get("root_purl") or ""
    if purl.startswith("pkg:generic/") and purl.endswith("@latest"):
        return False
    target = (run.get("target_lockfile") or "").split("/")[-1]
    if target in _TOOLING_FOR.get(rec.get("ecosystem") or "", set()):
        return False
    return True


def baseline_components(slug, target):
    """What v5 got **from the same input**, or None if it never tried it.

    Matching the target is the whole point, and omitting it invalidated the
    entire regression list once already. v5 often ran several inputs per
    project; taking the best of any of them and comparing it against the one
    input replayed here compares different questions. hasura/graphql-engine
    was the giveaway -- 424 components in v5 from `cabal.project.freeze` (a
    Haskell filesystem scan) against 0 here from `yarn.lock`. Twelve of the
    thirteen "regressions" were that mistake; the thirteenth was a real
    failure already explained elsewhere.

    Returns None rather than 0 when v5 never scanned this input, so "we have
    no comparison" stays distinguishable from "it produced nothing".
    """
    f = BASE / (slug.replace("/", "_") + ".json")
    if not f.exists() or not f.stat().st_size:
        return None
    rec = json.loads(f.read_text())
    runs = rec.get("runs") or ([rec] if rec.get("strict_rc") is not None else [])
    matched = [r for r in runs if (r.get("target_lockfile") or "") == (target or "")]
    if not matched:
        return None
    best = None
    for run in matched:
        if not baseline_is_trustworthy(rec, run):
            continue
        s = run.get("sbom") or {}
        best = max(best or 0, s.get("components") or 0)
    return best


crashes, arch_only, silent_fail, killed, needs_rerun = [], [], [], [], []
LOGS = ROOT / 'arm64/logs'
total = 0
for f in sorted(ARM.glob("*.json")):
    if not f.stat().st_size:
        continue
    try:
        rec = json.loads(f.read_text())
    except json.JSONDecodeError:
        continue
    if rec.get("error"):
        continue
    total += 1
    slug = rec["slug"]
    got = components(rec)
    rc = rec.get("strict_rc")

    if rec.get("traceback"):
        crashes.append((slug, rec.get("crash_line") or "<no exception line>"))
    if rec.get("killed"):
        killed.append((slug, rec.get("target_lockfile")))

    # Memory starvation is not an architecture defect. At 2g every Gradle
    # project died with "Gradle build daemon disappeared unexpectedly" and
    # produced nothing, which is indistinguishable in the results from arm64
    # breaking. arrow-kt settled it: 0 components at 2g, 1280 at 8g. These
    # need re-running uncapped, not reporting.
    # The Gradle daemon message is the starvation signature and predates the
    # `killed` flag, so read the log rather than trusting the record alone.
    log = LOGS / (slug.replace("/", "_") + ".log")
    daemon_died = False
    if log.exists():
        try:
            daemon_died = "daemon disappeared unexpectedly" in log.read_text(errors="ignore")
        except OSError:
            pass
    starved = rec.get("killed") or daemon_died
    was = baseline_components(slug, rec.get("target_lockfile"))
    if was and was > 0 and got == 0 and not starved:
        arch_only.append((slug, rec.get("target_lockfile"), was))
    elif starved and got == 0:
        needs_rerun.append((slug, rec.get("target_lockfile")))

    if rc not in (0, None) and got == 0 and not rec.get("recommended_action"):
        silent_fail.append((slug, rec.get("target_lockfile"), rc))

print(f"triaged {total} arm64 records\n")

print(f"=== UNHANDLED EXCEPTIONS ({len(crashes)}) -- unambiguous bugs")
for slug, line in crashes[:40]:
    print(f"   {slug:38s} {line[:110]}")
if crashes:
    print("\n   by exception type:")
    for exc, n in Counter(c[1].split(":")[0] for c in crashes).most_common(10):
        print(f"      {exc[:60]:60s} {n}")

print(f"\n=== PRODUCED COMPONENTS BEFORE, EMPTY NOW, SAME INPUT ({len(arch_only)})")
for slug, target, was in sorted(arch_only, key=lambda x: -x[2])[:40]:
    print(f"   {slug:38s} {str(target)[:34]:34s} was {was}")

print(f"\n=== KILLED BY THE RUNTIME ({len(killed)}) -- OOM / segfault / disk")
for slug, target in killed[:20]:
    print(f"   {slug:38s} {str(target)[:40]}")

print(f"\n=== MEMORY-STARVED, RE-RUN UNCAPPED ({len(needs_rerun)}) -- harness, not product")
for slug, target in needs_rerun[:30]:
    print(f"   {slug:38s} {str(target)[:40]}")

print(f"\n=== FAILED WITHOUT ADVICE ({len(silent_fail)}) -- usability defects")
for slug, target, rc in silent_fail[:25]:
    print(f"   {slug:38s} {str(target)[:34]:34s} rc={rc}")
