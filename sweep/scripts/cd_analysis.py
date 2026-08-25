#!/usr/bin/env python3
"""Quantify what clearly-cached actually returned across the whole run.

Rich wraps console output at the terminal width, so a single WARNING is
spread over two or three lines. Everything here first re-joins those
continuations back into one logical line before matching, otherwise the
tail of every message (which is where the reason lives) is invisible.
"""

import pathlib
import re
from collections import Counter

LOGS = pathlib.Path("/home/ubuntu/sbomify-eval/logs")

# A new log line starts with a timestamp or a level keyword at a fixed
# indent; anything else is a continuation of the previous one.
NEW = re.compile(r"^\[\d\d/\d\d/\d\d |^\s{10,}(WARNING|INFO|ERROR|DEBUG)\s")


def logical_lines(path):
    buf = ""
    for raw in path.read_text(errors="replace").splitlines():
        if NEW.match(raw):
            if buf:
                yield buf
            buf = " ".join(raw.split())
        else:
            buf += " " + " ".join(raw.split())
    if buf:
        yield buf


def main():
    reason = Counter()
    per_repo = Counter()
    ecosys = Counter()
    other_src = Counter()

    for f in sorted(LOGS.glob("*.log")):
        for line in logical_lines(f):
            if "clearlydefined.io" not in line:
                # Track transient failures from every other source too, so
                # clearly-cached's rate can be compared against them rather
                # than read in isolation.
                if "Transient failure from" in line:
                    m = re.search(r"Transient failure from (\S+)", line)
                    if m:
                        other_src[m.group(1)] += 1
                continue
            if "Transient failure" not in line:
                continue
            per_repo[f.stem] += 1
            if "not yet harvested" in line:
                reason["not_yet_harvested"] += 1
            elif m := re.search(r"HTTP (\d{3})", line):
                reason[f"HTTP {m.group(1)}"] += 1
            elif "skipped after" in line:
                reason["circuit_open_skip"] += 1
            else:
                reason["other"] += 1
            if m := re.search(r"pkg:([a-z]+)/", line):
                ecosys[m.group(1)] += 1

    total = sum(reason.values())
    print(f"clearly-cached transient events: {total}\n")
    print("## Reason")
    for k, v in reason.most_common():
        print(f"  {k:22s} {v:6d}  {100*v/max(total,1):5.1f}%")
    print("\n## By purl type")
    for k, v in ecosys.most_common(10):
        print(f"  {k:22s} {v:6d}")
    print("\n## Worst repos")
    for k, v in per_repo.most_common(10):
        print(f"  {k:38s} {v:6d}")
    print("\n## Transient failures from other sources (for comparison)")
    for k, v in other_src.most_common(10):
        print(f"  {k:22s} {v:6d}")


if __name__ == "__main__":
    main()
