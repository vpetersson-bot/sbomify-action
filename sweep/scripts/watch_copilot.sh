#!/usr/bin/env bash
# Emit one line per new Copilot review item on any open PR.
#
# Copilot arrives under two different logins depending on where it writes:
# inline review comments come from "Copilot", the review that wraps them from
# "copilot-pull-request-reviewer[bot]". Matching on a case-insensitive
# substring covers both without guessing at future renames.
#
# State lives in a file of item IDs already reported, so a restart does not
# replay history. The first run seeds that file from whatever is already
# there and stays silent about it -- existing feedback is reported separately,
# once, rather than arriving as a burst of notifications.
set -uo pipefail

STATE=/home/ubuntu/sbomify-eval/.copilot-seen
INTERVAL=${INTERVAL:-120}
touch "$STATE"

emit_new() {
  local pr=$1 kind=$2 line id
  # `|| true` on every API call: a transient failure must not end the watch.
  case $kind in
    comments)
      gh api "repos/sbomify/sbomify-action/pulls/$pr/comments" \
        --jq '.[] | select(.user.login | ascii_downcase | contains("copilot"))
              | "c\(.id)\t\(.path):\(.line // 0)\t\(.body | gsub("\n"; " ") | .[0:220])"' 2>/dev/null || true
      ;;
    reviews)
      gh api "repos/sbomify/sbomify-action/pulls/$pr/reviews" \
        --jq '.[] | select(.user.login | ascii_downcase | contains("copilot"))
              | select(.body != "")
              | "r\(.id)\t\(.state)\t\(.body | gsub("\n"; " ") | .[0:220])"' 2>/dev/null || true
      ;;
  esac
}

while true; do
  prs=$(gh pr list --repo sbomify/sbomify-action --state open --json number --jq '.[].number' 2>/dev/null || true)
  for pr in $prs; do
    for kind in comments reviews; do
      while IFS=$'\t' read -r id where body; do
        [ -z "${id:-}" ] && continue
        if ! grep -qxF "$pr:$id" "$STATE" 2>/dev/null; then
          echo "$pr:$id" >> "$STATE"
          [ "${SEED:-0}" = "1" ] && continue
          echo "PR #$pr — Copilot [$where]: $body"
        fi
      done < <(emit_new "$pr" "$kind")
    done
  done
  [ "${SEED:-0}" = "1" ] && exit 0
  sleep "$INTERVAL"
done
