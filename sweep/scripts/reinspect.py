#!/usr/bin/env python3
"""Re-score every SBOM on disk and write the result back into its record.

The inspector changed (packages are now scored separately from syft's
per-file entries), and the SBOMs are all still on disk, so the whole corpus
can be re-scored without re-running anything. Only the `sbom` block is
replaced; the run outcome recorded around it is left alone.
"""

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path("/home/ubuntu/sbomify-eval")


def rescore(meta_dir, out_dir):
    meta_dir, out_dir = ROOT / meta_dir, ROOT / out_dir
    if not meta_dir.is_dir():
        return 0, 0
    done = missing = 0
    for rec_path in sorted(meta_dir.glob("*.json")):
        try:
            rec = json.loads(rec_path.read_text())
        except Exception:
            continue
        sbom = out_dir / f"{rec_path.stem}.cdx.json"
        if not sbom.is_file():
            sbom = out_dir / f"{rec_path.stem}.json"
        if not sbom.is_file():
            missing += 1
            continue
        res = subprocess.run(
            [sys.executable, str(ROOT / "inspect_sbom.py"), str(sbom)],
            capture_output=True, text=True)
        try:
            rec["sbom"] = json.loads(res.stdout)
        except Exception:
            missing += 1
            continue
        rec_path.write_text(json.dumps(rec))
        done += 1
    return done, missing


for m, o in (("meta", "out"), ("meta2", "out2"), ("meta_jvm", "out_jvm")):
    d, x = rescore(m, o)
    if d or x:
        print(f"{m}: rescored {d}, no sbom on disk {x}")
