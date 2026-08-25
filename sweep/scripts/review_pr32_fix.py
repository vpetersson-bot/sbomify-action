#!/usr/bin/env python3
"""Check that the placement I am about to suggest actually parses.

A review that says "move it" without showing the moved version parses is
worth less than one that does, especially in a repository with no PR CI.
"""

import base64
import json
import re
import subprocess
import tomllib

head = subprocess.run(
    ["gh", "pr", "view", "32", "--repo", "sbomify/sbom-tools", "--json", "headRefName", "--jq", ".headRefName"],
    capture_output=True, text=True, check=True,
).stdout.strip()

raw = base64.b64decode(
    json.loads(
        subprocess.run(
            ["gh", "api", f"repos/sbomify/sbom-tools/contents/bundles.toml?ref={head}"],
            capture_output=True, text=True, check=True,
        ).stdout
    )["content"]
).decode()

lines = raw.splitlines(keepends=True)

# Lift the two wrapper tables (and the comment block above them) out.
start = next(i for i, ln in enumerate(lines) if ln.strip().startswith("# The build-tool wrappers"))
end = next(i for i, ln in enumerate(lines) if ln.strip() == 'tool = "mvn"') + 1
block = lines[start:end]
rest = lines[:start] + lines[end:]

# Put them back immediately before the first sub-table of [bundle.jvm], which
# is where a sub-table can live without swallowing the keys that follow.
anchor = next(i for i, ln in enumerate(rest) if re.match(r"\s*\[bundle\.jvm\.upstream", ln))
fixed = "".join(rest[:anchor] + block + ["\n"] + rest[anchor:])

before = tomllib.loads(base64.b64decode(
    json.loads(subprocess.run(
        ["gh", "api", "repos/sbomify/sbom-tools/contents/bundles.toml?ref=master"],
        capture_output=True, text=True, check=True).stdout)["content"]).decode())["bundle"]["jvm"]
after = tomllib.loads(fixed)["bundle"]["jvm"]

print("with the block moved before the first [bundle.jvm.upstream.*] table:")
print(f"  keys on [bundle.jvm]: {sorted(after)}")
print(f"  lost vs master:       {sorted(set(before) - set(after) - {'wrappers'}) or 'none'}")
print(f"  env intact:           {after.get('env', {}).get('JAVA_HOME')!r}")
print(f"  built intact:         {after.get('built')}")
print(f"  npm_install intact:   {after.get('npm_install')}")
print(f"  wrappers:             {sorted(after.get('wrappers', {}))}")
print(f"  maven wrapper keys:   {sorted(after.get('wrappers', {}).get('maven', {}))}")
