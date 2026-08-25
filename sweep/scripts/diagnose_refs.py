#!/usr/bin/env python3
"""Why did these five resolve the way they did?

apache/hadoop -> 0.92RC0        a release candidate from 2011
apache/zookeeper -> 2.2.1       ZooKeeper is on 3.9.x
django/django -> 6.1a1          an alpha
phoenixframework/phoenix -> v1.5.3   unchanged; Phoenix is on 1.7.x
hashicorp/vault -> v2.0.4       Vault is on 1.x

Prints what the resolver saw so the fix addresses the cause rather than the
symptom.
"""

import subprocess
import sys

sys.path.insert(0, "/home/ubuntu/sbomify-eval")
from resolve_releases import _is_release_tag, _sort_key  # noqa: E402

REPOS = [
    ("apache/hadoop", "https://github.com/apache/hadoop.git"),
    ("apache/zookeeper", "https://github.com/apache/zookeeper.git"),
    ("django/django", "https://github.com/django/django.git"),
    ("phoenixframework/phoenix", "https://github.com/phoenixframework/phoenix.git"),
    ("hashicorp/vault", "https://github.com/hashicorp/vault.git"),
]

for slug, url in REPOS:
    out = subprocess.run(
        ["gh", "api", f"repos/{slug}/releases?per_page=100",
         "--jq", '.[] | select(.draft == false and .prerelease == false) | .tag_name'],
        capture_output=True, text=True,
    )
    releases = [t.strip() for t in out.stdout.splitlines() if t.strip()]
    usable = [t for t in releases if _is_release_tag(t, slug)]

    print(f"\n=== {slug}")
    print(f"  published non-prerelease releases: {len(releases)}")
    print(f"  first few: {releases[:5]}")
    print(f"  accepted by the classifier: {len(usable)}")
    if usable:
        top = sorted(usable, key=_sort_key, reverse=True)[:5]
        print(f"  highest by sort key: {[(t, _sort_key(t)) for t in top[:3]]}")
        print(f"  -> would choose: {max(usable, key=_sort_key)}")
    else:
        print("  (falls through to tags)")
        ls = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", url],
            capture_output=True, text=True, timeout=300,
            env={"PATH": "/usr/bin:/bin", "GIT_CONFIG_GLOBAL": "/home/ubuntu/sbomify-eval/gitconfig"},
        )
        tags = [ln.split("refs/tags/", 1)[1].strip() for ln in ls.stdout.splitlines() if "refs/tags/" in ln]
        ok = [t for t in tags if _is_release_tag(t, slug)]
        print(f"  tags: {len(tags)}, accepted: {len(ok)}")
        if ok:
            top = sorted(ok, key=_sort_key, reverse=True)[:5]
            print(f"  highest: {[(t, _sort_key(t)) for t in top[:3]]}")
