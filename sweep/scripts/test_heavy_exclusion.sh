#!/usr/bin/env bash
# Does the heavy family really serialise now?
#
# The claim being checked is the one that was wrong last time: not "never two
# java jobs" -- that held -- but "never two *heavy* jobs", which did not, and
# put java and kotlin side by side at 4 GB each on a box with room for one.
#
# Same shape as the run: xargs -P 3 over the real corpus, with the same lock
# key derivation. Any moment with two heavy ecosystems in flight is a failure.
set -uo pipefail
W=/home/ubuntu/sbomify-eval/.heavytest
rm -rf "$W"; mkdir -p "$W/eco" "$W/running"

cat > "$W/worker.sh" <<'WORKER'
#!/usr/bin/env bash
set -uo pipefail
W=/home/ubuntu/sbomify-eval/.heavytest
_HEAVY=" java kotlin scala android clojure "
eco=$1; slug=$2
key=$eco
[[ $_HEAVY == *" $eco "* ]] && key=_heavy
held=""
for _t in $(seq 1 200); do
  if mkdir "$W/eco/$key.lock" 2>/dev/null; then held=1; break; fi
  sleep 0.05
done
[ -z "$held" ] && { echo "GAVEUP $eco" >> "$W/log"; exit 0; }
trap 'rm -f "$W/running/$$"; rmdir "$W/eco/$key.lock" 2>/dev/null' EXIT

# Record what class of work this is, so two heavy jobs are detectable.
class=other
[[ $_HEAVY == *" $eco "* ]] && class=HEAVY
printf '%s %s\n' "$class" "$eco" > "$W/running/$$"

snap=$(cat "$W/running"/* 2>/dev/null | tr '\n' '|')
heavy_now=$(cat "$W/running"/* 2>/dev/null | grep -c '^HEAVY' || true)
[ "$heavy_now" -gt 1 ] && echo "$heavy_now heavy: $snap" >> "$W/violations"
cat "$W/running"/* 2>/dev/null | awk '{print $2}' | sort | uniq -d >> "$W/dupes"
sleep 0.12
WORKER
chmod +x "$W/worker.sh"

: > "$W/violations"; : > "$W/dupes"; : > "$W/log"
head -200 /home/ubuntu/sbomify-eval/projects_v5.tsv \
  | cut -f1,2 | tr '\t\n' '\0\0' \
  | xargs -0 -P 3 -n 2 "$W/worker.sh"

v=$(grep -c . "$W/violations" 2>/dev/null || true)
d=$(sort -u "$W/dupes" 2>/dev/null | grep -c . || true)
echo "moments with >1 heavy build:       $v"
echo "moments with a duplicate ecosystem: $d"
if [ "$v" -eq 0 ] && [ "$d" -eq 0 ]; then
  echo "PASS: at most one heavy build, and never two of one ecosystem"
else
  echo "FAIL"; head -3 "$W/violations" "$W/dupes" 2>/dev/null
fi
rm -rf "$W"
