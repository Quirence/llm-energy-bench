# Collaboration and Workstreams

This document is the starting point for contributors. It assigns stable areas
of responsibility without creating separate implementations or changing the
frozen research protocol.

## Sources of Truth

- `STATUS.md` is the current project snapshot and names the next acceptance
  gate.
- GitHub Issues contain active work, owners, blockers, and acceptance criteria.
- `docs/experiment-log.md` is the append-only index of environment probes and
  validated hardware runs.
- `docs/research-plan.md` and the approved design define the methodology.
- Pull requests and Git history record reviewed implementation decisions.

Do not report an environment probe as a validated experimental run. Do not
change the model matrix, prompt set, metric definitions, or validity gates only
to improve a result.

## Current Owners

| Contributor | Primary responsibility | Active work |
| --- | --- | --- |
| `@Quirence` | runner, validation, reporting, methodology, RTX 3050 pilot and RTX 5060 baseline | [Issues #3, #4, and #6](https://github.com/Quirence/llm-energy-bench/issues?q=is%3Aissue+is%3Aopen+assignee%3AQuirence) |
| `@Qcsteeven` | NVML capability probing, telemetry lifecycle, energy-source fallback, RTX 4060 desktop study | [Issue #5](https://github.com/Quirence/llm-energy-bench/issues/5) and [Issue #6](https://github.com/Quirence/llm-energy-bench/issues/6) |
| `@Skipl1` (Dimas) | Ollama preload/inventory, streaming generation, TTFT, model digest and GPU-placement checks | [Issue #7](https://github.com/Quirence/llm-energy-bench/issues/7) |

CODEOWNERS reflects the module ownership. Shared schemas and methodology still
require cross-review; ownership does not permit unilateral protocol changes.

## Starting Work

For a new clone:

```text
git clone https://github.com/Quirence/llm-energy-bench.git
cd llm-energy-bench
git switch main
git pull --ff-only
python -m venv .venv
.venv\Scripts\python -m pip install ".[dev]"
.venv\Scripts\python -m pytest -q
```

On Linux, replace `.venv\Scripts\python` with `.venv/bin/python`.
The regular install is deliberate on Windows: Python 3.12 may decode an
editable install's UTF-8 `.pth` using the local code page when the repository
path contains non-ASCII characters. Reinstall the package after changing code;
pytest imports the current `src/` tree directly.

Before editing, open the assigned Issue and create a branch from current
`main`:

```text
git switch main
git pull --ff-only
git switch -c feat/<issue-number>-<short-name>
```

Examples are `feat/5-rtx4060-study` and
`feat/7-ollama-runtime-validation`. Never develop directly on `main`.

## Pull Request Contract

Every pull request must:

1. link its Issue and state which acceptance criteria it satisfies;
2. include focused tests for changed behavior and run the full test suite;
3. preserve raw failures instead of silently substituting successful values;
4. update `STATUS.md` only when the reported state is already verified;
5. update `docs/experiment-log.md` for a real probe or run;
6. avoid usernames, home paths, tokens, serial numbers, and raw GPU UUIDs;
7. obtain the required approval and pass both Windows and Linux CI checks.

Changes to config schemas, manifest fields, validity rules, prompt sets, model
tags, or research methodology require review from another contributor before
merge.

## Dimas: Ollama Workstream

Dimas starts from [Issue #7](https://github.com/Quirence/llm-energy-bench/issues/7)
and treats `src/llm_energy_bench/ollama.py` plus `tests/test_ollama.py` as his
primary boundary. The workstream covers:

- model inventory, preload, resolved digest, and complete GPU placement;
- streaming response parsing, TTFT, token counts, and runtime durations;
- timeouts, premature disconnects, final chunks without output, and partial
  failure preservation;
- read-only `doctor` support and evidence needed by the measured pilot.

The CLI must never pull a model automatically. A missing model is a preflight
error. Dimas should coordinate before changing shared request/result schemas,
the frozen model tags, prompt files, or benchmark configuration.

## Hardware Coordination

The final RTX 4060 run must use the same committed config, prompt hash, Ollama
version, and model digests as the RTX 5060 run. Contributors may prepare a host
and run `doctor` earlier, but a result is comparable only after these inputs are
frozen and recorded. Invalid requests remain in raw artifacts with explicit
reasons and are excluded from primary aggregates.
