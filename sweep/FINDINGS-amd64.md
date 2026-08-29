# amd64 sweep — 478 repositories, `26.8.0+ed3f547`

The full corpus on x86_64 against the then-current master
(`sbomifyhub/sbomify-action@sha256:41729ea72ca388751bb472cb4cbf8601795d187cdf04efc00ce4319d2772078f`),
cold cache. Records in `results/amd64-meta/`.

478, not 500: the corpus contains 13 container images alongside the
repositories, and scanning an image is a different code path that needs its
own run rather than a guaranteed clone failure. Two projects failed to clone
for unrelated reasons.

## Result

**Zero unhandled exceptions. Zero regressions.**

One project produced components before and none now from the same input —
`square/retrofit` (`build.gradle`, was 197) — and that is the
`java14CompileClasspath` resolution failure already recorded on
[#383](https://github.com/sbomify/sbomify-action/issues/383), not something
new. Nothing regressed between the v5-era build and 26.8.0.

Rate limiting stayed negligible at 3 workers: 11 projects saw an HTTP 429 and
only **one** was actually blocked by it, against 44 seen / 22 blocked at 6
workers on the arm64 run. Three workers is the setting to keep.

## The regression list was wrong, 12 times out of 13

It first showed thirteen projects that "produced components before and produce
none now" — including `hasura/graphql-engine` at 424 → 0 from a real
`yarn.lock`, which would have been the most serious finding of the exercise.

Twelve of the thirteen were comparing **different inputs**.

`build_arm64_list.py` picks the *first* target v5 recorded for a project.
`baseline_components()` took the *best across all* v5 runs. When v5 tried
several inputs for one project, those are not the same question. hasura gave
it away on inspection: the 424 came from `cabal.project.freeze`, a Haskell
filesystem scan, and was being held against 0 from `yarn.lock`.

The fix makes the baseline match on target, and return `None` rather than `0`
when v5 never scanned that input — so "no comparison available" stays
distinguishable from "produced nothing", which is the distinction the original
version quietly destroyed.

## Two more harness bugs found here

**The clone rewrite.** This machine has a global
`url.git@github.com:.insteadOf https://github.com/`, so every clone became SSH
and `github.com:22` times out from here — 127 of 500 lost as "clone failed"
and silently skipped by triage.

The first fix was wrong: `git -c url."git@github.com:".insteadOf=` does *not*
clear it. `insteadOf` is multi-valued, so `-c` appends an empty entry and
leaves the original in force. It appeared to work because SSH intermittently
succeeds, and still lost 36 repositories. The correct fix asks for
`https://github.com:443/…` — `insteadOf` matches literal prefixes, so an
explicit port never matches, and nothing about the user's git config is
touched.

**The image filter.** `nginx:latest` and `postgres:17-alpine` carry no
registry prefix, so a `docker.io/` check missed them. A colon in the final
path segment is the reliable tell.

## Running total across both sweeps

**Twelve harness bugs, zero product bugs found by the harness.**

All five filed issues (#382, #383, #384, #387, #388) came from reading logs by
hand. Every finding the measurement itself produced was a defect in the
measurement — and the last two were caught only because the numbers looked
*too* interesting to accept.

That is the durable result of this exercise. A harness artifact and a product
defect are indistinguishable in the output, so the discipline that matters is
attacking every finding as a harness bug first and believing it only when that
fails. Twelve times that attack succeeded.
