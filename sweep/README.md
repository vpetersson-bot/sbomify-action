# Corpus sweep harness

Tooling for running sbomify-action against a large corpus of real open-source
repositories, to find out where it does badly and why.

This is research tooling, not product code. It lives on a branch deliberately.

## Layout

```
sweep/
  scripts/          the harness and every analysis script written for it
  baseline/v5-meta/ 500 records from the v5 sweep -- the comparison baseline
  state/            work lists, plus v6-meta (the run in progress)
```

## The run currently in progress (v6)

A **regression** run: the worst 200 projects of the 500, replayed against a
newer image. Every input is held constant -- same release tags, same
`LOCK_FILE` targets, same environment -- so any difference is attributable to
the image and nothing else.

| | |
|---|---:|
| image | `sbomifyhub/sbomify-action@sha256:042ba7e9325256551af8ec8e0f96588df3dde2e97dcbaf997640217a02ea2e41` |
| which is | `26.7.0+af0579d` |
| corpus | `state/replay200.tsv` (200 projects) |
| done | 24 / 200 |

Composition of the 200, by what the user got from v5: 94 no runs, 48 crashed,
46 empty documents, 11 tooling subject, 1 inferred versions.

### Resume on a new machine

```sh
git clone <repo> && git checkout eval/sweep-harness      # this branch
mkdir -p ~/sbomify-eval/v6
cp -r sweep/scripts/*      ~/sbomify-eval/
cp    sweep/state/*.tsv    ~/sbomify-eval/
cp -r sweep/state/v6-meta  ~/sbomify-eval/v6/meta        # keeps the 24 done
cp -r sweep/baseline/v5-meta ~/sbomify-eval/v5-meta      # for comparison

# Discard the two records poisoned by a harness mistake (see below).
xargs -I{} rm -f ~/sbomify-eval/v6/meta/{}.json < sweep/state/v6-invalidate.txt

cd ~/sbomify-eval
OUT_ROOT=$HOME/sbomify-eval/v6 \
IMAGE=sbomifyhub/sbomify-action@sha256:042ba7e9325256551af8ec8e0f96588df3dde2e97dcbaf997640217a02ea2e41 \
WORKERS=2 MEM=2g RUN_TIMEOUT=900 ./orchestrate_replay.sh
```

Resume is idempotent: a project with a populated record is skipped, so
re-running only does what is left. Pin the digest rather than using `:latest`
-- concurrent merges race on that tag, and a sweep that silently spans two
images cannot be compared against anything.

Scale `WORKERS` to the machine. The box this ran on had 15G shared with other
work; an uncapped sweep there OOM-killed the session driving it. Every
container is memory-capped and `--oom-score-adj=1000` so a runaway generator
dies before the host does.

## Two traps worth knowing before you touch this

**Containers run as root, so the host user cannot clean up after them.**
`rm -rf` on a work directory or cache returns *exit 0 having deleted nothing*.
That silent no-op is how 64G of unreachable cache accumulated under
`v5/slots`. `replay_one.sh` falls back to `sudo -n rm -rf`, which fails loudly
on a box without passwordless sudo rather than quietly filling the disk.

**Never let the harness restate a product decision.** Three findings from the
v5 sweep turned out to be the harness's own fault, because it kept copies of
logic that then drifted:

- it re-implemented the wizard's lockfile priority table, truncated at Rust,
  and described a Swift package as `pkg:gem/workspace@latest`
- it cloned default branches, when the action is tag-triggered
- it passed `COMPONENT_NAME="$(basename $slug)"`, which named every document
  after its repository -- producing the "203-component SBOM named
  rabbitmq-server describing Selenium" finding. The product would have called
  that component `rabbitmq-server-selenium-javascript`, which is honest. A
  whole ecosystem-veto feature was built on that finding and had to be
  reverted.

`replay_one.sh` is deliberately thin for this reason: the targets are already
recorded, so it chooses nothing. `inspect_sbom_v2.py` is reused verbatim as
the summariser rather than restating what "good" means.

Note that `COMPONENT_NAME` is *still* passed, on purpose -- changing an input
would make diffs unattributable to the image. The cost is that **this run
cannot see naming defects**; those need a separate pass.

## `state/v6-invalidate.txt`

`airbytehq_airbyte` and `dart-lang_http` were in flight when leaked work
directories were cleared without excluding running projects. Their bind-mounted
clone vanished mid-run, so their records are harness artifacts, not results.
Delete and re-run them before any analysis, or they read as regressions the
image did not cause.

## Key scripts

| script | what it does |
|---|---|
| `orchestrate_replay.sh` | worker pool over `replay200.tsv`, resume-safe |
| `replay_one.sh` | one project: clone at ref, strict + fallback run, record |
| `inspect_sbom_v2.py` | scores one SBOM into a flat record (the summariser) |
| `pick_worst_200.py` | ranks the 500 by how badly they were served |
| `build_replay_list.py` | joins the worst-200 with their refs and targets |
| `watch_v6.sh` | progress monitor; reports stop-early and low-disk too |
| `run_one_v5.sh` / `orchestrate_v5.sh` | the original full-corpus sweep |

The remaining scripts are one-off analyses kept for provenance -- they are how
individual findings were reached, and several encode a correction to an
earlier wrong answer.
