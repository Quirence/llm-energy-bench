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

No primary-matrix run has been published yet. The first such entry will be the
RTX 5060 Laptop `pilot-v1` run repeated from the reviewed, merged implementation.
Observation-only launches are recorded below but cannot enter the primary
decision blocks.

### 2026-09-28 — GTX 1080 pilot-v1 observation launch (before the tag)

- Contributor: Skipl1 (Dimas)
- Host role: **observation-only**, outside the primary two-host matrix. It
  must not enter the primary decision blocks.
- Code: `0ffc091`, the squash-merge commit of PR #17, whose tree is identical
  to the approved head `9c8a5d9`. **The run was made before `pilot-v1-code`
  was tagged**: `git tag --points-at HEAD` returned nothing. If the tag is
  placed on `0ffc091`, this run used the tagged code; otherwise it has to be
  repeated from the tag.
- GPU: NVIDIA GeForce GTX 1080, 8 GiB; driver 582.66; power limit 200 W.
- Runtime and model: Ollama 0.34.2; `llama3.2:3b-instruct-q4_K_M`, digest
  `a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`.
- Config and prompts: committed `configs/pilot-gtx1080-observation.toml`,
  config hash `58b255cfdb4a…`, prompt-set hash `c7c4ae95e164…`.
- Preflight: `doctor --config configs/pilot-gtx1080-observation.toml --json`
  returned `ok: true`. The runtime version and model digest matched the frozen
  values, with `fully_on_gpu: true`, `gpu_fraction: 1.0`, and
  `energy_source: total_energy_counter`.
- Conditions: desktop on mains power; no wallpaper renderer or other GPU
  workload running. Idle power was a median 8.3 W in P8 before `doctor`, and
  10.6 W 30 s after it, immediately before the launch. Peak GPU temperature
  was 49 °C.
- Run ID: `pilot-v1-observation-gtx1080-observation-20260928T155322Z-989238`,
  committed under `experiments/runs/`.
- Result: the CLI returned success, `validation.json` reports `ok: true`, and
  18/18 measured requests are valid. The four warm-ups reported 0, 20, 20 and
  20 cached tokens, giving a floor of 20. Every measured request reported 20
  cached tokens (excess 0). The largest measured `load_duration` was 2.3 ms,
  and warm-ups stayed at 1.9–2.1 ms. All 18 requests used the total-energy
  counter with no fallback. Quality was 1.0.
- Ratio-of-sums metrics: `short` 78.3 tok/s and 0.420 tok/J, `long` 57.8
  tok/s and 0.315 tok/J, `scored` 22.5 tok/s and 0.128 tok/J, at a mean GPU
  power of 176–186 W.
- Anomalies: none. The pre-launch idle reading was about 2 W above the
  session idle because `doctor` had just preloaded the model.

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

#### Provisional combined integration run

- Scope: local acceptance of the combined, still-unmerged PR #14, PR #15, and
  PR #16 changes. The run directory is intentionally ignored by Git and must
  not be treated as a frozen or published research artifact.
- Workload: the six `pilot-v1` prompts, three measured repetitions, two
  excluded warm-ups, one model, concurrency 1, and 18 measured requests.
- Runtime and placement: Ollama 0.34.2; the same model digest listed above;
  context 4096; GPU fraction 1.0 on the RTX 5060 Laptop.
- Cache result: the final warm-up established a 20-token template baseline.
  All 18 measured requests reported 20 raw cached tokens and zero excess, so
  none was rejected as prompt-cache contamination.
- Telemetry result: semantic validation accepted all 18 requests. Seventeen
  requests used the total-energy counter after its per-request sanity check;
  one short request produced no positive counter delta and fell back to
  instantaneous-power integration. For requests that retained the counter,
  its energy was approximately 0.73--1.29 times the independently integrated
  instantaneous-power estimate. The mixed source is recorded explicitly in
  the derived summary rather than hidden.
- Coverage: the largest observed telemetry gap was 125 ms, below the 500 ms
  rejection threshold. The maximum observed power sample was 91.70 W; this is
  an observed sample, not a claim about wall power or sustained TGP.
- Analysis result: the report generated successfully, but no comparative rank
  is possible with one model configuration. The scored prompts averaged 0.5,
  below the frozen 0.75 quality floor, so the configuration was correctly
  excluded from ranking. A follow-up A/B check showed that the current leading
  raw SHA-256 cache-buster changed the arithmetic answer from `391` to a safety
  refusal. Therefore the observed score is a measurement-instrument confound,
  not evidence about the model's arithmetic quality. PR #16 records the
  proposed UUID-form marker design and must be updated before the repeated run.
- Decision: the acceptance run supports the implementation path only. It
  makes no speed-versus-energy research claim and will be repeated from the
  reviewed, merged commit before publication.

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

### 2026-09-25 — UUID cache-marker correction and acceptance

- Correction: the raw SHA-256 first-line marker above is retained as historical
  context but is superseded. A live A/B check found that it changed the
  arithmetic utility answer from `391` to a safety refusal.
- Decision: encode the first 16 SHA-256 bytes as a deterministic UUID v4 and
  follow it with an explicit instruction that the benchmark marker is metadata
  to ignore. A logical prompt and repetition share a marker across model
  configurations in the same run.
- Diagnostic evidence: 10/10 arithmetic requests returned `391` with the UUID
  marker and all 10 reported the 20-token template floor.
- Stabilization acceptance: the complete six-prompt workload then produced
  18/18 valid measured requests on the RTX 5060 Laptop, all with raw cache 20
  and excess cache 0. Both scored prompts passed in all three repetitions, so
  the aggregate quality score was 1.0. All requests selected instantaneous
  power integration during this run.
- Scope: ignored local acceptance artifact from the unmerged stabilization
  branch. It verifies the correction but is not the publishable research run;
  the run must be repeated from the reviewed `pilot-v1-code` tag.

### 2026-09-28 — Schema-v2 validity correction

- New evidence: RTX 4060 Ti and GTX 1080 local observations found intermittent
  cache counts exactly one token above the recorded floor. The GTX 1080 also
  showed that one final-warm-up baseline can be inflated and that the request
  following a CUDA/runtime crash can include a multi-second model reload while
  passing the old validator.
- Superseding decision: use four excluded warm-ups. Treat the first as the
  cold-start exclusion and define the template floor as the minimum cached
  count across warm-ups two through four. Persist every warm-up record.
- Cache validity: allow at most one cached token above the floor. This bounded
  tolerance covers the observed unique-marker tokenizer boundary; two or more
  excess tokens remain invalid.
- Runtime validity: a measured `load_duration` above 100 ms is a model reload.
  Persist the invalid request, abort the launch, and restart the complete run.
- Schema decision: emit schema v2, retain the original zero-cache validator for
  schema v1, and reject missing or unknown schema versions.
- Reporting correction: aggregate prefill uses persisted uncached prompt tokens;
  invalid runs contribute no aggregate ranks or claims.
- Scope: methodology and synthetic-test correction on PR #17. Earlier local
  observations remain outside the dataset and are summarized in
  `docs/diagnostic-observations.md`.

### 2026-09-28 — RTX 5060 schema-v2 preflight

- Contributor: Quirence/Codex.
- Command: `doctor --config configs/pilot-rtx5060.toml --json` from the final
  stabilization working tree; no experiment run directory was created.
- GPU/NVML: NVIDIA GeForce RTX 5060 Laptop GPU, driver 591.66, 80 W reported
  power limit, total-energy/instantaneous/legacy power fields available.
- Model: `llama3.2:3b-instruct-q4_K_M`, full frozen digest matched, context
  4096, `size_vram == size == 2,554,708,622`, GPU fraction 1.0.
- Runtime gate: the installed Ollama reported 0.34.4, while the approved pilot
  config requires 0.34.2. `doctor` correctly returned `ok: false`.
- Decision: do not launch or publish the pilot under mixed runtime versions.
  Use the frozen 0.34.2 runtime on every host, or approve one protocol-wide
  amendment and repeat preflight everywhere.

### 2026-09-28 — Prospective host-matrix amendment

- Timing: the amendment was made before `pilot-v1-code` was tagged and before
  any publishable run existed.
- Evidence: the contributor machine available for the second primary campaign
  is an RTX 4060 Ti desktop, not the originally anticipated RTX 4060 desktop.
- Decision: name RTX 5060 Laptop and RTX 4060 Ti desktop as the two primary
  hosts. Do not alias one GPU model as the other.
- Additional host: GTX 1080 receives a committed observation-only pilot config
  with the same runtime, model, prompt, and inference controls. It remains
  outside the primary two-host decision blocks.
- Historical data: all earlier RTX 4060 Ti and GTX 1080 local launches remain
  diagnostics. The amendment does not retroactively validate them; every
  accepted run must be repeated from the tagged schema-v2 baseline.
