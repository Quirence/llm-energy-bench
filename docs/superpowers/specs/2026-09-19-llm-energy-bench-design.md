# llm-energy-bench MVP Design

Status: approved for implementation planning on 2026-09-19.

## Purpose

`llm-energy-bench` is a small research CLI for reproducible measurement of
local LLM inference. It tests whether an engineering choice based on latency
or throughput changes when GPU energy metrics are included.

The project is not a monitoring platform, a datacenter product, or a claim
that energy-aware ranking must differ. A negative result is valid: if speed
and energy rankings consistently agree within measurement uncertainty, the
research hypothesis is not supported in the tested scope.

## Research Scope

The primary comparison covers two Windows hosts:

- MAIBENBEN X16C with RTX 5060 Laptop GPU as the main development and
  experiment host;
- RTX 4060 desktop as the second host.

The currently available RTX 3050 Laptop GPU is used only for a technical
smoke run. It is not part of the main research conclusions.

The initial runtime is Ollama. llama.cpp may be added only after a validated
Ollama pilot. vLLM, web dashboards, databases, FastAPI, Django, and external
wall-meter synchronization are outside the MVP.

## Fixed Model Matrix

The main two-host experiment uses exactly these Ollama tags:

- `qwen3:4b-instruct-2507-q4_K_M`;
- `qwen3:4b-instruct-2507-q8_0`;
- `llama3.2:3b-instruct-q4_K_M`;
- `llama3.2:3b-instruct-q8_0`.

The RTX 3050 smoke run uses only
`llama3.2:3b-instruct-q4_K_M`. Every run records the resolved model digest;
model tags alone are not considered sufficient identifiers.

## CLI and Component Boundaries

The package targets Python 3.12 and exposes three commands:

```text
python -m llm_energy_bench doctor [--json]
python -m llm_energy_bench run --config <experiment.toml>
python -m llm_energy_bench report <run-dir> [<run-dir> ...]
```

The required modules are:

- `cli`: command parsing, user-facing errors, and exit codes;
- `config`: TOML and prompt JSONL loading with explicit dataclass validation;
- `ollama`: model preloading, placement inspection, streaming inference, TTFT,
  and runtime metrics;
- `nvml`: capability probing and request-scoped telemetry sampling;
- `runner`: preflight, warm-up, deterministic ordering, repetitions, and
  lifecycle coordination;
- `results`: immutable raw artifacts, validation, aggregation, and reports.

There is no plugin registry in the MVP. A formal runtime adapter protocol is
introduced only when the second runtime is implemented.

Runtime dependencies are limited to `httpx` and `nvidia-ml-py`. TOML, JSON,
JSONL, gzip, hashing, CLI parsing, and dataclasses use the Python standard
library. `pytest` and `ruff` are development-only dependencies.

## Experiment Flow

For each experiment the runner:

1. Loads and validates the TOML config and prompt set.
2. Hashes the resolved config and prompt set.
3. Probes Ollama, the GPU, NVML capabilities, and model placement.
4. Rejects missing models and partial CPU offload instead of pulling models
   or silently changing the workload.
5. Preloads each model and performs two excluded warm-up requests.
6. Executes measured prompts in a deterministic shuffled order.
7. Starts telemetry before each request and stops it after the final response
   chunk.
8. Writes raw records immediately so interrupted runs remain auditable.
9. Validates the completed artifacts and generates derived reports.

Interrupted or failed runs are preserved with an explicit status. They are
never resumed in place; a retry receives a new run identifier.

## Reproducibility Controls

Default experiment controls are:

```text
num_ctx = 4096
temperature = 0
seed = 42
concurrency = 1
kv_cache = f16
warmup_requests = 2
telemetry_interval_ms = 100
```

The manifest records OS, GPU name, hashed GPU fingerprint, VRAM, driver,
runtime version, model digest, quantization, context settings, prompt-set
hash, ordering seed, power limits, temperature, and telemetry capabilities.

Public artifacts must not contain Windows usernames, home-directory paths,
serial numbers, access tokens, or raw GPU UUIDs.

## Raw and Derived Data

Each run directory contains:

```text
manifest.json
config.resolved.toml
requests.jsonl
outputs.jsonl
telemetry.jsonl.gz
validation.json
summary.csv
report.md
```

All run artifacts are versioned in Git. Telemetry is gzip-compressed, model
weights are never committed, and validation rejects any single artifact over
25 MB.

Raw request and telemetry data are authoritative. Reports are derived and may
be regenerated without repeating inference.

## Metrics

Required request metrics are:

- end-to-end latency and TTFT;
- Ollama total, load, prompt-evaluation, and evaluation durations;
- prompt, cached-prompt, and output token counts;
- prefill, decode, and end-to-end output throughput;
- average and maximum observed GPU power;
- GPU energy per request;
- joules per output token and output tokens per joule;
- GPU-only electricity cost per one million output tokens;
- start/maximum temperature, power limit, and start/peak VRAM.

Energy uses the best supported source in this order: total-energy counter,
instantaneous-power integration, legacy-power integration. The source and
fallback reason are stored with every request.

Support is necessary but not sufficient for the total-energy counter. Each
request checks that its counter delta is positive, does not imply average
power above 120% of the enforced limit, and stays within a factor of two of an
available power integral. A failed check selects the next usable source and
records the reason; it never silently publishes the inconsistent counter.

An electricity tariff is optional. Without an explicit tariff and currency,
cost fields are `null`. Any reported cost is labelled as a GPU-only estimate,
not whole-system energy or total cost of ownership.

## Analysis Rules

Reports use median and IQR plus aggregate ratios such as total tokens divided
by total time or total energy. They do not average per-request ratios.

Scored prompts are weighted equally: first aggregate repetitions within each
prompt, then aggregate prompts. A configuration enters the engineering
ranking only if its quality score is at least 75%.

A rank inversion is material only when its effect is at least
`max(5%, 3 × repeatability CV)` and its bootstrap 95% confidence interval does
not cross zero. If speed and energy select the same top configuration in at
least 90% of workload blocks and no material inversion exists, the hypothesis
is reported as unsupported in the tested scope.

## Collaboration and Reporting

The public repository is owned by `Quirence`; `Qcsteeven` is a direct
collaborator. Work follows Issue → feature branch → pull request → review.

Quirence owns the initial config, Ollama, runner, storage, and report path.
Qcsteeven owns the independent NVML probe and telemetry sampler. Changes to
the data schema or experimental methodology require review by the other
author.

`STATUS.md` is the concise current-state document. Completed experiments are
appended to `docs/experiment-log.md` once experimental work begins.
