#!/usr/bin/env bash
# Does the one-job-per-ecosystem rule actually hold?
#
# Asserting it in a comment is not the same as observing it. This runs a stub
# worker with the same locking as run_one_v5.sh under the real orchestrator
# pattern -- xargs -P 3 over the interleaved corpus -- and records the ecosystem
# of every concurrently running job. Any moment with two of the same ecosystem
# in flight is a failure.
set -uo pipefail
W=/home/ubuntu/sbomify-eval/.ecotest
rm -rf "$W"; mkdir -p "$W/eco" "$W/running"

cat > "$W/worker.sh" <<'WORKER'
#!/usr/bin/env bash
set -uo pipefail
W=/home/ubuntu/sbomify-eval/.ecotest
eco=$1; slug=$2
eco_held=""
for _try in $(seq 1 100); do
  if mkdir "$W/eco/$eco.lock" 2>/dev/null; then eco_held=1; break; fi
  sleep 0.05
done
[ -z "$eco_held" ] && { echo "GAVEUP $eco $slug" >> "$W/log"; exit 0; }
trap 'rm -f "$W/running/$$"; rmdir "$W/eco/$eco.lock" 2>/dev/null' EXIT

echo "$eco" > "$W/running/$$"
# Observe every ecosystem in flight at this instant, including our own.
cat "$W/running"/* 2>/dev/null | sort | uniq -d >> "$W/dupes"
sleep 0.15
WORKER
chmod +x "$W/worker.sh"

: > "$W/dupes"; : > "$W/log"
head -120 /home/ubuntu/sbomify-eval/projects_v5.tsv \
  | cut -f1,2 \
  | tr '\t\n' '\0\0' \
  | xargs -0 -P 3 -n 2 "$W/worker.sh"

dupes=$(sort -u "$W/dupes" 2>/dev/null | grep -c . || true)
gaveup=$(grep -c GAVEUP "$W/log" 2>/dev/null || true)
echo "concurrent same-ecosystem observations: $dupes"
echo "workers that gave up waiting:           $gaveup"
[ "$dupes" -eq 0 ] && echo "PASS: never two of one ecosystem at once" || {
  echo "FAIL: saw these doubled up:"; sort -u "$W/dupes"; }
rm -rf "$W"
