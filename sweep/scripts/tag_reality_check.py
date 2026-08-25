#!/usr/bin/env python3
"""How often would the tag path in #365 actually fire?

The objection: a CI run almost always checks out a branch, not a tag, so the
"use the tag" branch is close to dead code and the real behaviour is "always
emit 0.0.0+g<sha>".

Two things to measure rather than argue:

1. Would the tag have applied for the corpus at all? Every clone in this
   evaluation is `git clone --depth 1` of the default branch, which is exactly
   the shape a CI checkout has.

2. Is there a better source sitting right there? A project's own manifest
   usually states a version -- pyproject.toml, package.json, Cargo.toml -- and
   that is a version a registry and a CVE feed both know, which 0.0.0+g<sha>
   is not.

Samples the projects whose root version came out as a placeholder.
"""

import json
import pathlib
import re
import subprocess
import sys
import tempfile

V4 = pathlib.Path("/home/ubuntu/sbomify-eval/v4")
SHA = re.compile(r"^(sha256:)?[0-9a-f]{32,}$", re.I)
PLACEHOLDERS = {"latest", "unknown", "none", "n/a", ""}


def placeholder(v):
    if not v:
        return True
    return v.strip().lower() in PLACEHOLDERS or bool(SHA.match(v.strip()))


def manifest_version(repo: pathlib.Path) -> tuple[str, str] | None:
    """What the project itself says its version is."""
    pj = repo / "package.json"
    if pj.is_file():
        try:
            v = json.loads(pj.read_text()).get("version")
            if v:
                return ("package.json", str(v))
        except Exception:
            pass
    pp = repo / "pyproject.toml"
    if pp.is_file():
        text = pp.read_text()
        for pat in (r'^\s*version\s*=\s*"([^"]+)"', r'^\s*version\s*=\s*\'([^\']+)\''):
            if m := re.search(pat, text, re.M):
                return ("pyproject.toml", m.group(1))
    ct = repo / "Cargo.toml"
    if ct.is_file():
        if m := re.search(r'^\s*version\s*=\s*"([^"]+)"', ct.read_text(), re.M):
            return ("Cargo.toml", m.group(1))
    cj = repo / "composer.json"
    if cj.is_file():
        try:
            v = json.loads(cj.read_text()).get("version")
            if v:
                return ("composer.json", str(v))
        except Exception:
            pass
    return None


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    targets = []
    for f in sorted(V4.glob("meta/*.json")):
        try:
            rec = json.loads(f.read_text())
        except Exception:
            continue
        out = V4 / "out" / f"{f.stem}.cdx.json"
        if not out.is_file():
            continue
        try:
            root = (json.loads(out.read_text()).get("metadata") or {}).get("component") or {}
        except Exception:
            continue
        if root and placeholder(root.get("version")):
            targets.append((rec["slug"], rec.get("ecosystem"), root.get("version")))

    print(f"{len(targets)} SBOMs have a placeholder root version; sampling {limit}\n")
    print(f"{'project':34s} {'eco':10s} {'now':14s} {'at a tag?':10s} manifest says")

    at_tag = 0
    have_manifest = 0
    for slug, eco, current in targets[:limit]:
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp) / "r"
            url = f"https://github.com/{slug}.git"
            cl = subprocess.run(
                ["git", "clone", "--depth", "1", "--quiet", url, str(repo)],
                capture_output=True, text=True, timeout=600,
                env={"PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": "/home/ubuntu/sbomify-eval/gitconfig"},
            )
            if cl.returncode != 0:
                print(f"{slug:34s} {str(eco):10s} clone failed")
                continue
            tag = subprocess.run(
                ["git", "-C", str(repo), "describe", "--exact-match", "--tags", "HEAD"],
                capture_output=True, text=True,
            )
            tagged = "yes" if tag.returncode == 0 else "no"
            at_tag += tag.returncode == 0
            mv = manifest_version(repo)
            have_manifest += mv is not None
            shown = f"{mv[1]}  ({mv[0]})" if mv else "-"
            print(f"{slug:34s} {str(eco):10s} {str(current)[:13]:14s} {tagged:10s} {shown}")

    n = min(limit, len(targets))
    print(f"\nat a tag on a default-branch shallow clone: {at_tag}/{n}")
    print(f"manifest states a version:                  {have_manifest}/{n}")


if __name__ == "__main__":
    main()
