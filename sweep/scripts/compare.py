#!/usr/bin/env python3
"""Before/after for the projects the merged fixes were supposed to change.

Two things this has to get right, both of which the first version got wrong.

**Component count is not the only axis.** The pyproject fix does not change
how many components come out -- it changes whether they come out at all
*under default settings*. Those projects previously needed an undocumented
environment variable, and with it the count was identical. Comparing counts
alone reported "unchanged" for the fix's entire point.

**Which baseline.** For Java the main survey ran ten containers against one
runtime cache, which cannot measure a JVM project (F16). The honest before
for those is the isolated re-run in meta_jvm/, not the contaminated number
in meta/ -- which differ: jenkins reads 13 in one and 0 in the other.

Controls are included so that a fix improving its target while breaking
something that already worked cannot pass unnoticed.
"""

import json
import pathlib

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
JVM = {"netty/netty", "jenkinsci/jenkins"}

CASES = [
    ("crystal-lang/crystal", "F15 symlink hang", "timing"),
    ("psf/requests", "F1 pyproject manifest", "default"),
    ("django/django", "F1 pyproject manifest", "default"),
    ("pandas-dev/pandas", "F1 pyproject manifest", "default"),
    ("netty/netty", "F22 maven -N", "count"),
    ("jenkinsci/jenkins", "F22 maven -N", "count"),
    ("symfony/symfony", "F18 php toolchain (open)", "count"),
    ("apple/swift-nio", "F20 Package.swift (#351)", "count"),
    ("python-poetry/poetry", "control: poetry", "count"),
    ("composer/composer", "control: composer.lock", "count"),
    ("gin-gonic/gin", "control: go", "count"),
    ("BurntSushi/ripgrep", "control: rust", "count"),
    ("axios/axios", "control: js", "count"),
]


def load(directory: str) -> dict:
    out = {}
    for f in (ROOT / directory).glob("*.json"):
        try:
            record = json.loads(f.read_text())
        except Exception:
            continue
        if slug := record.get("slug"):
            out[slug] = record
    return out


def count(record):
    return ((record or {}).get("sbom") or {}).get("components")


def needed_fallback(slug: str) -> bool:
    """Whether the re-run had to retry with the flag to get anything."""
    key = slug.replace("/", "_").replace(".", "_")
    log = ROOT / "validate" / "logs" / f"{key}.log"
    return log.exists() and "retry with fallback" in log.read_text(errors="replace")


def main() -> None:
    survey, jvm, after = load("meta"), load("meta_jvm"), load("validate/meta")

    def before_of(slug):
        return jvm.get(slug) if slug in JVM and slug in jvm else survey.get(slug)

    print(f"{'project':26s} {'tests':26s} {'before':>17s} {'after':>17s}  verdict")
    print("-" * 114)
    improved = regressed = 0

    for slug, what, axis in CASES:
        b, a = before_of(slug), after.get(slug)
        if a is None:
            print(f"{slug:26s} {what:26s} {'':>17s} {'(missing)':>17s}")
            continue

        if axis == "default":
            was_default = b is not None and b.get("strict_rc") == 0
            is_default = a.get("rc") == 0 and not needed_fallback(slug)
            b_txt = f"{count(b)} default" if was_default else f"{count(b)} w/ flag"
            a_txt = f"{count(a)} default" if is_default else f"{count(a)} w/ flag"
            if is_default and not was_default:
                verdict, improved = "FIXED - no flag needed", improved + 1
            elif was_default and not is_default:
                verdict, regressed = "REGRESSION - needs flag", regressed + 1
            else:
                verdict = "unchanged"
        elif axis == "timing":
            secs = a.get("discover_s")
            b_txt, a_txt = "59 min, killed", f"{secs}s rc={a.get('discover_rc')}"
            if secs is not None and secs < 60:
                verdict, improved = "FIXED - terminates", improved + 1
            else:
                verdict = "still slow"
        else:
            bn, an = count(b), count(a)
            b_txt = "no SBOM" if bn is None else str(bn)
            a_txt = "no SBOM" if an is None else str(an)
            if bn == an:
                verdict = "unchanged" if "control" in what else "still open, as expected"
            elif bn is None or (an or 0) > (bn or 0):
                verdict, improved = f"improved {bn} -> {an}", improved + 1
            else:
                verdict, regressed = f"REGRESSION {bn} -> {an}", regressed + 1

        print(f"{slug:26s} {what:26s} {b_txt:>17s} {a_txt:>17s}  {verdict}")

    controls = [c for c in CASES if "control" in c[1]]
    held = sum(1 for slug, _w, _a in controls if count(before_of(slug)) == count(after.get(slug)))
    print("-" * 114)
    print(f"improved: {improved}    regressions: {regressed}    controls held: {held}/{len(controls)}")


if __name__ == "__main__":
    main()
