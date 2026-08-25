#!/usr/bin/env python3
"""Clear the records the harness measured without the tooling filter.

Seventeen projects were handed an input the product would never have chosen,
because the harness mirrored _default_selected without _is_tooling. Rather
than trust the list written down by hand, it is recomputed here from each
record against the product's own function -- the same rule this whole
evaluation keeps relearning.
"""

import json
import pathlib
import shutil
from pathlib import PurePath

from sbomify_action.cli.wizard.screens.discover import _is_tooling

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")
META = ROOT / "v5/meta"


def main() -> None:
    rows = {
        line.split("\t")[1]: line
        for line in (ROOT / "projects_v5.tsv").read_text().splitlines()
        if line.strip()
    }
    rerun = []
    for f in sorted(META.glob("*.json")):
        if not f.stat().st_size:
            continue
        rec = json.loads(f.read_text())
        found = [d for d in (rec.get("discovered") or []) if not d.get("nested_repo")]
        if not found:
            continue

        harness_depth = min(d["depth"] for d in found)
        harness = {d["path"] for d in found if d["depth"] == harness_depth}

        real = [d for d in found if not _is_tooling(PurePath(d["path"]))]
        tier = real or found
        depth = min(d["depth"] for d in tier)
        product = {d["path"] for d in tier if d["depth"] == depth}

        if harness == product:
            continue

        slug = rec["slug"]
        key = f.stem
        print(f"  {rec['ecosystem']:11s} {slug}")
        f.unlink()
        shutil.rmtree(ROOT / "v5/out" / key, ignore_errors=True)
        shutil.rmtree(ROOT / "v5/locks" / key, ignore_errors=True)
        rerun.append(rows[slug])

    (ROOT / "rerun.tsv").write_text("".join(r + "\n" for r in rerun))
    print(f"cleared {len(rerun)} records; wrote rerun.tsv")


if __name__ == "__main__":
    main()
