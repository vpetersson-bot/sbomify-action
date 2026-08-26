# arm64 sweep — 500 projects, `26.7.0+af0579d`

Ran the full 500-repository corpus on `aarch64`
(`sbomifyhub/sbomify-action@sha256:042ba7e9325256551af8ec8e0f96588df3dde2e97dcbaf997640217a02ea2e41`),
a platform that had never been swept. Results in `results/arm64-meta/`.

## The answer on arm64

**Healthy.** Zero unhandled exceptions across 500 projects, and zero failures
across the 49 projects whose input was a real lock file — `requirements.txt`,
`uv.lock`, `go.sum`, `mix.lock`, `yarn.lock`, `pnpm-lock.yaml`.

**One confirmed arm64-specific defect**, found only after the confounds were
removed — see the correction below. Twenty-eight of the twenty-nine flagged
candidates dissolved on inspection; the twenty-ninth was real.

## What the candidates actually were

| flagged | actual cause |
| ------- | ------------ |
| ~44 Maven / sbt projects | **HTTP 429** from `repo.maven.apache.org` — six parallel workers rate-limiting themselves |
| 26 projects | Maven wrapper jar absent from the repository |
| 5 Gradle projects | the harness's `--memory=2g` OOM-killing the Gradle daemon |
| 9 `Package.swift` | the **correct** refusal, with working remediation advice |
| Alamofire, RxSwift | the amd64 *baseline* was wrong — fastlane `Gemfile.lock` |

## Correction: there is one arm64 defect

This document first said "zero confirmed arm64-specific defects". That was
wrong, and the way it was wrong is worth keeping.

`ktorio/ktor` fails on aarch64 with `Unknown host target: linux aarch64`, and
produces 1100 components on amd64 with a correct `pkg:maven/io.ktor/ktor@3.5.2`
root — a baseline that passes the trustworthiness filter. It is a genuine
architecture-specific failure, filed as
[#387](https://github.com/sbomify/sbomify-action/issues/387).

It was invisible in the first pass because ktor was one of the projects the
sweep's own concurrency had rate-limited. Removing a confound does not only
retract false findings; it also *reveals* true ones that the noise was hiding.
The "zero defects" conclusion was drawn while 22 projects were still
unmeasured, and stating it that confidently was the error — not the arithmetic.

The nine projects that remained empty after the low-concurrency re-run each
had a distinct, identifiable cause. None was noise.

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
  `OpenAPITools/openapi-generator`, and `yesodweb/yesod` via `stack.yaml.lock`
  — two ecosystems, so not a JavaScript quirk. Worse than crashing: an empty
  SBOM does not read as "generation failed", it reads as "this project has no
  dependencies".
- [#387](https://github.com/sbomify/sbomify-action/issues/387) — Kotlin
  Multiplatform cannot be scanned on aarch64. The one architecture-specific
  finding. Originates in ktor's own KMP build, so arguably upstream's, but the
  user cannot tell that from the output and arm64 runners are now normal.
- [#388](https://github.com/sbomify/sbomify-action/issues/388) — a single
  Android module fails the whole Gradle build, because the image ships no
  Android SDK. `grpc/grpc-java` is mostly plain JVM and none of it is scanned
  because of `:grpc-cronet`. `fmtlib/fmt` reached the same failure for a
  second reason worth separating: it is a **C++** project whose selected input
  was `support/build.gradle`, i.e. its tooling rather than what it ships.

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

## The rate-limited re-run

Done, at 2 workers instead of 6. Of the 44 projects that hit a 429, only 22
were also empty — the rest were slowed, not blocked. Re-running those 22
recovered **13**, including quarkus (2189 components), elasticsearch (1984),
keycloak (914) and debezium (799). 429s fell from 22 projects to 3.

So those empty results were the sweep throttling itself, not the product. The
nine that stayed empty are triaged in the table above.

## Not done

`COMPONENT_NAME` was passed throughout, so **this sweep cannot see naming
defects**. That needs its own pass.

`http4s/http4s` is untriaged: an sbt launcher `NoSuchElementException: key not
found: (1,0)`. Not filed, because I could not tell whether it is ours or
sbt's, and a guess would be worse than an admission.

`COMPONENT_NAME` was passed throughout, so **this sweep cannot see naming
defects**. That needs its own pass.
