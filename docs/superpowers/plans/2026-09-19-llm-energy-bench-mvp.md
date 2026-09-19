# llm-energy-bench MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible Python 3.12 CLI that measures warm Ollama
inference performance and NVIDIA GPU energy, preserves raw artifacts, and
compares speed-only and energy-aware rankings.

**Architecture:** A small config-driven CLI coordinates one Ollama client and
one NVML sampler. Raw JSONL telemetry and request records are immutable inputs
to validation and report generation. No server, database, dashboard, or plugin
framework is introduced.

**Tech Stack:** Python 3.12, standard library, httpx, nvidia-ml-py, pytest,
ruff, Ollama, NVIDIA NVML.

**Spec:** `docs/superpowers/specs/2026-09-19-llm-energy-bench-design.md`

## Global Constraints

- Production dependencies are limited to `httpx` and `nvidia-ml-py`.
- Public CLI commands are `doctor`, `run`, and `report`.
- Config files use TOML; prompt sets use JSONL.
- Raw telemetry uses gzip-compressed JSONL and is committed to Git.
- Unsupported telemetry values are `null`, never numeric zero.
- Model downloading is never automatic.
- Partial CPU offload invalidates a primary GPU run.
- Public artifacts contain no usernames, home paths, serial numbers, tokens,
  or raw GPU UUIDs.
- Implementation uses test-first RED-GREEN-REFACTOR cycles.

## Review Focus

- Ollama returns a final chunk without generated text: preserve the run and
  mark the request invalid rather than dividing by zero.
- NVML supports power but not total energy: select the documented fallback
  and record the source.
- The telemetry thread exits during an HTTP exception or Ctrl+C: stop and
  flush it in `finally` without losing partial samples.
- Repeated prompts reuse a prefix cache: preserve cached counts and exclude
  contaminated requests from primary aggregates.
- A public manifest contains a Windows absolute path: sanitization must reject
  it before the manifest is finalized.

---

### Task 1: Package, CLI shell, and CI

**Files:**

- Create `pyproject.toml`
- Create `src/llm_energy_bench/__init__.py`
- Create `src/llm_energy_bench/__main__.py`
- Create `src/llm_energy_bench/cli.py`
- Create `tests/test_cli.py`
- Create `.github/workflows/ci.yml`

**Produces:** `main(argv: list[str] | None = None) -> int` with `doctor`,
`run`, and `report` parsers and exit-code constants 0, 2, 3, and 4.

- [x] Write failing parser and exit-code tests.
- [x] Run `python -m pytest tests/test_cli.py -v` and verify failure.
- [x] Add the minimal package and `argparse` command shell.
- [x] Run the focused test and verify success.
- [x] Add Windows/Linux Python 3.12 CI running `ruff check` and `pytest`.
- [x] Commit as `chore: add package shell and CI`.

### Task 2: Configuration and prompt contracts

**Files:**

- Create `src/llm_energy_bench/config.py`
- Create `tests/test_config.py`
- Create `configs/pilot.toml`
- Create `prompts/pilot-v1.jsonl`

**Produces:**

```python
load_config(path: Path) -> ExperimentConfig
load_prompts(path: Path) -> tuple[PromptCase, ...]
```

`ExperimentConfig` includes experiment ID, host ID, output directory, Ollama
URL, GPU index, models, prompt path, warm-ups, repetitions, random seed,
telemetry interval, inference options, and optional tariff/currency.

- [ ] Write failing tests for valid TOML, unknown keys, invalid ranges,
  duplicate prompt IDs, missing scorer data, and absent tariff semantics.
- [ ] Run `python -m pytest tests/test_config.py -v` and verify failure.
- [ ] Implement frozen dataclasses and explicit validators using `tomllib`.
- [ ] Add the six approved pilot prompts: two short, two long, two scored.
- [ ] Run config tests and verify success.
- [ ] Commit as `feat: define experiment and prompt contracts`.

### Task 3: Result storage and integrity

**Files:**

- Create `src/llm_energy_bench/results.py`
- Create `tests/test_results.py`

**Produces:** atomic JSON, JSONL, and gzip-JSONL writers; SHA-256 helpers;
sanitization; `validate_run(run_dir: Path) -> ValidationReport`; and the fixed
run-directory layout.

- [x] Write failing tests for atomic writes, gzip round-trip, checksums,
  interrupted-run preservation, privacy rejection, and the 25 MB file limit.
- [x] Run the focused tests and verify failure.
- [x] Implement storage and validation without third-party serialization.
- [x] Run focused tests and verify success.
- [x] Commit as `feat: add immutable run artifacts`.

### Task 4: Ollama streaming client

**Files:**

- Create `src/llm_energy_bench/ollama.py`
- Create `tests/test_ollama.py`

**Produces:**

```python
OllamaClient.preload(model: str) -> RunningModel
OllamaClient.generate_stream(request: InferenceRequest) -> InferenceResult
```

The result contains client monotonic timestamps, TTFT, output text, done
reason, token counts, cache counts, and all Ollama duration fields.

- [ ] Write failing mock-stream tests for normal output, missing final chunk,
  timeout, disconnect, zero output, digest capture, and placement data.
- [ ] Run focused tests and verify failure.
- [ ] Implement `/api/tags`, `/api/ps`, preload, and `/api/generate` streaming.
- [ ] Verify no method downloads or mutates a model.
- [ ] Run focused tests and verify success.
- [ ] Commit as `feat: add Ollama streaming measurements`.

### Task 5: NVML capability probe and sampler

**Owner:** Qcsteeven

**Files:**

- Create `src/llm_energy_bench/nvml.py`
- Create `tests/test_nvml.py`

**Produces:**

```python
NvmlSampler.probe(gpu_index: int) -> GpuCapabilities
NvmlSampler.start(request_id: str) -> None
NvmlSampler.stop() -> tuple[TelemetrySample, ...]
```

Each sample contains monotonic/UTC timestamps, request ID, available power
fields, energy counter, temperature, VRAM, utilization, clocks, power limit,
and per-field errors.

- [ ] Write failing tests using a fake NVML binding for full support,
  unsupported fields, sampling exceptions, repeated start, safe stop, and
  shutdown during interruption.
- [ ] Run focused tests and verify failure.
- [ ] Implement capability probing without assuming consumer-GPU support.
- [ ] Implement a 100 ms default sampler thread with `finally` cleanup.
- [ ] Run focused tests and verify success.
- [ ] Commit as `feat: add NVML telemetry sampler`.

### Task 6: Metrics and experiment runner

**Files:**

- Create `src/llm_energy_bench/runner.py`
- Create `tests/test_runner.py`
- Extend `tests/test_results.py`

**Consumes:** configuration, Ollama result records, telemetry samples, and
atomic result writers.

**Produces:** `run_experiment(config: ExperimentConfig) -> Path` and derived
request metrics for latency, throughput, power, energy, efficiency, and cost.

- [ ] Write failing tests for deterministic order, two excluded warm-ups,
  unique leading cache-buster IDs, full-GPU preflight, telemetry cleanup,
  total-energy preference, trapezoidal fallback, and partial-run status.
- [ ] Add formula tests for J/token, token/J, and optional tariff cost.
- [ ] Run focused tests and verify failure.
- [ ] Implement the minimal orchestration and metric calculations.
- [ ] Run focused tests and verify success.
- [ ] Commit as `feat: run measured Ollama experiments`.

### Task 7: Doctor and reporting

**Files:**

- Modify `src/llm_energy_bench/cli.py`
- Modify `src/llm_energy_bench/results.py`
- Create `tests/test_report.py`

**Produces:** human/JSON doctor output and
`build_report(run_dirs: tuple[Path, ...]) -> ReportPaths`.

- [ ] Write failing doctor tests for unavailable Ollama, missing model,
  unsupported energy counter, partial GPU placement, and sanitized JSON.
- [ ] Write failing report tests for median/IQR, aggregate ratios, equal
  prompt weighting, 75% quality floor, and cross-run ranking.
- [ ] Run focused tests and verify failure.
- [ ] Implement doctor, validation summary, CSV output, and Markdown report.
- [ ] Run focused tests and verify success.
- [ ] Commit as `feat: add environment doctor and reports`.

### Task 8: RTX 3050 hardware pilot

**Files:**

- Add one run under `experiments/runs/`
- Create or append `docs/experiment-log.md`
- Update `STATUS.md`

- [ ] Install and record one Ollama version without enabling mid-campaign
  updates.
- [ ] Pull `llama3.2:3b-instruct-q4_K_M` manually.
- [ ] Run `python -m llm_energy_bench doctor --json` and confirm 100% GPU.
- [ ] Run `python -m llm_energy_bench run --config configs/pilot.toml`.
- [ ] Verify 18 measured request records, positive energy for valid requests,
  telemetry coverage, hashes, and validation status.
- [ ] Regenerate the report and confirm deterministic output.
- [ ] Run the complete `ruff check .` and `pytest` suite.
- [ ] Commit as `data: add RTX 3050 pilot run`.

### Task 9: Two-host benchmark preparation

**Files:**

- Create `configs/benchmark-v1.toml`
- Create `prompts/benchmark-v1.jsonl`
- Update `docs/research-plan.md`

- [ ] Add eight short/decode, eight long/prefill, and eight scored prompts.
- [ ] Configure five repetitions and the four fixed model/quant tags.
- [ ] Add tests confirming 24 unique prompt IDs and fixed matrix values.
- [ ] Document the repeatability CV and rank-inversion decision rules.
- [ ] Run all tests and commit as `docs: freeze benchmark v1 protocol`.

## Completion Criteria

The MVP is complete only when CI passes, the public repository workflow is in
place, the RTX 3050 pilot validates, all raw artifacts are auditable, and the
same frozen benchmark config is ready for RTX 5060 Laptop and RTX 4060 desktop.
