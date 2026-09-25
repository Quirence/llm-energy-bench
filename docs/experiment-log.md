# Experiment Log

This file is the append-only human index of hardware runs committed under
`experiments/runs/`. Raw artifacts and their manifest hashes remain the source
of truth. Do not rewrite earlier entries when analysis changes; append a dated
correction that references the original run ID.

Each completed entry records:

- date, contributor, host role, GPU, driver, and power limit;
- Git commit, runtime version, model tag and digest, and config/prompt hashes;
- run ID, validation outcome, valid/request counts, and energy source;
- material anomalies, exclusions, and links to the committed run directory.

Environment probes that do not execute an LLM request belong in the separate
section below and are never counted as experimental runs.

## Validated Experimental Runs

None yet. The first entry will be the RTX 3050 Laptop `pilot-v1` run after
Ollama and `llama3.2:3b-instruct-q4_K_M` are available locally.

## Environment Probes

### 2026-09-20 — RTX 3050 Laptop NVML smoke check

- Contributor: Quirence/Codex
- GPU: NVIDIA GeForce RTX 3050 Laptop GPU, 4 GiB
- Driver: 572.83
- Reported power limit: approximately 74–75 W
- Capability result: temperature, clocks, utilization, memory, instantaneous
  power, legacy power, total-energy counter, and power limit are available.
- Observation: over two idle samples the total-energy delta was about
  171–205 J for roughly 2 s, while instantaneous-power integration measured
  about 23–24 J at 11.6–11.9 W average power.
- Decision: treat the counter as physically inconsistent on this host/driver.
  The implemented per-request sanity check falls back to
  `power_instant_integration` and records the rejection reason.
- Scope: telemetry smoke validation only. Ollama was unavailable, no model was
  loaded, and no inference run was produced.

### 2026-09-20 — GTX 1080 Ollama runtime observation

- Contributor: Skipl1 (Dimas)
- Scope: Issue #7 runtime validation. This entry executed real inference
  requests, but it is **not** an experimental run: the GPU is outside the
  research matrix and the workload was three ad-hoc prompts at one
  repetition, not the frozen protocol. Its artifacts were written outside the
  repository and are not committed.
- GPU: NVIDIA GeForce GTX 1080, 8 GiB, compute capability 6.1
- Driver: 582.66; reported power limit 200 W
- Runtime: Ollama 0.34.2; model `llama3.2:3b-instruct-q4_K_M`, digest
  `a80c4f17acd5…`, pulled by hand
- Result: `doctor --json` reported `ok: true` with the live version, the
  resolved digest and `gpu_fraction 1.0`; the run completed in 10.5 s and
  wrote every artifact with `energy_source: total_energy_counter`.
- Findings that block measurement everywhere: the chat-template prompt-cache
  floor of 20–21 tokens against a rule that rejects any cached token, and a
  cache buster whose shared run-ID head is itself cached. See
  `docs/ollama-runtime-observations.md`.
- Telemetry note: unlike the RTX 3050 host, this driver's total-energy counter
  is self-consistent, matching integrated power to about 1.5%.

## Methodology Decisions

### 2026-09-25 — Ollama template-cache baseline

- Source observation: the 2026-09-20 GTX 1080 runtime check above found a
  stable 20–21 token chat-template floor and additional contamination from a
  shared cache-buster prefix.
- Decision: require at least two warm-ups for every model and use the final
  warm-up's cached count as the recorded per-model, per-digest baseline.
- Validity rule: a measured cached count must be present and no larger than the
  baseline. The raw count, applied baseline, and excess are persisted and
  independently checked by semantic validation.
- Prompt construction: a deterministic SHA-256 request nonce is the literal
  first line, before the shared marker and prompt body.
- Metric rule: prefill throughput excludes all cached tokens, including the
  accepted template floor.
- Scope: code and synthetic-test validation only. The policy is not considered
  hardware-validated until it passes against Ollama on the RTX 5060 host.
