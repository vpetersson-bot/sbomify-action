#!/usr/bin/env python3
"""Summarise the uploaded log export.

Grouped by shape rather than listed, because 787 rows of near-identical
messages hide the two or three that are actually distinct. Numbers, hashes,
paths and identifiers are masked before grouping so the same error with
different arguments collapses into one row.
"""

import csv
import pathlib
import re
from collections import Counter, defaultdict

PATH = pathlib.Path(
    "/home/ubuntu/.claude/uploads/ed8745d2-bd30-44a5-b92d-f32915f96655/"
    "0832eea0-AllMessagessearchresult.csv"
)

MASKS = [
    (re.compile(r"\b[0-9a-f]{7,}\b", re.I), "<hex>"),
    (re.compile(r"\b\d+\.\d+[\w.\-+]*"), "<version>"),
    (re.compile(r"\b\d+\b"), "<n>"),
    (re.compile(r"'[^']{1,80}'"), "'<s>'"),
    (re.compile(r'"[^"]{1,80}"'), '"<s>"'),
    (re.compile(r"/[\w./\-]{4,}"), "<path>"),
]


def shape(message: str) -> str:
    text = message.strip()
    for pattern, repl in MASKS:
        text = pattern.sub(repl, text)
    return text[:150]


rows = list(csv.DictReader(PATH.open()))
print(f"{len(rows)} rows")

sources = Counter(r["source"] for r in rows)
print("\nby source:")
for s, n in sources.most_common(10):
    print(f"  {n:4d}  {s}")

times = sorted(r["timestamp"] for r in rows if r.get("timestamp"))
if times:
    print(f"\nspan: {times[0]}  ->  {times[-1]}")

shapes: Counter[str] = Counter()
examples: dict[str, str] = {}
by_shape_sources: dict[str, set[str]] = defaultdict(set)
for r in rows:
    sh = shape(r["message"])
    shapes[sh] += 1
    examples.setdefault(sh, r["message"].strip()[:220])
    by_shape_sources[sh].add(r["source"])

print(f"\n{len(shapes)} distinct message shapes:\n")
for sh, n in shapes.most_common(25):
    srcs = ",".join(sorted(by_shape_sources[sh]))[:40]
    print(f"  {n:4d}  [{srcs}]")
    print(f"        {examples[sh]}")
