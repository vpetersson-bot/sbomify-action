#!/usr/bin/env python3
"""Pin each of the 500 projects to the release a user would actually scan.

Every sweep before v5 cloned the default branch. That is the wrong subject: an
SBOM describes something you ship, and nobody ships master. The action does not
choose the checkout either -- the workflow does, and it is tag-triggered.

The first version of this script fixed that and introduced a subtler version of
the same mistake. Two ways:

  * It trusted GitHub's `releases/latest`, which is a **mutable flag** a
    maintainer sets, not "the newest release". phoenixframework/phoenix still
    points it at v1.5.3, four minor versions back.
  * Its tag fallback sorted with `--sort=-v:refname` and took the first line.
    Version-sorting tags that are not versions is meaningless, so it returned
    `show` for apache/kafka, `remove-ozone` for apache/hadoop, `assets` for
    Mic92/sops-nix and `zookeeper-` for apache/zookeeper. Scanning Kafka at a
    tag called "show" is not measuring Kafka.

So: parse versions rather than trust orderings, and refuse anything that does
not look like a release of the project itself.

The residue is deliberate. A monorepo that only ever tags per package --
dart-lang/sdk tagging `meta-v1.3.0`, flutter/packages tagging
`xdg_directories-v1.1.0` -- has no whole-project release, and inventing one
would be the same error again. Those fall through to the default branch and are
recorded as `released: false` so they can be excluded from any claim about
released software.
"""

import json
import pathlib
import re
import subprocess
import sys
from collections import Counter

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
GIT_ENV = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": str(ROOT / "gitconfig")}

#: The numeric core of a version: 1.2.3, 8_21_0, 3.10.3.0.
_NUMERIC = re.compile(r"^\d+(?:[._]\d+)*$")

#: A prerelease marker, in every shape these 500 projects actually use. Both
#: separated (`-rc.1`, `-nullsafety.2`, `.dev`) and welded to the number, which
#: is the form that slipped through: Django tags alphas `6.1a1`, and the digits
#: alone sort it above every 6.0.x release.
_PRERELEASE = re.compile(
    r"(?:^|[-._+])(?:a|b|c|m|rc|alpha|beta|dev|pre|preview|snapshot|nightly|canary"
    r"|milestone|test|unstable|nullsafety)\d*(?:$|[-._+])",
    re.I,
)
_WELDED_PRERELEASE = re.compile(r"\d(?:a|b|rc|m)\d+$", re.I)

#: Suffixes that mean "this is the real thing", not a prerelease.
_FINAL_SUFFIX = re.compile(r"^[-._](?:final|release|ga|stable)$", re.I)

#: Generic prefixes projects put in front of a version. `release-3.9.4` is how
#: ZooKeeper tags, `rel/release-3.4.1` is how Hadoop does. Neither carries the
#: project's name, and rejecting them left Hadoop on a release candidate from
#: 2011 and ZooKeeper on 2.2.1 while it ships 3.9.x.
#: `parent` is here because Maven's aggregator POM for a project is tagged
#: `<project>-parent-<version>`, and the repo-name match consumes only the
#: `<project>` half. Gson's newer tags are all `gson-parent-2.9.1`, so without
#: it the project stayed pinned to `gson-2.4` while shipping 2.11.
_GENERIC_PREFIXES = ("release", "releases", "rel", "v", "ver", "version", "tags", "tag", "parent")

#: Extract the numeric part for ordering.
_NUMS = re.compile(r"\d+")


def _looks_like_a_date(core: str) -> bool:
    """Whether this numeric core is a timestamp or a date rather than a version.

    Both forms outrank every real version under numeric comparison, which is
    how minio landed on `release-1434511043` (a 2015 unix timestamp) and
    tigerbeetle on `release-20230510.1905` while shipping 0.16.x.

    Also catches zero-padded leading components: semver has no `09`, and
    `release-09.11.1` is how batteries-included tagged in 2009 -- (9, 11, 1)
    beats the v3.9.0 it actually ships.
    """
    parts = core.replace("_", ".").split(".")
    if any(len(p) >= 6 for p in parts):
        return True
    return any(len(p) > 1 and p.startswith("0") for p in parts)


def _is_version(text: str) -> bool:
    """Whether this is a released version rather than a prerelease or a wildcard."""
    if not text:
        return False
    if _PRERELEASE.search(text) or _WELDED_PRERELEASE.search(text):
        return False
    core_match = re.match(r"^\d+(?:[._]\d+)*", text)
    if core_match and _looks_like_a_date(core_match.group(0)):
        return False
    if _NUMERIC.match(text):
        return True
    # A numeric core plus a suffix that means "final": netty-4.2.17.Final.
    head = _NUMERIC.match(text.split("-")[0].split("+")[0])
    if not head:
        # Try splitting on the last dot: 4.2.17.Final
        stem, dot, tail = text.rpartition(".")
        if dot and _NUMERIC.match(stem) and _FINAL_SUFFIX.match("." + tail):
            return True
        return False
    rest = text[head.end() :]
    return not rest or bool(_FINAL_SUFFIX.match(rest))


def _is_release_tag(tag: str, repo: str) -> bool:
    """Whether this tag names a release of *this project*.

    Accepts a bare version, a version behind a generic prefix, and a version
    behind the project's own name -- curl tags `curl-8_21_0`, Camel tags
    `camel-4.22.0`, Erlang tags `OTP-29.0.5`. The name has to match the
    repository for that last form to count, which is what keeps `meta-v1.3.0`
    out of dart-lang/sdk while letting `curl-8_21_0` into curl.
    """
    if not tag:
        return False

    # Path-shaped tags: keep the last segment if everything before it is a
    # generic prefix (`rel/release-3.4.1`, `releases/lucene/10.5.0`), and
    # reject otherwise so `stable/5.1.x` stays out.
    if "/" in tag:
        *lead, tag = tag.split("/")
        name = repo.split("/")[-1].lower()
        if not all(part.lower().rstrip("-_") in _GENERIC_PREFIXES or part.lower() == name for part in lead):
            return False

    candidates = [tag]
    lowered = tag.lower()
    name = repo.split("/")[-1].lower()
    squashed = name.replace("-", "").replace("_", "").replace(".", "")

    for sep in ("-", "_", "@", "/"):
        head, found, rest = tag.partition(sep)
        if not found or not rest:
            continue
        h = head.lower()
        if h.rstrip("-_") in _GENERIC_PREFIXES or h.replace("-", "").replace("_", "").replace(".", "") == squashed:
            candidates.append(rest)

    # `release-3.9.4` and `curl-8_21_0` reduce in one step; `rel/release-3.4.1`
    # already lost its path segment above.
    for candidate in list(candidates):
        for prefix in _GENERIC_PREFIXES:
            if candidate.lower().startswith(prefix) and len(candidate) > len(prefix):
                tail = candidate[len(prefix) :].lstrip("-_.")
                if tail and tail != candidate:
                    candidates.append(tail)

    if any(bad in lowered for bad in ("nightly", "canary", "snapshot")):
        return False
    return any(_is_version(c) for c in candidates)


def _sort_key(tag: str) -> tuple:
    """Numeric ordering, so 10.0 beats 9.0 and 8_21_0 beats 8_9_0."""
    return tuple(int(n) for n in _NUMS.findall(tag)[:6]) or (0,)


def newest_release(slug: str) -> tuple[str, str] | None:
    """The highest-versioned published release, ignoring the `latest` flag."""
    out = subprocess.run(
        ["gh", "api", f"repos/{slug}/releases?per_page=100",
         "--jq", '.[] | select(.draft == false and .prerelease == false) | .tag_name'],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        return None
    tags = [t.strip() for t in out.stdout.splitlines() if t.strip()]
    usable = [t for t in tags if _is_release_tag(t, slug)]
    if usable:
        return max(usable, key=_sort_key), "release"

    # Nothing version-shaped, but the project still publishes releases.
    #
    # minio tags every release `RELEASE.2025-10-15T17-29-55Z`. There is no
    # version to compare, so version ranking correctly refuses all of them --
    # and then, with no fallback, the project was pinned to whatever an
    # earlier and looser rule had accepted: `release-1434511043`, a 2015 unix
    # timestamp. It was scanned at a tree three years older than Go modules,
    # found no go.mod, and was recorded as "no recognised input" -- a coverage
    # gap invented entirely by the harness.
    #
    # When no candidate can be ordered by version, order by what GitHub says
    # was published most recently. That is a weaker signal -- publication
    # order is not release order for projects that backport -- so it is used
    # only when the stronger one yields nothing, and the source is recorded
    # as "published" to keep the distinction visible in the corpus.
    latest = subprocess.run(
        ["gh", "api", f"repos/{slug}/releases?per_page=100",
         "--jq", '[.[] | select(.draft == false and .prerelease == false)] '
                 '| sort_by(.published_at) | reverse | .[0].tag_name'],
        capture_output=True, text=True,
    )
    if latest.returncode == 0 and (name := latest.stdout.strip()) and name != "null":
        return name, "published"
    return None


def newest_tag(slug: str, url: str) -> tuple[str, str] | None:
    ls = subprocess.run(
        ["git", "ls-remote", "--tags", "--refs", url],
        capture_output=True, text=True, timeout=300, env=GIT_ENV,
    )
    if ls.returncode != 0:
        return None
    tags = [ln.split("refs/tags/", 1)[1].strip() for ln in ls.stdout.splitlines() if "refs/tags/" in ln]
    usable = [t for t in tags if _is_release_tag(t, slug)]
    if usable:
        return max(usable, key=_sort_key), "tag"
    return None


def main() -> None:
    rows = [ln.rstrip("\n").split("\t") for ln in (ROOT / "v4/all.tsv").read_text().splitlines() if ln.strip()]
    resolved, how = [], Counter()

    for i, (eco, slug, url, note) in enumerate(rows, 1):
        # Both, then the higher version -- not "releases, else tags".
        #
        # Phoenix publishes GitHub releases up to v1.5.3 and tags everything
        # after that, so preferring releases pinned it four minor versions
        # back. A release is better *evidence* that a version was shipped, but
        # it is not evidence that nothing newer was.
        candidates = [c for c in (newest_release(slug), newest_tag(slug, url)) if c]
        if candidates:
            ref, source = max(candidates, key=lambda c: _sort_key(c[0]))
        else:
            ref, source = "@default", "default-branch"
        how[source] += 1
        resolved.append((eco, slug, url, note, ref))
        if i % 50 == 0:
            print(f"  {i}/{len(rows)}", file=sys.stderr)

    (ROOT / "projects_v5.tsv").write_text("".join("\t".join(r) + "\n" for r in resolved))
    (ROOT / "v5_refs.json").write_text(json.dumps({r[1]: r[4] for r in resolved}, indent=1))

    print(f"wrote {len(resolved)} projects")
    for source, n in how.most_common():
        print(f"  {n:4d}  {source}")


if __name__ == "__main__":
    main()
