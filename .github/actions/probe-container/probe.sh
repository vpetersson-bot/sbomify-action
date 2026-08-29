#!/bin/sh
# What a Docker container action actually sees on a hosted runner.
echo "########## CONTAINER ACTION ##########"
echo "identity:        uid=$(id -u) gid=$(id -g) groups=$(id -G)"
echo "HOME:            [$HOME]"
echo "cwd:             $(pwd)"
echo "GITHUB_WORKSPACE:[$GITHUB_WORKSPACE]"
echo "workspace owner: $(stat -c '%u:%g %a' "$GITHUB_WORKSPACE" 2>/dev/null)"
echo "github_home:     $(stat -c '%u:%g %a' /github/home 2>/dev/null)"

echo "--- env precedence (caller set all three via env:) ---"
echo "COMPONENT_PURL:  [$COMPONENT_PURL]     <- caller env:, input UNSET, runs.env maps empty input"
echo "BOM_TYPE:        [$BOM_TYPE]           <- caller env:, input default 'sbom', runs.env maps it"
echo "PLAIN_ENV:       [$PLAIN_ENV]          <- caller env: only, not in runs.env at all"
echo "INPUT_COMPONENT_PURL: [$INPUT_COMPONENT_PURL]"
echo "INPUT_BOM_TYPE:  [$INPUT_BOM_TYPE]"

echo "--- docker socket ---"
if [ -S /var/run/docker.sock ]; then
  echo "socket:          present, $(stat -c '%u:%g %a' /var/run/docker.sock)"
  echo "socket writable: $([ -w /var/run/docker.sock ] && echo yes || echo NO)"
else
  echo "socket:          ABSENT"
fi
echo "docker on PATH:  $(command -v docker || echo no)"

echo "--- OIDC ---"
echo "ACTIONS_ID_TOKEN_REQUEST_URL set: $([ -n "$ACTIONS_ID_TOKEN_REQUEST_URL" ] && echo yes || echo no)"

echo "--- write test into workspace ---"
if touch "$GITHUB_WORKSPACE/.probe-container" 2>/dev/null; then
  echo "workspace write: OK, file owned $(stat -c '%u:%g' "$GITHUB_WORKSPACE/.probe-container")"
  rm -f "$GITHUB_WORKSPACE/.probe-container"
else
  echo "workspace write: DENIED"
fi
