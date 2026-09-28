# Pilot Baseline and GPU Handoff

This document becomes operational only after the stabilization pull request is
merged and its merge commit is tagged `pilot-v1-code`. Until then contributors
may run `doctor`, but must not publish experimental artifacts.

## Frozen inputs

- Python: 3.12
- Runtime: Ollama 0.34.2
- Model: `llama3.2:3b-instruct-q4_K_M`
- Required digest:
  `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`
- Context: 4096; temperature: 0; seed: 42; concurrency: 1
- Warm-ups: 4 (one cold exclusion plus three floor probes); measured repetitions: 3
- Prompt set: `prompts/pilot-v1.jsonl` at the hash recorded in each manifest
- Placement: `fully_on_gpu == true` and `gpu_fraction == 1.0`

## Synchronize

Do not discard local changes. Commit or stash them first, then run:

```text
git fetch origin --prune --tags
git switch main
git pull --ff-only origin main
git tag --points-at HEAD
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install ".[dev]"
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m ruff format --check .
.venv\Scripts\python -m pytest -q
ollama --version
```

On Windows, use a short ASCII checkout path such as `C:\src\llm-energy-bench`.
Deep worktree paths can exceed the legacy path limit while an atomic temporary
artifact is being written even when the final run-directory name itself fits.

`git tag --points-at HEAD` must include `pilot-v1-code`, and Ollama must report
0.34.2. Do not continue with a different commit or runtime version.

Pull the model manually if necessary. The benchmark never downloads weights:

```text
ollama pull llama3.2:3b-instruct-q4_K_M
```

Before every independent launch, keep the machine on AC power, use the same
documented OS/performance and cooling profile, close avoidable GPU workloads,
and let the GPU return to a stable idle state. Record any unavoidable change
in `docs/experiment-log.md`; never hide it by editing raw artifacts. A safe
hardware identity check that does not expose GPU UUIDs is:

```text
nvidia-smi --query-gpu=name,driver_version,memory.total,power.limit --format=csv,noheader
```

## Host assignments

| Contributor | Host | Config | Result branch |
| --- | --- | --- | --- |
| Quirence | RTX 5060 Laptop | `configs/pilot-rtx5060.toml` | `experiment/rtx5060-pilot-v1` |
| Qcsteeven | RTX 4060 Ti desktop | `configs/pilot-rtx4060ti.toml` | `experiment/rtx4060ti-pilot-v1` |
| Skipl1 | GTX 1080 | `configs/pilot-gtx1080-observation.toml` | `experiment/gtx1080-observation` |

## Preflight and run

Use the host's committed config in both commands:

```text
.venv\Scripts\python -m llm_energy_bench doctor --config configs/pilot-rtx5060.toml --json
.venv\Scripts\python -m llm_energy_bench run --config configs/pilot-rtx5060.toml
```

Qcsteeven substitutes `configs/pilot-rtx4060ti.toml`; Skipl1 uses
`configs/pilot-gtx1080-observation.toml`. A run is acceptable only
when `doctor` confirms the frozen runtime, digest and full placement, the CLI
returns success, `validation.json` reports `ok: true`, and all 18 measured
requests are valid. Raw output must retain the energy source and any fallback
reason for every request. The four raw warm-up records must support the
manifest floor, cached-token excess must be at most one, and no measured
`load_duration` may exceed 100 ms. Warm-ups two through four must also stay at
or below 100 ms so the cache floor cannot be established across a model reload.

The RTX 5060 and RTX 4060 Ti runs are primary pilot data. The GTX 1080 run is
observation-only even when it passes the same technical validation; it cannot
be silently added to the primary decision blocks.

After the first valid run, each primary host repeats the exact command twice
more as independent launches. These three run directories provide the
pre-registered repeatability CV. Do not change the environment between them.
Run and validate one launch at a time; do not use a loop that continues after
a failure. GTX 1080 produces one required observation launch and may repeat it
only when explicitly labelled as observation repeatability.

Create the assigned result branch from the tag before adding artifacts. Run
exactly one of these commands:

```text
git switch -c experiment/rtx5060-pilot-v1 pilot-v1-code
git switch -c experiment/rtx4060ti-pilot-v1 pilot-v1-code
git switch -c experiment/gtx1080-observation pilot-v1-code
```

Then add only the run artifacts and append-only log entry:

```text
git add experiments/runs/<run-id> docs/experiment-log.md
git commit -m "data: add <host> pilot-v1 run"
git push -u origin experiment/<host>-pilot-v1
```

Open a pull request and request review from another contributor. Do not change
code, prompts, configs or validity rules in a result PR. In the final push
command, use the exact branch created above (including the GTX 1080 observation
name). If any frozen input differs, preserve the local output for diagnosis
but do not publish it as a comparable run.
