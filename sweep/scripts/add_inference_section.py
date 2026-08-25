#!/usr/bin/env python3
"""Add the inference finding to the post, where it belongs in the argument.

The findings run in order of what is wrong with the document: the wrong
subject (curl), the wrong identity (thirty projects, five purls), then the
wrong versions, then no content at all. The inference finding is the third and
was written after the post, so it goes between the identity one and the empty
one rather than at the end.
"""

import pathlib

POST = pathlib.Path(
    "/home/ubuntu/code/sbomify.com/.claude/worktrees/blog-500-projects/"
    "content/posts/2026-08-10-500-open-source-projects.md"
)

SECTION = """### A quarter of the SBOMs described today, not what the project ships

This is the one we would most want a reader to check in their own output.

A lock file records the versions a project committed to. A manifest — `composer.json`, `pyproject.toml`, `package.json` — records the versions it would _accept_. When only the manifest is committed, the resolver picks from whatever the registry offers at that moment, and the resulting document describes the day it was generated.

**104 of 405 successful documents were built that way**, and not one of them said so.

`laravel/framework` commits no `composer.lock`. Its SBOM asserts 72 exact versions — `guzzlehttp/guzzle@7.15.3` and the rest — every one chosen during the run. Generate it tomorrow and they differ. The application that installs Laravel resolves its own tree and differs again. Nothing in the file distinguishes that from a document describing a pinned, tested, shipped dependency set.

Worse, the document said where those versions came from, and was wrong:

```json
"evidence": {"identity": [{"concludedValue": "composer.lock", "confidence": 1.0}]}
```

There is no `composer.lock` in that repository. Composer created one to resolve, and it vanished with the container. So the SBOM cited a source its reader cannot inspect, at maximum confidence.

The fix is not to refuse. A resolved-today SBOM answers "what would I get if I installed this now", which is exactly the right question for vulnerability scanning. It is only harmful when it cannot be told apart from the other kind. So the document now says which it is, and — because "your versions were inferred" is a complaint rather than advice — what to run about it:

```
┌───────────────────────────────────────────────────────────────┐
│  THE VERSIONS IN THIS SBOM WERE INFERRED, NOT RECORDED        │
└───────────────────────────────────────────────────────────────┘

TO FIX THIS, run:
    composer update
then commit composer.lock and point LOCK_FILE at it.
```

`uv lock` for Python, `cargo generate-lockfile` for Rust, `swift package resolve` for Swift. Maven, Gradle and sbt have no lock file by convention, so they are told to generate the SBOM from the build instead of being pointed at a file that cannot exist. The notice and the remedy are written into the document as well as the log, because the person who later asks why the versions do not match production is reading the file, not the CI output.

Deciding which projects deserve the notice turned out to be the subtle part, and we got it wrong twice before getting it right. It cannot be done by filename. `go.mod` looks like a manifest and is not one: the format cannot express a range at all — Kubernetes has 207 requires, every one an exact version — and Go resolves deterministically, so a Go SBOM is reproducible. Meanwhile `requirements.txt` can hold `flask==3.1.0`, or `pytest>=2.8`, or a bare `flask`, and the filename is identical in all three cases. Both are now decided by reading the file. That correction alone withdrew the notice from eight projects — including opencv, redis and httpx — that had recorded their versions properly all along.

### JavaScript libraries produced nothing at all

The same manifest-without-a-lock-file situation, one step worse.

A JavaScript library gitignores its lock file, because the consuming application resolves it. So most libraries on GitHub arrive as a bare `package.json` — and the generator could not read one. Not badly: at all.

| Project | Runtime dependencies declared | Components |
| ------- | ----------------------------: | ---------: |
| eslint  | 30                            | **0**      |
| express | 28                            | **0**      |

Exit code zero, valid document, nothing in it. Resolving the manifest first — which takes under a second and downloads no packages — takes eslint to 133 components and express to 67, each with an exact version and a package URL. Those documents carry the notice above, because that is what they are.

"""

body = POST.read_text()
anchor = "### The silent empty document, still"
assert anchor in body, "insertion point not found"
POST.write_text(body.replace(anchor, SECTION + anchor, 1))
print("inference and JavaScript sections added")
