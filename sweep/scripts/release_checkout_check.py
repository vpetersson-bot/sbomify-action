#!/usr/bin/env python3
"""What changes if the testbed checks out releases instead of default branches?

The corpus clones each project's default branch, which is not what anyone
generates an SBOM for. An SBOM describes something you ship, and what you ship
is a release. Measuring master means measuring a moving target nobody
installs -- so a placeholder root version may be an artifact of the harness
rather than a defect in the tool.

Two things worth separating, because they pull in opposite directions:

  * does the project's own manifest state a real version at the release tag,
    where at master it did not? (then the testbed is the whole problem)
  * does the tag itself supply one where the manifest still cannot?
    (then the testbed fix and #365 are complementary, not alternatives)
"""

import json
import pathlib
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, "/home/ubuntu/code/sbomify-action/.claude/worktrees/purrfect-beaming-snowglobe")

V4 = pathlib.Path("/home/ubuntu/sbomify-eval/v4")
SHA = re.compile(r"^(sha256:)?[0-9a-f]{32,}$", re.I)
PLACEHOLDERS = {"latest", "unknown", "none", "n/a", ""}
GIT_ENV = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": "/home/ubuntu/sbomify-eval/gitconfig"}


def placeholder(v):
    if not v:
        return True
    return v.strip().lower() in PLACEHOLDERS or bool(SHA.match(v.strip()))


def latest_release(slug: str) -> str | None:
    out = subprocess.run(
        ["gh", "api", f"repos/{slug}/releases/latest", "--jq", ".tag_name"],
        capture_output=True, text=True,
    )
    if out.returncode == 0 and out.stdout.strip():
        return out.stdout.strip()
    # No GitHub release; fall back to the newest tag the remote advertises.
    ls = subprocess.run(
        ["git", "ls-remote", "--tags", "--refs", "--sort=-v:refname", f"https://github.com/{slug}.git"],
        capture_output=True, text=True, timeout=300, env=GIT_ENV,
    )
    if ls.returncode != 0:
        return None
    for line in ls.stdout.splitlines():
        if "\trefs/tags/" in line:
            return line.split("refs/tags/", 1)[1].strip()
    return None


def manifest_version(repo: pathlib.Path) -> str | None:
    pj = repo / "package.json"
    if pj.is_file():
        try:
            if v := json.loads(pj.read_text()).get("version"):
                return str(v)
        except Exception:
            pass
    for name, pat in (("pyproject.toml", r'^\s*version\s*=\s*"([^"]+)"'), ("Cargo.toml", r'^\s*version\s*=\s*"([^"]+)"')):
        f = repo / name
        if f.is_file() and (m := re.search(pat, f.read_text(), re.M)):
            return m.group(1)
    return None


def main() -> None:
    from sbomify_action._augmentation.root_version import resolve_root_version

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 8
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

    print(f"{'project':30s} {'eco':9s} {'master gave':13s} {'release tag':16s} {'manifest@tag':14s} #365 gives")
    manifest_fixes = tag_fixes = 0
    n = 0
    for slug, eco, current in targets[:limit]:
        tag = latest_release(slug)
        if not tag:
            print(f"{slug:30s} {str(eco):9s} {str(current)[:12]:13s} (no release)")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp) / "r"
            cl = subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", tag, "--quiet",
                 f"https://github.com/{slug}.git", str(repo)],
                capture_output=True, text=True, timeout=900, env=GIT_ENV,
            )
            if cl.returncode != 0:
                print(f"{slug:30s} {str(eco):9s} {str(current)[:12]:13s} {tag:16s} clone failed")
                continue
            n += 1
            mv = manifest_version(repo)
            derived = resolve_root_version(repo)
            manifest_fixes += mv is not None and not placeholder(mv)
            tag_fixes += derived is not None and not derived.startswith("0.0.0+")
            print(f"{slug:30s} {str(eco):9s} {str(current)[:12]:13s} {tag[:15]:16s} {str(mv)[:13]:14s} {derived}")

    print(f"\nof {n} checked out at their release:")
    print(f"  manifest alone now states a real version: {manifest_fixes}/{n}")
    print(f"  #365 derives a real version from the tag: {tag_fixes}/{n}")


if __name__ == "__main__":
    main()
