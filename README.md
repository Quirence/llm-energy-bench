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
- Windows and Linux CI plus 189 hardware-independent tests.

The components are not wired into an end-to-end benchmark yet. The three CLI
commands deliberately return a not-implemented environment error until the
experiment runner, doctor output, aggregation, and report generation are
completed in Tasks 6 and 7 of the implementation plan.

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
warm-ups, and three measured repetitions (18 measured requests when the runner
is implemented).

## Project Documents

- [Current project status](STATUS.md)
- [Approved MVP design](docs/superpowers/specs/2026-09-19-llm-energy-bench-design.md)
- [MVP implementation plan](docs/superpowers/plans/2026-09-19-llm-energy-bench-mvp.md)
- [Initial research plan](docs/research-plan.md)
