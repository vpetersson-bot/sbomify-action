# arm64 sweep — 500 projects, `26.7.0+af0579d`

Ran the full 500-repository corpus on `aarch64`
(`sbomifyhub/sbomify-action@sha256:042ba7e9325256551af8ec8e0f96588df3dde2e97dcbaf997640217a02ea2e41`),
a platform that had never been swept. Results in `results/arm64-meta/`.

## The answer on arm64

**Healthy.** Zero unhandled exceptions across 500 projects, and zero failures
across the 49 projects whose input was a real lock file — `requirements.txt`,
`uv.lock`, `go.sum`, `mix.lock`, `yarn.lock`, `pnpm-lock.yaml`.

**Zero confirmed arm64-specific defects.** Twenty-nine candidates were flagged
and all twenty-nine dissolved on inspection.

## What the candidates actually were

| flagged | actual cause |
| ------- | ------------ |
| ~44 Maven / sbt projects | **HTTP 429** from `repo.maven.apache.org` — six parallel workers rate-limiting themselves |
| 26 projects | Maven wrapper jar absent from the repository |
| 5 Gradle projects | the harness's `--memory=2g` OOM-killing the Gradle daemon |
| 9 `Package.swift` | the **correct** refusal, with working remediation advice |
| Alamofire, RxSwift | the amd64 *baseline* was wrong — fastlane `Gemfile.lock` |

## Real defects found

Three, all filed, all reproducing on **amd64 as well** — so product defects,
not platform ones. None was surfaced by the harness's own output; all three
came from reading logs by hand.

- [#382](https://github.com/sbomify/sbomify-action/issues/382) — the injected
  cyclonedx-gradle plugin breaks Gradle dependency verification. The init
  script puts our artifacts on the build `classpath`, which the project's
  `verification-metadata.xml` cannot cover by construction.
  `JetBrains/kotlin`, `elastic/elasticsearch`.
- [#383](https://github.com/sbomify/sbomify-action/issues/383) — no JDK is
  provisioned for a project's requested Gradle toolchain, and no toolchain
  resolver is configured, so Gradle cannot fetch one either.
  `ReactiveX/RxJava`, `google/ksp`.
- [#384](https://github.com/sbomify/sbomify-action/issues/384) — exit 0 and a
  schema-valid SBOM with zero components, from a real lock file.
  `OpenAPITools/openapi-generator`. Worse than crashing: an empty SBOM does not
  read as "generation failed", it reads as "this project has no dependencies".

## The result that matters more than the arm64 answer

**Eight harness bugs, zero product bugs found by the harness.**

Every single thing the measurement apparatus flagged as a product defect was a
defect in the measurement:

1. summariser referenced by absolute path — recorded `null` for every SBOM
   while every run reported success
2. disk guard read a nonexistent home directory — every project aborted with
   "only G free"
3. orchestrator and watcher hardcoded to one machine
4. `--memory=2g` fabricated an architecture defect out of every JVM project
5. six workers rate-limited themselves into 44 HTTP 429s
6. the v5 baseline was treated as ground truth while containing the old
   harness's known-bad records
7. `scp`-ing a fixed script over a live sweep corrupted six workers mid-parse
   (bash reads scripts incrementally)
8. clearing leaked work directories without excluding in-flight projects

The lesson is not "be careful". It is that a harness artifact and a product
defect are *indistinguishable in the results*, so any finding must first be
attacked as a harness bug and only believed once that fails.

## Not done

The 44 rate-limited projects were not re-run. Doing it properly needs low
concurrency or a local Maven mirror, and would take hours. Until then the JVM
picture on arm64 is unmeasured — not bad, unmeasured.

`COMPONENT_NAME` was passed throughout, so **this sweep cannot see naming
defects**. That needs its own pass.
