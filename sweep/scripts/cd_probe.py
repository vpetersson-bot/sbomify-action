#!/usr/bin/env python3
"""Probe clearly-cached directly with real coordinates from the run's SBOMs.

The pipeline only consults clearly-cached when higher-priority sources miss,
so its logs undercount how it behaves. This asks it about every coordinate
the run actually produced, at modest concurrency, and reports the status and
latency distribution -- which separates "the service is slow/erroring" from
"the pipeline rarely asks it anything".
"""

import json
import pathlib
import random
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests
from packageurl import PackageURL

BASE = "https://clearly-cached.sbomify.com"
CD_TYPE = {
    "pypi": "pypi/pypi", "npm": "npm/npmjs", "cargo": "crate/cratesio",
    "maven": "maven/mavencentral", "gem": "gem/rubygems",
    "nuget": "nuget/nuget", "golang": "go/golang",
}

from urllib.parse import quote


def coords(limit):
    """Collect distinct (type, namespace, name, version) from every SBOM."""
    seen = set()
    for f in pathlib.Path("/home/ubuntu/sbomify-eval/out").glob("*.json"):
        try:
            doc = json.loads(f.read_text())
        except Exception:
            continue
        for c in doc.get("components") or []:
            purl = c.get("purl") or ""
            if not purl.startswith("pkg:"):
                continue
            # Parse rather than split. A purl percent-encodes its segments --
            # an npm scope is stored as "%40types" -- so string-splitting and
            # re-quoting yields "%2540types" and the service rejects it as an
            # invalid coordinate. That is a bug in the probe, not the API, and
            # it is exactly what the action avoids by using PackageURL here.
            try:
                p = PackageURL.from_string(purl)
            except Exception:
                continue
            if p.type not in CD_TYPE or not p.version:
                continue
            seen.add((p.type, p.namespace or "-", p.name, p.version))
    out = sorted(seen)
    random.Random(0).shuffle(out)
    return out[:limit]


def probe(session, c):
    ptype, ns, name, ver = c
    url = f"{BASE}/v1/definitions/{CD_TYPE[ptype]}/" + "/".join(
        quote(p, safe="") for p in (ns, name, ver))
    t0 = time.time()
    try:
        r = session.get(url, timeout=30)
        dt = time.time() - t0
        harvested = None
        if r.status_code == 200:
            try:
                harvested = bool(r.json().get("harvested"))
            except Exception:
                harvested = None
        return r.status_code, dt, harvested, ptype
    except Exception as e:
        return type(e).__name__, time.time() - t0, None, ptype


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    cs = coords(limit)
    print(f"probing {len(cs)} distinct coordinates\n")
    s = requests.Session()
    s.headers["User-Agent"] = "sbomify-eval/1.0"
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(lambda c: probe(s, c), cs))

    status = Counter(r[0] for r in res)
    lat = sorted(r[1] for r in res)
    harv = Counter(r[2] for r in res if r[0] == 200)
    by_type = Counter()
    ok_by_type = Counter()
    for st, _, h, t in res:
        by_type[t] += 1
        if st == 200 and h:
            ok_by_type[t] += 1

    print("## Status")
    for k, v in status.most_common():
        print(f"  {str(k):12s} {v:5d}  {100*v/len(res):5.1f}%")
    print("\n## Harvested (of HTTP 200)")
    for k, v in harv.most_common():
        print(f"  {str(k):12s} {v:5d}")
    print("\n## Latency (s)")
    if lat:
        print(f"  p50 {lat[len(lat)//2]:.2f}  p90 {lat[int(len(lat)*.9)]:.2f} "
              f" p99 {lat[min(int(len(lat)*.99), len(lat)-1)]:.2f}  max {lat[-1]:.2f}")
    print("\n## Useful answer rate by purl type (200 + harvested)")
    for t in sorted(by_type):
        print(f"  {t:10s} {ok_by_type[t]:4d}/{by_type[t]:<4d} "
              f"{100*ok_by_type[t]/by_type[t]:5.1f}%")


if __name__ == "__main__":
    main()
