# llm-energy-bench

Research tool for measuring local LLM inference performance, GPU energy use, and approximate cost.

The project starts as a small experimental bench, not as a production monitoring platform. Its first goal is to check whether energy-aware metrics change the engineering choice of local LLM configuration compared with speed-only benchmarks.

## Initial Research Question

Does the preferred local LLM configuration change when comparing models, quantization modes, context lengths, and GPUs by:

- latency;
- tokens per second;
- GPU energy per request;
- tokens per joule;
- approximate cost per 1M tokens?

## Current State

The repository now contains the tested building blocks for the MVP:

- a Python 3.12 package and CLI shell with `doctor`, `run`, and `report`
  subcommands;
- strict TOML configuration and JSONL prompt contracts;
- the six-prompt RTX 3050 pilot protocol;
- immutable JSON/JSONL/gzip result storage, checksums, privacy checks, and
  basic run validation;
- an Ollama client for inventory, preload, placement checks, streaming
  generation, TTFT, token counts, and runtime durations;
- an NVML capability probe and request-scoped telemetry sampler with explicit
  fallbacks for consumer GPUs;
- a deterministic warm-run experiment orchestrator with immediate raw-record
  persistence and semantic validation;
- human/JSON environment diagnosis plus CSV and Markdown aggregate reports;
- a frozen 24-prompt, four-configuration `benchmark-v1` protocol for the two
  main GPU hosts;
- Windows and Linux CI plus 230 hardware-independent tests.

The software path is complete through Task 7 of the implementation plan. It
has not yet produced a hardware-validated experimental run; Task 8 is the
first pilot on a real NVIDIA GPU and remains a separate acceptance gate. Task
9 protocol preparation is complete, but it does not bypass that gate.

A real-NVML smoke check has succeeded on the RTX 3050 Laptop host. Its driver
reports an implausible total-energy counter, and the per-request source sanity
check correctly selects instantaneous-power integration instead. Ollama and
the pilot model are not installed yet, so this is telemetry validation rather
than a completed inference experiment.

## Minimal Scope

- Run fixed prompt sets against local inference runtimes.
- Collect runtime metrics such as latency and token counts.
- Sample NVIDIA GPU telemetry through NVML.
- Save raw runs and derived metrics.
- Generate reproducible Markdown and CSV tables for comparison.

## Non-Goals

- Datacenter orchestration.
- Production monitoring.
- Automatic optimization claims without experiments.
- Universal conclusions about all LLM deployments.

## Repository Structure

- `src/llm_energy_bench/` - CLI, config, Ollama, NVML, and result contracts.
- `configs/` - reproducible experiment configurations.
- `prompts/` - versioned prompt sets.
- `tests/` - hardware-independent contract and failure-path tests.
- `experiments/` - future validated run artifacts and logs.
- `docs/` - research protocol, design, and implementation plan.

## Development Setup

```text
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m ruff check .
.venv\Scripts\python -m pytest -v
```

On Linux or macOS, replace `.venv\Scripts\python` with
`.venv/bin/python`. Ollama and an NVIDIA driver are not required for the test
suite because the runtime and NVML boundaries use fakes.

The checked-in pilot is intentionally small: one
`llama3.2:3b-instruct-q4_K_M` configuration, six prompts, two excluded
warm-ups, and three measured repetitions (18 measured requests).

## CLI

```text
python -m llm_energy_bench doctor --json
python -m llm_energy_bench run --config configs/pilot.toml
python -m llm_energy_bench report experiments/runs/<run-id>
```

`doctor` is read-only: it checks the configured Ollama instance, NVML energy
source, installed model digests, and complete GPU placement. `run` never pulls
models automatically. `report` regenerates derived CSV/Markdown summaries from
the raw artifacts and returns exit code 4 if any supplied run fails validation.
The nominal NVML source shown by `doctor` is revalidated for every request;
physically inconsistent total-energy counters fall back to power integration
and the selected source is stored in the request record.

## Project Documents

- [Current project status](STATUS.md)
- [Approved MVP design](docs/superpowers/specs/2026-09-19-llm-energy-bench-design.md)
- [MVP implementation plan](docs/superpowers/plans/2026-09-19-llm-energy-bench-mvp.md)
- [Initial research plan](docs/research-plan.md)
- [Append-only experiment log](docs/experiment-log.md)
