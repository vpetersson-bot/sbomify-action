#!/usr/bin/env python3
"""Review sbomify/sbom-tools#32 by parsing what it produces, not reading it.

sbom-tools runs no CI on pull requests, so a change to bundles.toml is
unverified at review time. TOML's table-scoping rules are exactly the kind of
thing that reads fine and parses differently.
"""

import base64
import json
import subprocess
import tomllib


def fetch(ref: str, path: str) -> str:
    out = subprocess.run(
        ["gh", "api", f"repos/sbomify/sbom-tools/contents/{path}?ref={ref}"],
        capture_output=True, text=True, check=True,
    ).stdout
    return base64.b64decode(json.loads(out)["content"]).decode()


head = subprocess.run(
    ["gh", "pr", "view", "32", "--repo", "sbomify/sbom-tools", "--json", "headRefName", "--jq", ".headRefName"],
    capture_output=True, text=True, check=True,
).stdout.strip()

before = tomllib.loads(fetch("master", "bundles.toml"))["bundle"]["jvm"]
after = tomllib.loads(fetch(head, "bundles.toml"))["bundle"]["jvm"]

print(f"branch: {head}\n")
print("keys on [bundle.jvm]")
print(f"  before: {sorted(before)}")
print(f"  after:  {sorted(after)}")

lost = sorted(set(before) - set(after))
print(f"\nkeys LOST from [bundle.jvm]: {lost or 'none'}")
for key in lost:
    print(f"  {key} = {str(before[key])[:90]}")

if "wrappers" in after:
    print(f"\nwhere they went -- [bundle.jvm.wrappers] contents:")
    print(f"  {json.dumps(after['wrappers'], indent=2)[:900]}")
