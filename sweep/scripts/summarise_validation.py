#!/usr/bin/env python3
"""Read the validation runs back off disk and say what actually happened.

Computed from the stored logs rather than inline, because the inline version
got it wrong: `grep -c pattern file || echo 0` prints grep's own zero *and*
the fallback zero, so the variable held "0\\n0", which is not "0", so every
row was marked as disclosing the notice -- including the ones whose logs do
not contain it. A harness that reports the result it was built to check is
worse than no harness.

Each project is judged against what its manifest declares, so "still empty" is
separated from "still empty and that is correct".
"""

import json
import pathlib
import re
import urllib.request

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
OUT = ROOT / "validate377"
CACHE = ROOT / ".manifest-cache"


def components(path: pathlib.Path) -> int | None:
    if not path.is_file():
        return None
    try:
        return len(json.loads(path.read_text()).get("components") or [])
    except Exception:
        return None


def runtime_deps(slug: str, ref: str, lock: str) -> int | None:
    """What the project says it depends on, so 'empty' can be judged."""
    base = lock.rsplit("/", 1)[-1]
    manifest = {
        "package.json": "package.json",
        "composer.json": "composer.json",
        "pyproject.toml": "pyproject.toml",
        "Cargo.toml": "Cargo.toml",
    }.get(base)
    if not manifest:
        return None
    path = lock[: -len(base)] + manifest
    CACHE.mkdir(exist_ok=True)
    key = CACHE / (slug.replace("/", "_") + "__" + path.replace("/", "_"))
    if key.exists():
        text = key.read_text()
    else:
        url = f"https://raw.githubusercontent.com/{slug}/{ref or 'HEAD'}/{path}"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                text = r.read(4 * 1024 * 1024).decode("utf-8", "replace")
        except Exception:
            return None
        key.write_text(text)
    try:
        if manifest == "package.json":
            return len(json.loads(text).get("dependencies") or {})
        if manifest == "composer.json":
            req = json.loads(text).get("require") or {}
            return len([k for k in req if k != "php" and not k.startswith(("ext-", "lib-"))])
        if manifest == "pyproject.toml":
            m = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.M | re.S)
            return len(re.findall(r"[\"']", m.group(1))) // 2 if m else 0
    except Exception:
        return None
    return None


def main() -> None:
    rows = [ln.split("\t") for ln in (ROOT / "validate377.tsv").read_text().splitlines() if ln.strip()]

    print(f"{'PROJECT':32s} {'INPUT':26s} {'DECL':>5s} {'BEFORE':>7s} {'AFTER':>6s}  NOTICE   VERDICT")
    fixed = correct = regressed = still = unchanged = 0
    for slug, lock, ref in [(r[0], r[1], r[2] if len(r) > 2 else "") for r in rows]:
        name = slug.split("/")[-1]
        before = components(OUT / name / "before" / "sbom.cdx.json")
        after = components(OUT / name / "after" / "sbom.cdx.json")
        # Read from the document, not the log. The console wraps the
        # warning box across lines, so grepping for the banner text found
        # nothing even where it had fired -- and the property in the file
        # is the stronger claim anyway: it proves the disclosure travels
        # with the artifact rather than living only in CI output.
        notice = "no"
        doc = OUT / name / "after" / "sbom.cdx.json"
        if doc.is_file():
            try:
                props = (json.loads(doc.read_text()).get("metadata") or {}).get("properties") or []
                if any(pr.get("name") == "sbomify:resolution" for pr in props):
                    notice = "in doc"
            except Exception:
                pass
        if notice == "no":
            log = OUT / name / "after" / "log"
            if log.is_file() and "TO FIX THIS" in log.read_text(errors="replace"):
                notice = "log only"
        declared = runtime_deps(slug, ref, lock)

        # "Not run yet" is not a result. Without this the table gave a
        # verdict for projects with no output directory at all, and reading it
        # sent me looking for why rabbitmq had failed when it had simply not
        # started.
        if not (OUT / name / "after").is_dir():
            # Distinguish never-started from could-not-start. A validation
            # that quietly drops the project it failed to clone is the same
            # failure as a corpus reporting 500 of 500 with empty records.
            why = "clone failed" if "clone failed" in (ROOT / "validate377.log").read_text() and slug in (
                ROOT / "validate377.log"
            ).read_text() else "not run"
            print(f"{slug:32s} {lock[:26]:26s} {'':>5s} {'':>7s} {'':>6s}  {'':7s}  (no data: {why})")
            continue

        if (after or 0) > (before or 0):
            verdict, fixed = "FIXED", fixed + 1
        elif (after or 0) < (before or 0):
            verdict, regressed = "REGRESSED", regressed + 1
        elif declared == 0:
            verdict, correct = "correctly empty", correct + 1
        elif after:
            # Unchanged and non-empty is not a failure. symfony produces 22
            # components before and after -- it was fixed by an earlier change
            # -- and calling that "still empty" reported a working project as
            # a broken one.
            verdict, unchanged = "unchanged (already worked)", unchanged + 1
        else:
            verdict, still = "still empty", still + 1

        print(
            f"{slug:32s} {lock[:26]:26s} {str(declared if declared is not None else '?'):>5s} "
            f"{str(before if before is not None else '-'):>7s} {str(after if after is not None else '-'):>6s}"
            f"  {notice:7s}  {verdict}"
        )

    print(f"\n  fixed            {fixed}")
    print(f"  correctly empty  {correct}   (project declares no runtime dependencies)")
    print(f"  unchanged        {unchanged}   (already produced components before this change)")
    print(f"  still empty      {still}")
    print(f"  REGRESSED        {regressed}")


if __name__ == "__main__":
    main()
