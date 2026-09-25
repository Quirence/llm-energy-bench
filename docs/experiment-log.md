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

### 2026-09-25 — RTX 5060 Laptop NVML reliability check

- Contributor: Quirence/Codex
- GPU: NVIDIA GeForce RTX 5060 Laptop GPU, 8 GiB
- Driver: 591.66; reported power limit 80 W
- Capability result: all requested NVML fields are exposed.
- Initial observation: the total-energy counter implied hundreds of watts at
  idle and was rejected by the existing physical-consistency check. A stress
  probe also found equal consecutive monotonic timestamps in 6 of 20 short
  windows and one transient 4666 W instantaneous-power sample. The former made
  otherwise usable integrations unavailable; the latter could dominate an
  energy result.
- Corrective check: equal timestamps now retain the latest reading while a
  decreasing timestamp remains invalid. A power stream containing a reading
  above 120% of the enforced limit is rejected rather than clipped, with
  fallback from instantaneous to legacy power.
- Verification: 20 consecutive 0.25 s windows at a 50 ms sampling interval
  all selected `power_instant_integration`; none was unavailable. Observed
  average and peak power stayed within approximately 8.71–9.21 W.
- Scope: telemetry reliability validation at idle only. Ollama was not
  installed during the initial probe, no model was loaded, and no inference
  run was produced.

#### Follow-up after Ollama installation

- Runtime: Ollama 0.34.2, installed from the pinned `winget` package with a
  verified installer hash.
- Model: `llama3.2:3b-instruct-q4_K_M`, digest
  `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`,
  quantization Q4_K_M, parameter size 3.2B.
- Placement preflight: context 4096, `size_vram == size == 2,554,708,622`
  bytes, GPU fraction 1.0.
- Cache probe: the first excluded request paid 43.85 s of one-time startup;
  the second completed in 0.58 s and reported a 20-token template floor. A
  long-prompt probe then reported 20 cached of 468 prompt tokens, so the PR #16
  policy recorded zero excess.
- Loaded telemetry probe: a 256-output-token request completed in 2.47 s with
  51 samples and a 63 ms maximum gap. The total-energy counter reported a
  physically impossible 299.26 J delta. PR #15 rejected it and integrated
  instantaneous power instead: 152.55 J, 61.79 W average, and 91.90 W observed
  peak.
- Scope: component-level hardware acceptance only. This was not the frozen
  18-request pilot, no run directory was created, and no research comparison
  is inferred from these values.

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
