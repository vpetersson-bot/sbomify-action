#!/usr/bin/env python3
"""Run the SHIPPED rule over the corpus, not a copy of it.

prototype_guard*.py reimplemented the logic to explore the shape; that is how
you get findings that describe the harness rather than the product. This
imports the real default_selection and replays each project's recorded
discovery against a tmp directory holding that repo's real root listing.

The baseline is the same function with the guard disabled -- not what the
harness happened to run, which was a capped multi-target rule and would have
attributed its own differences to this change.
"""

import json
import pathlib
import sys
import tempfile
from unittest import mock

sys.path.insert(0, "/home/ubuntu/code/sbomify-action/.claude/worktrees/purrfect-beaming-snowglobe")

from sbomify_action.cli.wizard.screens import discover as D  # noqa: E402
from sbomify_action.cli.wizard.state import DiscoveredLockfile  # noqa: E402

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
CACHE = ROOT / ".roots-cache"

changed, unchanged, blanked, no_root = [], 0, [], 0

for f in sorted((ROOT / "v5/meta").glob("*.json")):
    if not f.stat().st_size:
        continue
    rec = json.loads(f.read_text())
    discovered = [d for d in (rec.get("discovered") or []) if not d.get("nested_repo")]
    if not discovered:
        continue
    listing = CACHE / rec["slug"].replace("/", "_")
    if not listing.exists():
        no_root += 1
        continue
    names = json.loads(listing.read_text() or "[]")

    with tempfile.TemporaryDirectory() as td:
        top = pathlib.Path(td)
        for n in names:
            (top / n).write_text("")
        rows = [
            DiscoveredLockfile(
                path=top / d["path"],
                rel_path=pathlib.Path(d["path"]),
                ecosystem=d["ecosystem"],
                suggested_name=d.get("name") or "x",
            )
            for d in discovered
        ]
        after = D.default_selection(rows, top)
        declared = sorted(D.project_ecosystems(top))
        # Baseline: identical code path, guard neutralised.
        with mock.patch.object(D, "project_ecosystems", return_value=set()):
            before = D.default_selection(rows, top)

    if after == before:
        unchanged += 1
        continue
    was = sorted(str(rows[i].rel_path) for i in before)
    now = sorted(str(rows[i].rel_path) for i in after)
    if not after:
        blanked.append((rec["ecosystem"], rec["slug"], declared, was))
    else:
        changed.append((rec["ecosystem"], rec["slug"], declared, was, now))

print(f"identical {unchanged}   now selects nothing {len(blanked)}   narrowed {len(changed)}   no cached root {no_root}\n")
print("=== NOW SELECTS NOTHING ===")
for eco, slug, declared, was in blanked:
    print(f"   {slug:34s} root says {','.join(declared)[:18]:18s} was {str(was)[:60]}")

print("\n=== NARROWED ===")
for eco, slug, declared, was, now in changed:
    print(f"   {slug:30s} root says {','.join(declared)[:18]:18s}")
    for p in was:
        print(f"        {'keep ' if p in now else 'DROP '} {p}")
