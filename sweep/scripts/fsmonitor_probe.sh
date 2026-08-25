#!/usr/bin/env bash
# Which git subcommands execute a hostile repo's core.fsmonitor?
#
# The first version of this probe ran rev-parse AND status and reported the
# combined result as PWNED. That conflated them: fsmonitor fires when the
# index is refreshed, which `status` does and `rev-parse HEAD` may not. Since
# resolve_root_version only ever runs `describe` and `rev-parse`, the honest
# question is whether *those two* are a vector -- so each is tested alone.
set -uo pipefail
W=/home/ubuntu/sbomify-eval/.fsmonitor-probe
R=$W/repo
rm -rf "$W"
mkdir -p "$R"

git -C /home/ubuntu/sbomify-eval/.fsmonitor-probe/repo init -q
git -C /home/ubuntu/sbomify-eval/.fsmonitor-probe/repo config user.email t@e.invalid
git -C /home/ubuntu/sbomify-eval/.fsmonitor-probe/repo config user.name T
git -C /home/ubuntu/sbomify-eval/.fsmonitor-probe/repo config commit.gpgsign false
git -C /home/ubuntu/sbomify-eval/.fsmonitor-probe/repo config tag.gpgSign false
echo x > "$R/f"
git -C /home/ubuntu/sbomify-eval/.fsmonitor-probe/repo add f
git -C /home/ubuntu/sbomify-eval/.fsmonitor-probe/repo commit -qm one
git -C /home/ubuntu/sbomify-eval/.fsmonitor-probe/repo tag v1.0.0

printf '#!/bin/sh\ntouch %s/PWNED\nexit 0\n' "$W" > "$W/payload.sh"
chmod +x "$W/payload.sh"
git -C /home/ubuntu/sbomify-eval/.fsmonitor-probe/repo config core.fsmonitor "$W/payload.sh"

probe() {  # $1 = label, then the git args
  local label=$1; shift
  rm -f "$W/PWNED"
  git -C /home/ubuntu/sbomify-eval/.fsmonitor-probe/repo "$@" >/dev/null 2>&1
  if [ -e "$W/PWNED" ]; then echo "  PWNED   $label"; else echo "  clean   $label"; fi
}

echo "unhardened:"
probe "rev-parse HEAD" rev-parse HEAD
probe "describe --exact-match --tags HEAD" describe --exact-match --tags HEAD
probe "status --porcelain (not used by us; the control)" status --porcelain

rm -rf "$W"
